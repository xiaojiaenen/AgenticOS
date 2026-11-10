#!/bin/sh
# 内网容器线程/进程上限诊断：在目标机上执行
# 用法：sudo sh diagnose-threads.sh
set -e

echo "===== 1. 宿主机线程与进程 ====="
echo "当前系统线程总数：$(ps -eLf 2>/dev/null | wc -l)"
echo "threads-max  ：$(cat /proc/sys/kernel/threads-max 2>/dev/null)"
echo "pid_max       ：$(cat /proc/sys/kernel/pid_max 2>/dev/null)"
echo "当前已分配 pid：$(ls /proc | grep -E '^[0-9]+$' | wc -l)"
echo "vm.max_map_count：$(cat /proc/sys/vm/max_map_count 2>/dev/null)"

echo
echo "===== 2. 内存与 overcommit ====="
free -m 2>/dev/null | head -3
echo "overcommit_memory：$(cat /proc/sys/vm/overcommit_memory 2>/dev/null)"

echo
echo "===== 3. 各容器进程/线程数 ====="
for c in $(docker ps -a --format '{{.Names}}'); do
    pid=$(docker inspect -f '{{.State.Pid}}' "$c" 2>/dev/null || echo 0)
    if [ "$pid" != "0" ] && [ -d "/proc/$pid" ]; then
        n=$(ls /proc/$pid/task 2>/dev/null | wc -l)
        echo "  $c (pid $pid) 线程数=$n  状态=$(docker inspect -f '{{.State.Status}}' "$c")"
    else
        echo "  $c 未运行  状态=$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null)"
    fi
done

echo
echo "===== 4. 容器内 ulimit（以 backend 为例）====="
docker exec agenticos-backend-1 sh -c 'echo "nproc(进程/线程): $(ulimit -u)"; echo "nofile: $(ulimit -n)"; echo "threads-max: $(cat /proc/sys/kernel/threads-max)"; echo "容器内线程数: $(ls /proc/1/task | wc -l)"' 2>/dev/null || echo "  backend 未运行，跳过"

echo
echo "===== 5. backend 日志尾部 ====="
docker logs --tail 40 agenticos-backend-1 2>&1 | tail -40 || true

echo
echo "===== 6. healthcheck 实测 ====="
docker inspect -f '{{json .State.Health}}' agenticos-backend-1 2>/dev/null || echo "  无 healthcheck 信息"
