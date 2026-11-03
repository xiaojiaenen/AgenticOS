// =============================================================================
//  cdg-bridge / bridge.cpp
//  在“白名单进程”里执行文件 I/O，通过命名管道把明文原始字节交给你的平台。
//
//  编译： cl /nologo /LD /EHsc /O2 /MT /std:c++17 /DUNICODE /D_UNICODE bridge.cpp /Fe:bridge.dll
//  启动： rundll32.exe "D:\Tools\cdg-bridge\bin\bridge.dll",Start
//
//  为什么成立：
//    透明加密驱动按“发起 I/O 的进程”决定返回明文还是密文。
//    rundll32.exe 是系统进程，DLP 必须把它加白（否则系统功能会崩）。
//    于是 CreateFileW 的发起者是 rundll32 → 驱动透明解密 → 拿到明文原始字节。
//    本 DLL 里所有的 ReadFile/WriteFile 都在 rundll32 的进程上下文里执行。
//
//  协议（行头 + 可选裸数据，全部 UTF-8，路径用 \t 分隔）：
//    PING                                        -> OK\tpong\t<pid>\t<exe>
//    INFO                                        -> OK\t<k=v ...>
//    READ\t<path>                                -> OK\t<size>\n<bytes>
//    READCHUNK\t<path>\t<offset>\t<len>          -> OK\t<len>\n<bytes>
//    HEAD\t<path>\t<n>                           -> OK\t<hex>
//    WRITE\t<path>\t<size>\n<bytes>              -> OK
//    STAT\t<path>                                -> OK\t<size>\t<atime>\t<mtime>\t<ctime>\t<attr>
//    LIST\t<dir>\t<pattern>                      -> OK\t<count>\n<name>\t<size>\t<mtime>\t<attr>\n...
//    COPY\t<src>\t<dst>                          -> OK
//    DEL\t<path>                                 -> OK
//    MKDIR\t<path>                               -> OK
//    QUIT                                        -> OK
//    失败统一： ERR\t<winerror>\t<msg>
// =============================================================================

#define WIN32_LEAN_AND_MEAN
#define _CRT_SECURE_NO_WARNINGS

#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <string>
#include <vector>

static const wchar_t* PIPE_NAME_DEFAULT = L"\\\\.\\pipe\\cdgbridge";
static wchar_t g_pipe_name[512] = L"\\\\.\\pipe\\cdgbridge";
static const DWORD PIPE_BUF = 1 << 20;      // 1MB 管道缓冲
static const DWORD CHUNK    = 1 << 16;      // 64KB 单次 I/O
static volatile LONG g_run  = 1;

// ---------------------------------------------------------------- 编码工具
static std::wstring U8ToW(const std::string& s) {
    if (s.empty()) return std::wstring();
    int n = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), (int)s.size(), nullptr, 0);
    if (n <= 0) return std::wstring();
    std::wstring w((size_t)n, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.c_str(), (int)s.size(), &w[0], n);
    return w;
}

static std::string WToU8(const std::wstring& w) {
    if (w.empty()) return std::string();
    int n = WideCharToMultiByte(CP_UTF8, 0, w.c_str(), (int)w.size(), nullptr, 0, nullptr, nullptr);
    if (n <= 0) return std::string();
    std::string s((size_t)n, '\0');
    WideCharToMultiByte(CP_UTF8, 0, w.c_str(), (int)w.size(), &s[0], n, nullptr, nullptr);
    return s;
}

// ---------------------------------------------------------------- 管道收发
static bool SendBytes(HANDLE h, const void* p, size_t n) {
    const char* q = (const char*)p;
    DWORD w = 0;
    while (n > 0) {
        DWORD c = (DWORD)(n > CHUNK ? CHUNK : n);
        if (!WriteFile(h, q, c, &w, nullptr) || w == 0) return false;
        q += w; n -= w;
    }
    return true;
}

static bool SendStr(HANDLE h, const std::string& s) {
    return SendBytes(h, s.data(), s.size());
}

