#!/bin/bash
# 下载并解压图标库到 data/icons/
# 图标库通过 GitHub Release 分发，独立自包含

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET="$PROJECT_ROOT/data/icons"
VERSION="${ICONS_VERSION:-v1.0.0}"
RELEASE_URL="https://github.com/xiaojiaenen/AgenticOS/releases/download/icons-${VERSION}/icons.tar.gz"

if [ -d "$TARGET" ] && [ "$(ls -A "$TARGET" 2>/dev/null)" ]; then
    echo "data/icons/ 已存在且非空，跳过"
    exit 0
fi

mkdir -p "$TARGET"

ARCHIVE="/tmp/icons-${VERSION}.tar.gz"

if [ -f "$ARCHIVE" ]; then
    echo "使用本地缓存 $ARCHIVE"
else
    echo "从 GitHub Release 下载图标库 ..."
    curl -L -o "$ARCHIVE" "$RELEASE_URL" || {
        echo "错误: 下载失败，请手动下载 $RELEASE_URL"
        echo "      并解压到 $TARGET"
        exit 1
    }
fi

echo "解压图标库到 $TARGET ..."
tar -xzf "$ARCHIVE" -C "$TARGET" --strip-components=1
rm -f "$ARCHIVE"

echo "生成图标索引 ..."
python3 -c "
import json, os
index = {}
for lib in sorted(os.listdir('$TARGET')):
    lib_path = os.path.join('$TARGET', lib)
    if os.path.isdir(lib_path):
        names = sorted([f.replace('.svg', '') for f in os.listdir(lib_path) if f.endswith('.svg')])
        index[lib] = names
with open(os.path.join('$TARGET', 'icon_index.json'), 'w') as f:
    json.dump(index, f, ensure_ascii=False)
print(f'索引已生成: {sum(len(v) for v in index.values())} 个图标')
"

echo "完成: $(find "$TARGET" -name '*.svg' | wc -l) 个图标文件"
