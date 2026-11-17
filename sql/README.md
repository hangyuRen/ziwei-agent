# SQL 脚本

从仓库根目录使用 `psql` 执行，默认开启遇错停止。数据下载来源、容量与离线缓存见 [docs/DATA.md](../docs/DATA.md)。

| 入口 | 用途 |
| --- | --- |
| `bootstrap.sql` | 一次完成建表与两类数据导入 |
| `init.sql` | 只初始化 / 升级表结构 |
| `import_charts.sql` | 下载校验并导入选定年份 |
| `import_tianji.sql` | 下载校验并导入天纪片段 |
| `schema.sql` | 账号、命盘、会话等基础结构 |
| `tianji_embedding.sql` | pgvector 扩展及天纪存储 |
| `migrations/*.sql` | 按顺序执行的兼容迁移 |

```sh
uv run --env-file .env sh -c 'psql "$DATABASE_URL" -X -f sql/bootstrap.sql'
```

`Repository.schema()` 与 `init.sql` 都在事务内应用结构。Python 入口用于现有维护工具；SQL 入口不要求运行应用。新增迁移时需同时更新 `init.sql`。

## 当前表

| 表 / 视图 | 用途 |
| --- | --- |
| `chart` / `chart_section`（视图） | 命盘解读及 13 主题投影 |
| `auth_user` | 账号、密码哈希和令牌版本 |
| `auth_login_attempt` | 登录审计与限流 |
| `chat_session` | 会话及出生输入快照 |
| `chat_message` | 完整历史、工具消息和 SSE 回放 |
| `session_summary` | 长对话摘要 |
| `saved_chart` | 最近命盘 |
| `user_memory` | 用户显式记忆 |
| `tianji_embedding` | 原文、出处及可延后生成的向量 |
| `import_run` | 可选本地文件导入器的去重记录 |

共 10 张表、1 个视图。SQL 导入器使用事务内临时表，不额外留下 staging 表。

已移除的历史备份工具所用 `source_backup` 不再创建；已有数据库不会被自动删表。建表脚本不含 DROP TABLE，不改动线上用户资料。

运行 `scripts/verify_sql_schema.py` 检查结构升级；`scripts/verify_data_import.py` 验证真实 psql 导入和失败回滚，两者均使用隔离 schema。
