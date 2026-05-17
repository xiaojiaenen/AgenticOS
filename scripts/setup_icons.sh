#!/bin/bash
# 解压图标库到 data/icons/
# 图标压缩包独立自包含，不依赖外部仓库

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ARCHIVE="$PROJECT_ROOT/data/icons.tar.gz"
TARGET="$PROJECT_ROOT/data/icons"

if [ -d "$TARGET" ] && [ "$(ls -A "$TARGET" 2>/dev/null)" ]; then
    echo "data/icons/ 已存在且非空，跳过解压"
    exit 0
fi

if [ ! -f "$ARCHIVE" ]; then
    echo "错误: 找不到 $ARCHIVE"
    exit 1
fi

echo "解压图标库到 $TARGET ..."
mkdir -p "$TARGET"
tar -xzf "$ARCHIVE" -C "$PROJECT_ROOT/data/"
echo "完成: $(find "$TARGET" -name '*.svg' | wc -l) 个图标文件"
