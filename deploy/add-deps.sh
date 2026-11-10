#!/bin/sh
# 依赖热更新脚本 —— 容器 rootfs 只读时，把新依赖装进可写挂卷
#
# 原理：compose 里已设置
#   read_only: true
#   volumes: - ../data:/app/data          (可写)
#   PYTHONPATH=/app/data/pylibs:/app/backend
# 所以 pip 不能写 /usr/local/lib/python3.13/site-packages，
# 但可以写 /app/data/pylibs；PYTHONPATH 前置让 Python 优先从这里加载。
# backend 与 worker 共享同一 /app/data 卷，装一次两个容器都生效。
#
# ── 用法 ────────────────────────────────────────────────────────────
# A) 内网有 PyPI 镜像（推荐）：
#      PYPI_MIRROR=http://<内网pypi>/simple \
#        sh add-deps.sh 'taskiq==0.13.0' 'taskiq-redis==1.2.4'
#
#      也可以一次装一组（本次 taskiq 迁移）：
#      sh add-deps.sh 'redis>=8.0,<9' 'taskiq>=0.13.0' 'taskiq-redis>=1.2.4'
#
# B) 完全离线（无 PyPI）：先把 wheel 拷到宿主机 /opt/agenticos/data/wheels/
#      sh add-deps.sh --offline 'taskiq==0.13.0'
#      sh add-deps.sh --offline                 # 装 wheels/ 下全部 wheel
#
# C) 只验证、不安装：
#      sh add-deps.sh --check taskiq
#
# 传递依赖**默认一并安装**：--target 是独立目录，pip 必须把依赖一起解进来，
# 否则装完主包会缺依赖（例如 taskiq 缺 taskiq-dependencies）→ 启动
# ModuleNotFoundError。若确认镜像里已有全部依赖、只想装主包，用
# --no-deps-only。
#
# 环境变量：
#   PYPI_MIRROR   PyPI 源，默认 http://pypi.local/simple
#   CONTAINER     容器名，默认 agenticos-backend-1（用 docker ps 确认实际名）
#   WHEELS_DIR    宿主机 wheel 目录，默认脚本同级的上级 data/wheels
set -e

PYPI_MIRROR=${PYPI_MIRROR:-http://pypi.local/simple}
CONTAINER=${CONTAINER:-agenticos-backend-1}
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
WHEELS_DIR=${WHEELS_DIR:-"$SCRIPT_DIR/../data/wheels"}

MODE="online"
# 默认**带上依赖**：--target 是独立目录，pip 必须把依赖一起解进来，
# 否则装完 taskiq 会缺 taskiq-dependencies 之类，启动即 ModuleNotFoundError。
# 想只装主包（依赖镜像里已有）用 --no-deps-only。
DEPS_FLAG=""
CHECK_ONLY=""

# ── 解析参数 ────────────────────────────────────────────────────────
PKGS=""
while [ $# -gt 0 ]; do
    case "$1" in
        --offline)      MODE="offline"; shift ;;
        --with-deps)    DEPS_FLAG=""; shift ;;
        --no-deps-only) DEPS_FLAG="--no-deps"; shift ;;
        --check)        CHECK_ONLY="1"; shift ;;
        -h|--help)
            sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        -*) echo "未知选项: $1" >&2; exit 1 ;;
        *)  PKGS="$PKGS $1"; shift ;;
    esac
done
PKGS=$(echo "$PKGS" | sed 's/^ *//')

# ── 只验证 ──────────────────────────────────────────────────────────
if [ -n "$CHECK_ONLY" ]; then
    if [ -z "$PKGS" ]; then echo "用法: sh add-deps.sh --check <模块名>" >&2; exit 1; fi
    for mod in $PKGS; do
        echo "--- $mod ---"
        docker exec "$CONTAINER" python -c \
            "import $mod, sys; print('version:', getattr($mod, '__version__', 'n/a')); print('path:', $mod.__file__)" \
            || echo "  !! 未安装或导入失败"
    done
    echo ""
    echo "若 path 以 /app/data/pylibs/ 开头 → 来自可写卷（热更新生效）"
    echo "若 path 以 /usr/local/lib/python3.13/site-packages/ 开头 → 来自镜像"
    exit 0