static bool ReadN(HANDLE h, void* buf, size_t n) {
    char* p = (char*)buf;
    size_t got = 0;
    DWORD r = 0;
    while (got < n) {
        DWORD c = (DWORD)((n - got) > CHUNK ? CHUNK : (n - got));
        if (!ReadFile(h, p + got, c, &r, nullptr) || r == 0) return false;
        got += r;
    }
    return true;
}

static std::string ReadLine(HANDLE h) {
    std::string s;
    char c = 0;
    DWORD r = 0;
    while (ReadFile(h, &c, 1, &r, nullptr) && r == 1) {
        if (c == '\n') break;
        if (c != '\r') s.push_back(c);
    }
    return s;
}

static std::vector<std::string> SplitTab(const std::string& s) {
    std::vector<std::string> out;
    size_t p = 0;
    while (true) {
        size_t t = s.find('\t', p);
        if (t == std::string::npos) { out.push_back(s.substr(p)); break; }
        out.push_back(s.substr(p, t - p));
        p = t + 1;
    }
    return out;
}

static void ReplyErr(HANDLE h, DWORD code, const char* msg) {
    char buf[512];
    sprintf_s(buf, "ERR\t%lu\t%s\n", (unsigned long)code, msg ? msg : "error");
    SendStr(h, buf);
}

// ---------------------------------------------------------------- 文件操作
static bool ReadAll(const std::wstring& path, std::string& out) {
    HANDLE h = CreateFileW(path.c_str(), GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        nullptr, OPEN_EXISTING, FILE_FLAG_SEQUENTIAL_SCAN, nullptr);
    if (h == INVALID_HANDLE_VALUE) return false;

    LARGE_INTEGER sz{};
    if (!GetFileSizeEx(h, &sz)) { CloseHandle(h); return false; }
    out.clear();
    out.resize((size_t)sz.QuadPart);

    bool ok = true;
    if (out.size() > 0) ok = ReadN(h, out.data(), out.size());
    CloseHandle(h);
    return ok;
}

static bool WriteAll(const std::wstring& path, const std::string& data) {
    HANDLE h = CreateFileW(path.c_str(), GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) return false;

    bool ok = true;
    if (data.size() > 0) ok = SendBytes(h, data.data(), data.size());
    CloseHandle(h);
    return ok;
}

static bool ReadChunk(const std::wstring& path, unsigned long long off, unsigned long long len, std::string& out) {
    HANDLE h = CreateFileW(path.c_str(), GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) return false;

    LARGE_INTEGER li{}; li.QuadPart = (LONGLONG)off;
    if (!SetFilePointerEx(h, li, nullptr, FILE_BEGIN)) { CloseHandle(h); return false; }

    out.clear();
    out.resize((size_t)len);
    bool ok = true;
    if (len > 0) {
        DWORD rd = 0;
        ok = ReadFile(h, out.data(), (DWORD)len, &rd, nullptr);
        out.resize(rd);
    }
    CloseHandle(h);
    return ok;
}

static bool ReadHead(const std::wstring& path, DWORD n, std::string& out) {
    HANDLE h = CreateFileW(path.c_str(), GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) return false;

    out.assign((size_t)n, '\0');
    DWORD rd = 0;
    bool ok = ReadFile(h, &out[0], n, &rd, nullptr);
    out.resize(rd);
    CloseHandle(h);
    return ok;
}

static std::string ToHex(const std::string& s) {
    std::string o;
    o.reserve(s.size() * 3);
    char b[8];
    for (size_t i = 0; i < s.size(); ++i) {
        sprintf_s(b, "%02X", (unsigned char)s[i]);
        if (i) o.push_back(' ');
        o.append(b);
    }
    return o;
}

