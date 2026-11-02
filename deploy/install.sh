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
for f in "$HERE"/images/*.tar.gz; do
    [ -f "$f" ] || continue
    echo "  loading $(basename "$f")"
    gunzip -c "$f" | docker load
done

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

echo "[5/5] 完成"
cat <<EOF

下一步：
  1) 编辑配置：vi $TARGET/deploy/.env
  2) 启动：cd $TARGET/deploy && docker compose -f docker-compose.offline.yml up -d
  3) 验证：curl http://127.0.0.1:10007/api/v1/health/
  4) 浏览器打开 http://<本机IP>:10008 完成首次管理员注册

详细说明见 $TARGET/deploy/OFFLINE-DEPLOY.md
EOF
