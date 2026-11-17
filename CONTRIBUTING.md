# 参与贡献

欢迎提交问题复现、排盘差异、文档改进和 Pull Request。

1. 按 README 安装开发环境，运行 `uv sync --extra test`。
2. 排盘差异请提供公历/农历、日期、钟表时间、出生地、流派和对照结果。请使用虚构生辰或得到授权的样例。
3. 修改数据导入、排盘、登录或对话逻辑时，添加能复现问题的测试。
4. 提交前执行 `uv run pytest tests -q`。涉及 SQL 时，另在开发数据库执行 `uv run --env-file .env python scripts/verify_sql_schema.py`。
5. 不提交 `.env`、API Key、证书、数据库导出、用户资料或下载的语料。第三方代码和数据请保留来源及许可。

前端使用原生 JavaScript/CSS，无需 Node 构建。上游 TypeScript 文件只供回归测试参考，运行时不依赖 Node。

数据下载或模型 API 的在线检查请手动运行；常规测试不需要付费模型，也不连接生产数据库。
