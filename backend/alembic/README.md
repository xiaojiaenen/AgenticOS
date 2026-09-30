# Alembic 迁移工作流

自 TECH-DEBT-2026-09 起，backend 的 schema 演进由 alembic 管理，替代原
`app/db/session.py::_ensure_compatible_schema()` 的手写 ALTER TABLE 补列。

## 目录结构

```
backend/
├── alembic.ini                  # 配置；sqlalchemy.url 留空 → env.py 从 settings 读 DATABASE_URL
└── alembic/
    ├── env.py                   # 接 app.db.session.engine 与 app.db.models.Base.metadata
    ├── script.py.mako
    ├── README.md
    └── versions/
        ├── baseline_20260930.py     # 空基线（head 起点，不执行 DDL）
        └── 0002_mysql_longtext.py   # MySQL 大文本列拉长为 LONGTEXT（原 compat 行为固化）
```

## 日常工作流（改 models 之后）

```bash
cd backend
# 1. 修改 app/db/models.py
uv run alembic revision --autogenerate -m "add xxx column"
# 2. 人工 review 生成的 versions/*.py（autogenerate 不感知部分服务端默认值/索引改名）
# 3. 本地验证
uv run alembic upgrade head
# 4. 提交迁移文件
```

生产部署：**先 migrate 后起新容器** —— 在发布流水线中先执行
`alembic upgrade head`，再滚动更新应用容器。

## 基线对齐（一次性）

- **存量库**（此前由 create_all + 历史 compat 层建好结构）：
  `alembic stamp head` —— 仅写 alembic_version 标记，不执行 DDL。
- **新库 / 开发 SQLite**：应用启动时 `init_db()` 的 create_all 建全量
  schema，开发环境不强制走迁移，随后 `alembic stamp head` 对齐即可。
- **新库 / 生产 MySQL**：启动一次让 create_all 建表后，执行
  `alembic upgrade head`（**不要 stamp**）—— `0002_mysql_longtext` 会把
  `agent_messages.message_json`、`ppt_artifacts.deck_json/preview_html`
  从 TEXT 拉长为 LONGTEXT（模型 Text 列在 MySQL 上默认 64KB 上限，
  工具返回与 SVG deck 可能远超此限）。

> 风险提示：若新 MySQL 库直接 `stamp head`，0002 会被标记为已应用而
> 实际未执行，大文本列停留在 TEXT(64KB)，超大工具结果/ decks 写入会
> 截断或报错。生产 MySQL 一律走 `upgrade head`。

## 命令速查

| 命令 | 用途 |
|------|------|
| `uv run alembic upgrade head` | 应用全部迁移 |
| `uv run alembic stamp head` | 仅对齐版本标记（存量库基线） |
| `uv run alembic current` | 查看当前版本 |
| `uv run alembic history -v` | 查看迁移历史 |
| `uv run alembic downgrade -1` | 回退一步（谨慎；0002 无 downgrade DDL） |
