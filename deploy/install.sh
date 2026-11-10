#!/bin/sh
# 内网部署机一键导入脚本（随离线包分发）
#
# 用法（解包后在包的根目录执行）：
#   sudo sh install.sh /opt/agenticos
#
# 前置：Docker 已安装并运行；外部 MySQL/Redis 已就绪。
set -e

TARGET=${1:-/opt/agenticos}
HERE=$(cd "$(dirname "$0")" && pwd)

echo "== AgenticOS 内网离线安装 =="
echo "目标目录: $TARGET"

command -v docker >/dev/null 2>&1 || { echo "错误：未找到 docker，请先安装"; exit 1; }

echo "[1/5] 校验包完整性"
if [ -f "$HERE/MANIFEST.sha256" ]; then
    (cd "$HERE" && sha256sum -c MANIFEST.sha256 --quiet) && echo "  校验通过" || {
        echo "  警告：部分文件校验失败（可能是传输损坏，请重传）"; exit 1; }
else
    echo "  跳过（无清单）"
fi

echo "[2/5] 导入镜像"
loaded=0
for f in "$HERE"/images/*.tar "$HERE"/images/*.tar.gz; do
    [ -f "$f" ] || continue
    echo "  loading $(basename "$f")"
    case "$f" in
        *.tar.gz) gunzip -c "$f" | docker load ;;
        *.tar)    docker load -i "$f" ;;
    esac
    loaded=$((loaded + 1))
done

# 内网没有外网出口，镜像必须来自包内。这里立刻检查，别等 compose up 时
# 才报 `lookup registry-1.docker.io ... server misbehaving` —— 那个报错
# 看着像网络问题，实际是镜像没导进来。
if [ "$loaded" -eq 0 ]; then
    echo "  错误：images/ 下没有找到任何镜像包"
    echo "  离线包必须包含 images/agenticos-runtime.tar 与 images/nginx.tar"
    exit 1
fi

for img in agenticos-runtime:latest nginx:1.27-alpine; do
    if docker image inspect "$img" >/dev/null 2>&1; then
        echo "  已就绪：$img"
    else
        echo "  警告：缺少镜像 $img"
        echo "       若包内没有对应 tar，请单独导出后 docker load："
        echo "       docker save $img -o $img.tar"
        missing=1
    fi
done
if [ "${missing:-0}" = "1" ]; then
    echo "  错误：镜像不全，已中止。补齐后再运行本脚本。"
    exit 1
fi

echo "[3/5] 安装文件到 $TARGET"
mkdir -p "$TARGET"
for d in backend frontend data deploy; do
    [ -d "$HERE/$d" ] || continue
    if [ -d "$TARGET/$d" ]; then
        echo "  $d 已存在 → 备份为 $d.bak.$(date +%s)"
        mv "$TARGET/$d" "$TARGET/$d.bak.$(date +%s)"
    fi
    cp -a "$HERE/$d" "$TARGET/$d"
done

echo "[4/5] 初始化配置"
cd "$TARGET/deploy"
if [ ! -f .env ]; then
    cp .env.offline.example .env
    echo "  已生成 .env —— 请编辑填写 DATABASE_URL / REDIS_URL / AUTH_SECRET_KEY"
    echo "  参考: vi $TARGET/deploy/.env"
else
    echo "  .env 已存在，保持不变"
fi

echo "[4.5/5] 同步依赖（按 pyproject.toml）"
# 启动一次容器，让 sync-deps 能在容器里比对已装版本。
# 首次安装时容器还没起，依赖会以 --all 全量装进 /app/data/pylibs。
if [ -f sync-deps.sh ]; then
    echo "  启动容器以比对依赖..."
    docker compose -f docker-compose.offline.yml up -d 2>/dev/null || true
    sleep 8
    if sh sync-deps.sh --dry-run >/dev/null 2>&1; then
        sh sync-deps.sh || echo "  警告：依赖同步失败，可稍后手动执行 sh sync-deps.sh"
    else
        echo "  容器未就绪，跳过（部署完成后执行 sh sync-deps.sh 补齐）"
    fi
else
    echo "  跳过（无 sync-deps.sh）"
fi

echo "[5/5] 完成"
cat <<EOF

下一步：
  1) 编辑配置：vi $TARGET/deploy/.env
  2) 启动：cd $TARGET/deploy && docker compose -f docker-compose.offline.yml up -d
  3) 验证：curl http://127.0.0.1:10007/api/v1/health/
  4) 浏览器打开 http://<本机IP>:10008 完成首次管理员注册

详细说明见 $TARGET/deploy/OFFLINE-DEPLOY.md
EOF
