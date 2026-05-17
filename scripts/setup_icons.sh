#!/bin/bash
# 解压图标库到 data/icons/
# 图标压缩包独立自包含，不依赖外部仓库

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ARCHIVES_DIR="$PROJECT_ROOT/data/icons_archives"
TARGET="$PROJECT_ROOT/data/icons"

if [ -d "$TARGET" ] && [ "$(ls -A "$TARGET" 2>/dev/null)" ]; then
    echo "data/icons/ 已存在且非空，跳过解压"
    exit 0
fi

if [ ! -d "$ARCHIVES_DIR" ]; then
    echo "错误: 找不到 $ARCHIVES_DIR"
    exit 1
fi

echo "解压图标库到 $TARGET ..."
mkdir -p "$TARGET"
for archive in "$ARCHIVES_DIR"/*.tar.gz; do
    echo "  解压 $(basename "$archive") ..."
    tar -xzf "$archive" -C "$TARGET"
done
echo "完成: $(find "$TARGET" -name '*.svg' | wc -l) 个图标文件"