fi

if [ -z "$PKGS" ] && [ "$MODE" != "offline" ]; then
    echo "用法: sh add-deps.sh <包名...>        (有 PyPI 镜像)" >&2
    echo "      sh add-deps.sh --offline [包名] (离线 wheel)" >&2
    exit 1
fi

echo "目标容器: $CONTAINER"
echo "模式:     $MODE"
echo "传递依赖: $([ -n "$DEPS_FLAG" ] && echo '不装 (--no-deps)' || echo '一并安装')"
# ── 确认容器在跑 ────────────────────────────────────────────────────
if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "!! 容器 $CONTAINER 未运行。当前容器：" >&2
    docker ps --format '  {{.Names}}  {{.Status}}' >&2
    echo "用 CONTAINER=<实际名> sh add-deps.sh ... 指定" >&2
    exit 1
fi

# ── 安装 ────────────────────────────────────────────────────────────
# 关键：包名里带 `>=1.2.4,<2.0` 这类字符时，不能用 `sh -c "...$PKGS..."`
# —— `>` 会被容器里的 shell 当成重定向，报
# `cannot create =8.0.0,: Read-only file system`（真踩过）。
# 做法：把包名作为**位置参数**传给 sh -c（`sh -c 'script' _ arg1 arg2...`），
# 容器内用 "$@" 展开 —— 但 dash 不支持 "${@:2}"，所以先 shift 再取 "$@"。
if [ "$MODE" = "offline" ]; then
    IN_WHEELS="/app/data/wheels"
    if [ -z "$PKGS" ]; then
        echo "离线安装 $IN_WHEELS 下全部 wheel"
        docker exec "$CONTAINER" sh -c '
            mkdir -p /app/data/pylibs || exit 1
            exec pip install --no-cache-dir --no-index \
                --find-links="$1" --target=/app/data/pylibs --upgrade '"$DEPS_FLAG"' "$1"/*.whl
        ' _ "$IN_WHEELS"
    else
        echo "离线安装: $PKGS"
        # shellcheck disable=SC2086
        docker exec "$CONTAINER" sh -c '
            W="$1"; shift
            mkdir -p /app/data/pylibs || exit 1
            exec pip install --no-cache-dir --no-index \
                --find-links="$W" --target=/app/data/pylibs --upgrade '"$DEPS_FLAG"' "$@"
        ' _ "$IN_WHEELS" $PKGS
    fi
else
    echo "PyPI 源:  $PYPI_MIRROR"
    echo "安装:     $PKGS"
    # shellcheck disable=SC2086
    docker exec "$CONTAINER" sh -c '
        M="$1"; shift
        mkdir -p /app/data/pylibs || exit 1
        exec pip install --no-cache-dir \
            --target=/app/data/pylibs --upgrade '"$DEPS_FLAG"' -i "$M" "$@"
    ' _ "$PYPI_MIRROR" $PKGS
fi

# ── 重启使 PYTHONPATH 生效 ──────────────────────────────────────────
# restart 比 up -d --force-recreate 快，且不会重新拉镜像（pull_policy: never）
# scheduler 是 taskiq 迁移后新增的服务（跑 cron），必须一起重启；
# 老版本 compose 没有它 —— 先探测服务是否存在，避免 compose 抛
# "no such service: scheduler" 的 ERROR 噪音。
cd "$SCRIPT_DIR"
docker compose -f docker-compose.offline.yml restart backend worker
if docker compose -f docker-compose.offline.yml config --services 2>/dev/null | grep -qx scheduler; then
    docker compose -f docker-compose.offline.yml restart scheduler
else
    echo "（compose 里没有 scheduler 服务，跳过）"
fi

echo ""
echo "完成。验证（把 <模块名> 换成实际包名，如 wuwei）："
echo "  sh add-deps.sh --check <模块名>"
echo "  docker exec $CONTAINER python -c 'import <模块名>; print(<模块名>.__file__)'"
echo "  应显示 /app/data/pylibs/... 而不是 /usr/local/lib/python3.13/site-packages/..."
