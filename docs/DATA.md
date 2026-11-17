# 数据下载与导入

仓库不分发命盘解读、《天纪》语料、模型向量或用户数据库。下载器仅访问下列公开地址，不连接项目作者的数据库。

## 固定来源

| 数据 | 固定版本 / 下载地址 | 校验 |
| --- | --- | --- |
| 命盘解读 | [v4.0-13d Release](https://github.com/Renhuai123/ziwei-doushu/releases/tag/v4.0-13d)，按年 `year-YYYY.jsonl.zst` | 每个分片对照 SHA256SUMS |
| 校验清单 | [SHA256SUMS.txt](https://github.com/Renhuai123/ziwei-doushu/releases/download/v4.0-13d/SHA256SUMS.txt) | 清单自身 SHA-256 固定在下载器中 |
| 天纪语料 | [entries.jsonl](https://raw.githubusercontent.com/Renhuai123/nihai-tianji-corpus/462faa4c70af40b8b87ad82ffa82a5823a485e94/data/entries.jsonl)，提交 `462faa4c70af40b8b87ad82ffa82a5823a485e94` | 固定 SHA-256 |

命盘清单：`897b532dd13df7c2dc118701277400c33c8b521effbe7f3e2e30eb7030bd3d19`。

天纪文件：`f6c49b98084fab7a2d44482dc6fd8ce43b518a439dfcfeba3b2d480d582c8aae`。

命盘上游全量为 1950–2026 年，本应用只接受 2000–2026 年。不要将 v3 样本文件与此导入器混用。

## SQL 入口

先按 README 安装依赖并创建 `.env`，在仓库根目录运行：

```sh
uv run --env-file .env sh -c 'psql "$DATABASE_URL" -X -f sql/bootstrap.sql'
```

这是 **psql 脚本**。它通过客户端 `\copy FROM PROGRAM` 调用 Python 下载器；普通服务端 SQL 不具备 HTTP 下载及 zstd 解压能力。因此客户端需要 `uv`、Python、`psql`、`zstd` 和外网访问，无需数据库服务器安装 Python，也无需授予服务端执行程序权限。

脚本顺序：

1. `init.sql`：建表与兼容迁移。
2. `import_charts.sql`：流式解压、验证日期 / 主键 / 13 主题 / 全年条数，导入命盘。
3. `import_tianji.sql`：验证原始记录，按章节切为至多 500 字、重叠 20 字的片段，保留视频与时间定位。

每一阶段独立事务。命盘阶段成功后，若天纪失败，已完成的命盘会保留；失败阶段不落入半批数据。重复执行可恢复。不会删除账号、会话、记忆或不在本次输入内的命盘。

下载先写临时文件，校验成功后才进入缓存。已损坏的缓存会重新下载；上游变化不会被默默接受，需要显式更新固定版本与校验值。

### 选择年份与离线缓存

```sh
ZIWEI_CHART_YEARS=2000,2001,2026 uv run --env-file .env sh -c 'psql "$DATABASE_URL" -X -f sql/bootstrap.sql'
```

默认范围为 `2000-2026`。完整范围的文本为数十 GB；数据库还需要临时导入表、索引和 WAL 空间，建议先单年验证并按容量扩展。

可自行从上表下载压缩分片、校验清单和 `entries.jsonl`，放入 `data/upstream/`。文件名保持不变；文件均通过校验后可完全离线导入。也可用 `ZIWEI_DATA_DIR` 指定缓存目录。

### 只建表或只导入一种数据

```sh
uv run --env-file .env sh -c 'psql "$DATABASE_URL" -X -f sql/init.sql'
uv run --env-file .env sh -c 'psql "$DATABASE_URL" -X -f sql/import_charts.sql'
uv run --env-file .env sh -c 'psql "$DATABASE_URL" -X -f sql/import_tianji.sql'
```

`CREATE EXTENSION vector` 需要相应数据库权限，托管数据库可请管理员预先安装。其余导入使用普通建表、写表权限。

## 向量与关键词索引

原文导入不调用模型。新片段的向量为 NULL；不会写入假向量。相同内容再次导入时保留已生成向量。

```sh
uv run --env-file .env python -m ziwei.embedding_index
uv run --env-file .env ziwei-index
```

向量命令仅处理缺失、模型变化或内容变化的记录，使用智谱 `embedding-3` 的 1024 维输出。API Key 和调用费用由部署者承担。关键词索引可从 PG 重建，数据库为空时不会凭空补出资料。

应用启动时从 PG 片段构建真实目录，导入后重启应用即可更新；无需提交生成的原文目录文件。

## 数据许可

- [命盘 DATASET-LICENSE](https://github.com/Renhuai123/ziwei-doushu/blob/main/DATASET-LICENSE)：主体 CC BY 4.0，保留“来源 Renhuai123/ziwei-doushu，作者王多鱼AI”的署名；其中《天纪》引文有独立许可。
- [天纪 LICENSE.md](https://github.com/Renhuai123/nihai-tianji-corpus/blob/main/LICENSE.md)：语料为 CC BY-NC-SA 4.0，原课程权利归倪海厦先生及其权利继承人。
- 国内行政区划与坐标的来源单独记录在 `src/ziwei/data/README.md`。

本项目 MIT 许可只覆盖相应代码，不重新授权外部数据。
