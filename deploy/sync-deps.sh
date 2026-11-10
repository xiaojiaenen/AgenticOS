#!/bin/sh
# 依赖自动同步 —— 按 pyproject.toml 补齐容器里缺失/不满足的依赖
#
# 用法（在 /opt/agenticos/deploy 下）：
#   sh sync-deps.sh              # 对比 pyproject 与容器实际，只装差异
#   sh sync-deps.sh --dry-run    # 只打印差异，不安装
#   sh sync-deps.sh --all        # 忽略对比，全量重装一遍
#
# 原理：
#   1. 从包内 backend/pyproject.toml 读出 [project].dependencies；
#   2. 把这份列表**通过 stdin** 送进 backend 容器（rootfs 只读，不能 docker cp），
#      用容器自带的 packaging 库逐条判断「已装版本是否满足声明」；
#   3. 只把不满足的包交给 add-deps.sh 安装，最后重启 backend / worker / scheduler。
#
# 为什么在容器里判断而不是在宿主机：
#   依赖装在 /app/data/pylibs，真实运行时用的是那里的版本；宿主机上没有
#   packaging 也不一定对得上。用同一个 Python 解释器判断最准。
#
# 环境变量（与 add-deps.sh 共用）：
#   PYPI_MIRROR  PyPI 源；留空则从 .env 的 PYPI_MIRROR 读
#   CONTAINER    容器名，默认 agenticos-backend-1
set -e

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
CONTAINER=${CONTAINER:-agenticos-backend-1}
TARGET_ROOT=${TARGET_ROOT:-"$SCRIPT_DIR/.."}
PYPROJECT="$TARGET_ROOT/backend/pyproject.toml"

DRY_RUN=""
FORCE_ALL=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN="1" ;;
        --all)     FORCE_ALL="1" ;;
        -h|--help)
            sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "未知参数: $arg" >&2; exit 1 ;;
    esac
done

# ── PyPI 源：优先环境变量，其次 .env ────────────────────────────────
if [ -z "${PYPI_MIRROR:-}" ] && [ -f "$SCRIPT_DIR/.env" ]; then
    PYPI_MIRROR=$(grep -E '^PYPI_MIRROR=' "$SCRIPT_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"'"'"'')
fi
PYPI_MIRROR=${PYPI_MIRROR:-http://pypi.local/simple}
export PYPI_MIRROR

[ -f "$PYPROJECT" ] || { echo "错误：找不到 $PYPROJECT" >&2; exit 1; }

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "错误：容器 $CONTAINER 未运行。当前容器：" >&2
    docker ps --format '  {{.Names}}' >&2
    exit 1
fi

echo "== 依赖同步 =="
echo "清单:     $PYPROJECT"
echo "容器:     $CONTAINER"
echo "PyPI 源:  $PYPI_MIRROR"
[ -n "$FORCE_ALL" ] && echo "模式:     全量重装（--all）"
[ -n "$DRY_RUN" ]  && echo "模式:     仅检查（--dry-run）"

# ── 在容器里做比对，只输出「需要安装」的包名（一行一个）────────────
# 通过 stdin 把**脚本本身**送进容器：rootfs 只读，docker cp 不可用。
# pyproject 走路径参数—— /app/backend 是挂载卷，容器内能直接读，
# 这样 stdin 只承载脚本，不会和 heredoc 打架（踩过：两个都走 stdin 时
# Python 把 toml 当脚本体，报 SyntaxError）。
CONTAINER_PYPROJECT="/app/backend/pyproject.toml"

MISSING=$(
    docker exec -i "$CONTAINER" python - "$FORCE_ALL" "$CONTAINER_PYPROJECT" 2>/dev/null <<'PYEOF'
import sys
import tomllib

force_all = bool(sys.argv[1] if len(sys.argv) > 1 else "")
pyproject_path = sys.argv[2] if len(sys.argv) > 2 else "/app/backend/pyproject.toml"

with open(pyproject_path, "rb") as fh:
    deps = tomllib.load(fh)["project"]["dependencies"]

try:
    from packaging.requirements import Requirement
    from packaging.version import Version, InvalidVersion
    import importlib.metadata as md
except Exception:  # pragma: no cover
    for d in deps:
        print(d)
    sys.exit(0)


def installed_version(dist_name: str):
    try:
        return Version(md.version(dist_name))
    except (md.PackageNotFoundError, InvalidVersion):
        return None


for spec in deps:
    if force_all:
        print(spec)
        continue
    try:
        req = Requirement(spec)
    except Exception:
        print(spec)
        continue
    cur = installed_version(req.name)
    if cur is None or not req.specifier.contains(cur, prereleases=True):
        print(spec)
PYEOF
)

if [ -z "$(echo "$MISSING" | tr -d '[:space:]')" ]; then
    echo ""
    echo "✔ 全部依赖已满足，无需安装。"
    exit 0
fi

COUNT=$(echo "$MISSING" | grep -c . || true)
echo ""
echo "需要安装 $COUNT 项："
echo "$MISSING" | sed 's/^/  - /'

if [ -n "$DRY_RUN" ]; then
    echo ""
    echo "（--dry-run：未实际安装）"
    exit 0
fi

echo ""
echo "开始安装..."
# shellcheck disable=SC2086
sh "$SCRIPT_DIR/add-deps.sh" $MISSING

echo ""
echo "✔ 依赖同步完成。"
echo "  查看版本：sh add-deps.sh --check <模块名>"
