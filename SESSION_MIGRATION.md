# 会话迁移指南

## 快速入口

```bash
cd backend

# 1. 查看可用会话
uv run python scripts/migrate_session.py list

# 2. 导出指定会话到文件
uv run python scripts/migrate_session.py export <session_id> ./my_session.json

# 3. 查看目标机器上的用户
uv run python scripts/migrate_session.py list --users

# 4. 在目标机器上导入
# 将 my_session.json 复制到目标机器后：
uv run python scripts/migrate_session.py import ./my_session.json --target-user-id 1
```

---

## 方案 A：Python 迁移脚本（推荐 — 自动处理外键映射）

全功能脚本位于 `backend/scripts/migrate_session.py`，支持：
- `list` — 列出所有会话（含 ID、摘要、时间）
- `list --users` — 列出所有用户（查看 `target-user-id`）
- `export <id> [文件]` — 导出会话 + 消息 + 用量统计 + PPT 制品 → JSON
- `import <文件> --target-user-id <ID>` — 导入到目标数据库，自动映射 `user_id`，适配不存在的 `agent_profile_id`

跨数据库兼容：导出的 JSON 在 SQLite 和 MySQL 之间可互换使用。

---

## 方案 B：sqlite3 CLI（不处理外键映射，需手动编辑）

如果只用 SQLite，且目标机器上用户 ID 一致，可以直接用 SQL：

### 源机器：导出

```bash
cd backend

# 1. 查出要导出的 session_id
sqlite3 data/agenticos.db "SELECT session_id, substr(summary,1,40), created_at FROM agent_sessions;"

# 2. 导出会话元信息（注意替换 YOUR_SESSION_ID）
sqlite3 data/agenticos.db \
  ".mode insert agent_sessions" \
  "SELECT * FROM agent_sessions WHERE session_id = 'YOUR_SESSION_ID';" \
  > session_meta.sql

# 3. 导出消息
sqlite3 data/agenticos.db \
  ".mode insert agent_messages" \
  "SELECT * FROM agent_messages WHERE session_id = 'YOUR_SESSION_ID';" \
  > session_messages.sql

# 4. 导出用量事件
sqlite3 data/agenticos.db \
  ".mode insert agent_usage_events" \
  "SELECT * FROM agent_usage_events WHERE session_id = 'YOUR_SESSION_ID';" \
  > session_usage.sql

# 5. 合并
cat session_meta.sql session_messages.sql session_usage.sql > session_export.sql

# 6. 检查并手动编辑 user_id/agent_profile_id（如需）
# 用文本编辑器打开 session_export.sql，找到 INSERT INTO agent_sessions...
# 把 user_id 改为目标机器的用户 ID
```

### 目标机器：导入

```bash
cd backend

# 先备份原数据库
cp data/agenticos.db data/agenticos.db.bak

# 导入
sqlite3 data/agenticos.db < session_export.sql

# 验证
sqlite3 data/agenticos.db "SELECT count(*) FROM agent_messages WHERE session_id = 'YOUR_SESSION_ID';"
```

> **⚠️ 注意**：sqlite3 方式如果目标机器上 `user_id` 对应的用户不存在，会因外键约束失败。可以在目标机器先创建同名用户，再执行 `PRAGMA foreign_keys = OFF;` 临时绕过。

---

## 方案 C：直接用 Python 读 JSON 命令行

```bash
cd backend
uv run python -c "
import json
# 从标准输入读 session_id
sid = input('Session ID: ')
from scripts.migrate_session import export_session
export_session(sid, Path(f'./{sid[:8]}.json'))
"
```
