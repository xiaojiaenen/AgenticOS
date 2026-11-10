#!/bin/sh
# LDAP 连通性诊断：在部署机（宿主机）上执行
# 用法：sudo sh diagnose-ldap.sh 172.73.1.6 389
HOST=${1:-172.73.1.6}
PORT=${2:-389}

echo "===== 1. 宿主机到 LDAP 的 TCP 连通性 ====="
if command -v nc >/dev/null 2>&1; then
    nc -zv -w 5 "$HOST" "$PORT" 2>&1
elif command -v timeout >/dev/null 2>&1; then
    timeout 5 bash -c "</dev/tcp/$HOST/$PORT" 2>&1 && echo "  TCP 可达" || echo "  TCP 不可达"
else
    echo "  无 nc，跳过"
fi

echo
echo "===== 2. 路由与 ping ====="
ping -c 3 -W 2 "$HOST" 2>&1 | tail -4

echo
echo "===== 3. 从 backend 容器内测（关键：容器网络可能与宿主不同）====="
docker exec agenticos-backend-1 sh -c "
  timeout 5 bash -c '</dev/tcp/$HOST/$PORT' 2>/dev/null && echo '  容器内 TCP 可达' || echo '  容器内 TCP 不可达'
" 2>/dev/null || echo "  容器未运行，跳过"

echo
echo "===== 4. 容器 DNS 解析 ====="
docker exec agenticos-backend-1 getent hosts "$HOST" 2>/dev/null || echo "  （IP 直连无需 DNS）"

echo
echo "===== 5. 用 python ldap3 实测（与后端同一套逻辑）====="
docker exec agenticos-backend-1 python -c "
from ldap3 import Server, Connection
import traceback
try:
    s = Server('ldap://$HOST:$PORT', connect_timeout=10)
    c = Connection(s, auto_bind=False, receive_timeout=15)
    print('  open:', c.open())
except Exception as e:
    print('  异常:', type(e).__name__, e)
    traceback.print_exc()
" 2>&1 | tail -20

echo
echo "===== 6. backend 日志里的 LDAP 记录 ====="
docker compose -f docker-compose.offline.yml logs --tail 60 backend 2>/dev/null | grep -iE "ldap" | tail -20