// ---------------------------------------------------------------- 命令分发
static void HandleClient(HANDLE pipe) {
    std::string line = ReadLine(pipe);
    if (line.empty()) return;

    std::vector<std::string> f = SplitTab(line);
    std::string cmd = f[0];
    for (auto& ch : cmd) ch = (char)toupper((unsigned char)ch);

    // ---- PING / INFO / QUIT
    if (cmd == "PING") {
        wchar_t exe[MAX_PATH] = L"";
        GetModuleFileNameW(nullptr, exe, MAX_PATH);
        std::string sExe = WToU8(exe);
        char buf[1024];
        sprintf_s(buf, "OK\tpong\t%lu\t%s\n",
            (unsigned long)GetCurrentProcessId(), sExe.c_str());
        SendStr(pipe, buf);
        return;
    }
    if (cmd == "INFO") {
        wchar_t exe[MAX_PATH] = L"";
        GetModuleFileNameW(nullptr, exe, MAX_PATH);
        std::wstring user;
        {
            wchar_t b[256] = L"";
            DWORD cb = 256;
            if (GetUserNameW(b, &cb)) user = b;
        }
        std::string sExe = WToU8(exe);
        std::string sUser = WToU8(user);
        std::string sPipe = WToU8(g_pipe_name);
        char buf[2048];
        sprintf_s(buf, "OK\tpid=%lu\texe=%s\tuser=%s\tpipe=%s\n",
            (unsigned long)GetCurrentProcessId(),
            sExe.c_str(), sUser.c_str(), sPipe.c_str());
        SendStr(pipe, buf);
        return;
    }
    if (cmd == "QUIT") {
        InterlockedExchange(&g_run, 0);
        SendStr(pipe, "OK\n");
        FlushFileBuffers(pipe);
        // 让宿主进程真正退出（rundll32 的 Start 阻塞在 Sleep(INFINITE)）
        Sleep(200);
        ExitProcess(0);
    }

    // ---- READ
    if (cmd == "READ") {
        if (f.size() < 2) { ReplyErr(pipe, ERROR_INVALID_PARAMETER, "need path"); return; }
        std::string data;
        if (!ReadAll(U8ToW(f[1]), data)) {
            ReplyErr(pipe, GetLastError(), "read failed");
            return;
        }
        char hd[64];
        sprintf_s(hd, "OK\t%zu\n", data.size());
        SendStr(pipe, hd);
        SendBytes(pipe, data.data(), data.size());
        return;
    }

    // ---- READCHUNK
    if (cmd == "READCHUNK") {
        if (f.size() < 4) { ReplyErr(pipe, ERROR_INVALID_PARAMETER, "need path off len"); return; }
        std::string data;
        if (!ReadChunk(U8ToW(f[1]), _strtoui64(f[2].c_str(), nullptr, 10),
                       _strtoui64(f[3].c_str(), nullptr, 10), data)) {
            ReplyErr(pipe, GetLastError(), "readchunk failed");
            return;
        }
        char hd[64];
        sprintf_s(hd, "OK\t%zu\n", data.size());
        SendStr(pipe, hd);
        SendBytes(pipe, data.data(), data.size());
        return;
    }

    // ---- HEAD
    if (cmd == "HEAD") {
        if (f.size() < 2) { ReplyErr(pipe, ERROR_INVALID_PARAMETER, "need path"); return; }
        DWORD n = f.size() >= 3 ? (DWORD)atoi(f[2].c_str()) : 16;
        std::string head;
        if (!ReadHead(U8ToW(f[1]), n, head)) {
            ReplyErr(pipe, GetLastError(), "head failed");
            return;
        }
        std::string hex = ToHex(head);
        SendStr(pipe, "OK\t" + hex + "\n");
        return;
    }

    // ---- WRITE
    if (cmd == "WRITE") {
        if (f.size() < 3) { ReplyErr(pipe, ERROR_INVALID_PARAMETER, "need path size"); return; }
        size_t len = (size_t)_strtoui64(f[2].c_str(), nullptr, 10);
        std::string data;
        data.resize(len);
        if (len > 0 && !ReadN(pipe, &data[0], len)) {
            ReplyErr(pipe, ERROR_INVALID_DATA, "body truncated");
            return;
        }
        if (!WriteAll(U8ToW(f[1]), data)) {
            ReplyErr(pipe, GetLastError(), "write failed");
            return;
        }
        SendStr(pipe, "OK\n");
        return;
    }

    // ---- STAT
    if (cmd == "STAT") {
        if (f.size() < 2) { ReplyErr(pipe, ERROR_INVALID_PARAMETER, "need path"); return; }
        WIN32_FILE_ATTRIBUTE_DATA d{};
        if (!GetFileAttributesExW(U8ToW(f[1]).c_str(), GetFileExInfoStandard, &d)) {
            ReplyErr(pipe, GetLastError(), "stat failed");
            return;
        }
        unsigned long long sz = ((unsigned long long)d.nFileSizeHigh << 32) | d.nFileSizeLow;
        auto ft2u = [](FILETIME ft) -> unsigned long long {
            return ((unsigned long long)ft.dwHighDateTime << 32) | ft.dwLowDateTime;
        };
        char buf[512];
        sprintf_s(buf, "OK\t%llu\t%llu\t%llu\t%llu\t%lu\n",
            sz, ft2u(d.ftLastAccessTime), ft2u(d.ftLastWriteTime),
            ft2u(d.ftCreationTime), (unsigned long)d.dwFileAttributes);
        SendStr(pipe, buf);
        return;
    }

    // ---- LIST
    if (cmd == "LIST") {
        if (f.size() < 2) { ReplyErr(pipe, ERROR_INVALID_PARAMETER, "need dir"); return; }
        std::wstring dir = U8ToW(f[1]);
        std::wstring pat = f.size() >= 3 && !f[2].empty() ? U8ToW(f[2]) : L"*";
        std::wstring spec = dir;
        if (!spec.empty() && spec.back() != L'\\') spec.push_back(L'\\');
        spec += pat;

        WIN32_FIND_DATAW fd{};
        HANDLE hf = FindFirstFileW(spec.c_str(), &fd);
        if (hf == INVALID_HANDLE_VALUE) {
            ReplyErr(pipe, GetLastError(), "list failed");
            return;
        }
        std::vector<std::string> rows;
        do {
            if (wcscmp(fd.cFileName, L".") == 0 || wcscmp(fd.cFileName, L"..") == 0) continue;
            unsigned long long sz = ((unsigned long long)fd.nFileSizeHigh << 32) | fd.nFileSizeLow;
            unsigned long long mt = ((unsigned long long)fd.ftLastWriteTime.dwHighDateTime << 32)
                                  | fd.ftLastWriteTime.dwLowDateTime;
            char buf[1024];
            sprintf_s(buf, "%s\t%llu\t%llu\t%lu\n",
                WToU8(fd.cFileName).c_str(), sz, mt, (unsigned long)fd.dwFileAttributes);
            rows.push_back(buf);
        } while (FindNextFileW(hf, &fd));
        FindClose(hf);

        char hd[64];
        sprintf_s(hd, "OK\t%zu\n", rows.size());
        SendStr(pipe, hd);
        for (auto& r : rows) SendStr(pipe, r);
        return;
    }

    // ---- COPY
    if (cmd == "COPY") {
        if (f.size() < 3) { ReplyErr(pipe, ERROR_INVALID_PARAMETER, "need src dst"); return; }
        if (!CopyFileW(U8ToW(f[1]).c_str(), U8ToW(f[2]).c_str(), FALSE)) {
            ReplyErr(pipe, GetLastError(), "copy failed");
            return;
        }
        SendStr(pipe, "OK\n");
        return;
    }

    // ---- DEL
    if (cmd == "DEL") {
        if (f.size() < 2) { ReplyErr(pipe, ERROR_INVALID_PARAMETER, "need path"); return; }
        if (!DeleteFileW(U8ToW(f[1]).c_str())) {
            ReplyErr(pipe, GetLastError(), "del failed");
            return;
        }
        SendStr(pipe, "OK\n");
        return;
    }

    // ---- MKDIR
    if (cmd == "MKDIR") {
        if (f.size() < 2) { ReplyErr(pipe, ERROR_INVALID_PARAMETER, "need path"); return; }
        if (!CreateDirectoryW(U8ToW(f[1]).c_str(), nullptr)) {
            DWORD e = GetLastError();
            if (e != ERROR_ALREADY_EXISTS) { ReplyErr(pipe, e, "mkdir failed"); return; }
        }
        SendStr(pipe, "OK\n");
        return;
    }

    ReplyErr(pipe, ERROR_INVALID_FUNCTION, "unknown command");
}

