"""
批量诊断：扫描目录下所有 Office/PDF 文件，判定明文还是密文。
用来确认桥是否真的绕过了透明加密。

    python examples\\diagnose.py "D:\\Data"
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import cdgfs

EXTS = {".xlsx", ".xls", ".docx", ".doc", ".pptx", ".ppt", ".pdf"}


def main(root: str):
    print(f"root = {root}")
    try:
        host = cdgfs.ping()
        print(f"bridge = pid {host['pid']}  {host['exe']}")
    except cdgfs.BridgeError as e:
        print(f"[ERR] {e}")
        return 1

    total = plain = cipher = unknown = 0
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() not in EXTS:
                continue
            p = os.path.join(dirpath, fn)
            total += 1
            try:
                kind, detail = cdgfs.classify(p)
            except cdgfs.BridgeError as e:
                kind, detail = "error", str(e)
            if kind == "plain":
                plain += 1
            elif kind == "cipher":
                cipher += 1
            else:
                unknown += 1
            print(f"{kind:8s} {os.path.getsize(p):>10}  {detail[:40]:40s}  {p}")

    print()
    print(f"总计 {total}：明文 {plain}，密文 {cipher}，未知/失败 {unknown}")
    if cipher == 0 and total > 0:
        print("→ 全部明文：桥已绕过透明加密，可以直接读写原始字节")
    elif cipher > 0:
        print("→ 存在密文：当前宿主不在白名单，换宿主（dllhost.exe / explorer.exe）再试")
    return 0


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    sys.exit(main(root))
