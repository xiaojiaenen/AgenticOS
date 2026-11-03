// =============================================================================
//  cdg-bridge / probe.cpp
//  最小验证：确认“借进程”是否成立。3 行核心逻辑，先跑这个再谈别的。
//
//  编译： cl /nologo /LD /EHsc /O2 /MT probe.cpp /Fe:probe.dll
//  用法： rundll32.exe "probe.dll",Probe "<源文件>|<输出文件>"
//         rundll32.exe "probe.dll",Probe "D:\Data\排班表.xlsx|D:\Work\dump.xlsx"
//
//  结果判定（读 dump 文件头）：
//    50 4B 03 04  → 成功：宿主进程拿到了明文，且写出的文件也是明文
//    其他魔数      → 宿主不在白名单，换下一个宿主
//    报错/0 字节   → 路径或权限问题
// =============================================================================

#define WIN32_LEAN_AND_MEAN
#define _CRT_SECURE_NO_WARNINGS
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <string>

static std::string WToU8(const std::wstring& w) {
    if (w.empty()) return std::string();
    int n = WideCharToMultiByte(CP_UTF8, 0, w.c_str(), (int)w.size(), nullptr, 0, nullptr, nullptr);
    std::string s((size_t)n, '\0');
    WideCharToMultiByte(CP_UTF8, 0, w.c_str(), (int)w.size(), &s[0], n, nullptr, nullptr);
    return s;
}

static std::string HexHead(const wchar_t* path, DWORD n) {
    HANDLE h = CreateFileW(path, GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        nullptr, OPEN_EXISTING, 0, nullptr);
    if (h == INVALID_HANDLE_VALUE) return "<open failed>";
    char buf[64] = { 0 };
    DWORD rd = 0;
    ReadFile(h, buf, n, &rd, nullptr);
    CloseHandle(h);
    std::string o;
    char b[8];
    for (DWORD i = 0; i < rd; ++i) {
        sprintf_s(b, "%02X", (unsigned char)buf[i]);
        if (i) o.push_back(' ');
        o.append(b);
    }
    if (o.empty()) o = "<empty>";
    return o;
}

extern "C" __declspec(dllexport)
void __stdcall Probe(HWND, HINSTANCE, LPSTR cmdLine, int) {
    if (!cmdLine || !*cmdLine) return;

    std::string line = cmdLine;
    // 去掉包裹引号
    if (line.size() >= 2 && line.front() == '"' && line.back() == '"')
        line = line.substr(1, line.size() - 2);

    size_t bar = line.find('|');
    if (bar == std::string::npos) return;
    std::string src = line.substr(0, bar);
    std::string dst = line.substr(bar + 1);

    std::wstring wsrc(src.begin(), src.end());   // 纯 ASCII 路径场景
    std::wstring wdst(dst.begin(), dst.end());

    // 若路径含中文，cmdLine 是 ANSI，需按 ANSI→UTF8→宽字符转换
    if (line.find('\x00') == std::string::npos) {
        wsrc = std::wstring();
        int n = MultiByteToWideChar(CP_ACP, 0, src.c_str(), (int)src.size(), nullptr, 0);
        if (n > 0) { wsrc.resize((size_t)n); MultiByteToWideChar(CP_ACP, 0, src.c_str(), (int)src.size(), &wsrc[0], n); }
        n = MultiByteToWideChar(CP_ACP, 0, dst.c_str(), (int)dst.size(), nullptr, 0);
        wdst = std::wstring();
        if (n > 0) { wdst.resize((size_t)n); MultiByteToWideChar(CP_ACP, 0, dst.c_str(), (int)dst.size(), &wdst[0], n); }
    }

    BOOL copied = CopyFileW(wsrc.c_str(), wdst.c_str(), FALSE);

    wchar_t exe[MAX_PATH] = L"";
    GetModuleFileNameW(nullptr, exe, MAX_PATH);

    std::string report;
    report += "host_exe   = " + WToU8(exe) + "\r\n";
    report += "host_pid   = " + std::to_string(GetCurrentProcessId()) + "\r\n";
    report += "src        = " + src + "\r\n";
    report += "dst        = " + dst + "\r\n";
    report += "copy_ok    = " + std::string(copied ? "true" : "false") + "\r\n";
    report += "src_head   = " + HexHead(wsrc.c_str(), 16) + "\r\n";
    report += "dst_head   = " + HexHead(wdst.c_str(), 16) + "\r\n";

    std::wstring logPath = wdst + L".probe.txt";
    HANDLE h = CreateFileW(logPath.c_str(), GENERIC_WRITE, 0, nullptr,
                           CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h != INVALID_HANDLE_VALUE) {
        DWORD w = 0;
        WriteFile(h, report.data(), (DWORD)report.size(), &w, nullptr);
        CloseHandle(h);
    }
}