// ---------------------------------------------------------------- 服务循环
static DWORD WINAPI ClientThread(LPVOID p) {
    HANDLE pipe = (HANDLE)p;
    __try {
        HandleClient(pipe);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        // 单个连接出错不影响整体
    }
    FlushFileBuffers(pipe);
    DisconnectNamedPipe(pipe);
    CloseHandle(pipe);
    return 0;
}

static DWORD WINAPI Server(LPVOID) {
    while (InterlockedCompareExchange(&g_run, 1, 1) == 1) {
        HANDLE pipe = CreateNamedPipeW(g_pipe_name,
            PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
            PIPE_UNLIMITED_INSTANCES,
            PIPE_BUF, PIPE_BUF, 0, nullptr);
        if (!pipe) { Sleep(100); continue; }

        BOOL ok = ConnectNamedPipe(pipe, nullptr);
        if (!ok && GetLastError() == ERROR_PIPE_CONNECTED) ok = TRUE;
        if (!ok) {
            DisconnectNamedPipe(pipe);
            CloseHandle(pipe);
            continue;
        }

        HANDLE t = CreateThread(nullptr, 0, ClientThread, (LPVOID)pipe, 0, nullptr);
        if (t) CloseHandle(t);
        else { HandleClient(pipe); DisconnectNamedPipe(pipe); CloseHandle(pipe); }
    }
    return 0;
}

