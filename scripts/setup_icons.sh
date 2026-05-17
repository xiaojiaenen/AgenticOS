#!/bin/bash
# 从本地 ppt-master 复制图标库到 data/icons/
# 图标文件太大（47MB, 11631 个 SVG），不适合直接提交到 git

set -e

PPT_MASTER_DIR="${PPT_MASTER_DIR:-$HOME/code/ppt-master}"
SOURCE="$PPT_MASTER_DIR/skills/ppt-master/templates/icons"
TARGET="$(cd "$(dirname "$0")/.." && pwd)/data/icons"

if [ ! -d "$SOURCE" ]; then
    echo "错误: 找不到 ppt-master 图标目录: $SOURCE"
    echo "请设置 PPT_MASTER_DIR 环境变量指向 ppt-master 仓库路径"
    exit 1
fi

echo "从 $SOURCE 复制图标到 $TARGET ..."
mkdir -p "$TARGET"
cp -r "$SOURCE"/* "$TARGET"/
echo "完成: $(find "$TARGET" -name '*.svg' | wc -l) 个图标文件已复制"
