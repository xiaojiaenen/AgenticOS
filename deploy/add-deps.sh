#!/bin/sh
# 依赖热更新脚本（内网有 PyPI 仓库时用，避免重建 3.9GB 镜像）
#
# 用法（在部署机 /opt/agenticos/deploy 下）：
#   sh add-deps.sh requests==2.32.3 "pandas>=2.0"
#
# 原理：容器根文件系统只读，但 /app/data 是可写卷。把新增依赖装到
# /app/data/pylibs，并用 PYTHONPATH 前置，让 Python 优先从这里加载。
# compose 里已设置 PYTHONPATH=/app/data/pylibs:/app/backend。
set -e

if [ $# -eq 0 ]; then
    echo "用法: sh add-deps.sh <包名...>"
    echo "示例: sh add-deps.sh 'requests==2.32.3' 'pandas>=2.0'"
    exit 1
fi

PYPI_MIRROR=${PYPI_MIRROR:-http://pypi.local/simple}
CONTAINER=${CONTAINER:-agenticos-backend-1}

echo "目标容器: $CONTAINER"
echo "PyPI 源:  $PYPI_MIRROR"
echo "安装:     $*"

# 1. 装到可写卷（backend 容器内执行）
docker exec "$CONTAINER" sh -c \
    "mkdir -p /app/data/pylibs && pip install --no-cache-dir --target=/app/data/pylibs -i $PYPI_MIRROR $*"

# 2. worker 共享同一挂载，无需重复安装（同一 /app/data 卷）

# 3. 重启使新依赖生效（PYTHONPATH 已指向该目录）
cd "$(dirname "$0")"
docker compose -f docker-compose.offline.yml restart backend worker

echo ""
echo "完成。验证："
echo "  docker exec $CONTAINER python -c 'import <包名>; print(<包名>.__file__)'"
echo "  应显示 /app/data/pylibs/... 而不是 /usr/local/lib/python3.13/site-packages/..."