// ---------------------------------------------------------------- 导出入口
// rundll32 调用签名：void __stdcall Start(HWND, HINSTANCE, LPSTR lpszCmdLine, int)
// lpszCmdLine 可传自定义管道名：rundll32.exe bridge.dll,Start cdgbridge2
extern "C" __declspec(dllexport) void __stdcall Start(HWND, HINSTANCE, LPSTR cmd, int) {
    if (cmd && *cmd) {
        while (*cmd == ' ' || *cmd == '"') ++cmd;
        std::string name = cmd;
        size_t q = name.find('"');
        if (q != std::string::npos) name = name.substr(0, q);
        // 去掉尾部空白（rundll32 会保留参数末尾空格）
        while (!name.empty() && (name.back() == ' ' || name.back() == '\t' || name.back() == '\r'))
            name.pop_back();
        if (!name.empty()) {
            std::wstring w = L"\\\\.\\pipe\\" + U8ToW(name);
            wcsncpy_s(g_pipe_name, w.c_str(), _TRUNCATE);
        }
    }

    // 单实例保护（按管道名区分，不同管道可并存）
    static wchar_t mtxName[600];
    wcscpy_s(mtxName, L"Global\\cdgbridge_singleton");
    {
        const wchar_t* tail = wcsrchr(g_pipe_name, L'\\');
        if (tail && tail[1]) wcscat_s(mtxName, tail + 1);
    }
    HANDLE mtx = CreateMutexW(nullptr, FALSE, mtxName);
    if (mtx && WaitForSingleObject(mtx, 0) != WAIT_OBJECT_0) {
        return;   // 同一管道已有实例
    }

    CreateThread(nullptr, 0, Server, nullptr, 0, nullptr);
    Sleep(INFINITE);      // 常驻，直到进程被杀
}

// 便于调试：以普通 exe/dll 宿主方式直接运行
extern "C" __declspec(dllexport) int __stdcall RunServer(const char* pipeName) {
    if (pipeName && *pipeName) {
        std::wstring w = L"\\\\.\\pipe\\" + U8ToW(pipeName);
        wcsncpy_s(g_pipe_name, w.c_str(), _TRUNCATE);
    }
    Server(nullptr);
    return 0;
}
