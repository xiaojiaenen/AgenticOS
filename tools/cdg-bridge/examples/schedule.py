"""
Excel 排班表读写示例：排版零损失（搬完整原始字节，不抽内容）。

    python examples\\schedule.py "D:\\Data\\排班表.xlsx"
"""

import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import cdgfs


def inspect(path: str):
    """读出所有 sheet 的值 + 填充色（班次色块），不改文件。"""
    import openpyxl

    raw = cdgfs.read_bytes(path)
    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=False)

    for ws in wb.worksheets:
        print(f"\n=== {ws.title}  {ws.max_row} 行 x {ws.max_column} 列 ===")
        print(f"合并区: {[str(r) for r in ws.merged_cells.ranges]}")
        for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 30)):
            cells = []
            for c in row:
                if c.value is None:
                    cells.append("")
                    continue
                fill = ""
                try:
                    if c.fill and c.fill.patternType == "solid":
                        rgb = c.fill.start_color.rgb
                        if isinstance(rgb, str) and rgb not in ("00000000", "FFFFFFFF"):
                            fill = f"[{rgb}]"
                except Exception:
                    pass
                cells.append(f"{c.value}{fill}")
            line = " | ".join(cells).rstrip(" |")
            if line.strip():
                print(f"  {row[0].row:>3}: {line}")


def edit(path: str, cell: str, value):
    """改一个单元格并写回，其余字节原样保留。"""
    import openpyxl

    raw = cdgfs.read_bytes(path)
    wb = openpyxl.load_workbook(io.BytesIO(raw))
    ws = wb.worksheets[0]
    old = ws[cell].value
    ws[cell] = value

    buf = io.BytesIO()
    wb.save(buf)
    cdgfs.write_bytes(path, buf.getvalue())
    print(f"{path}  {cell}: {old!r} -> {value!r}")
    print(f"字节数 {len(raw)} -> {len(buf.getvalue())}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    target = sys.argv[1]
    print(f"classify = {cdgfs.classify(target)}")
    if len(sys.argv) >= 5:
        edit(target, sys.argv[2], sys.argv[3])
        inspect(target)
    else:
        inspect(target)
