# 验证方式

## 日常测试

```sh
uv sync --extra test
uv run pytest tests -q
```

覆盖排盘参考结果、国内区划、时间校正、四化、对话摘要和证据策略，以及下载器校验。无需数据库和模型 API。

`tests/fixtures/` 中是算法回归结果，不是从业务数据库导出的命盘解读。`tests/upstream_reference/` 保留用于对照的上游代码及 MIT 声明，不参与生产运行。

## SQL 集成

在配置好的开发库运行：

```sh
uv run --env-file .env python scripts/verify_sql_schema.py
uv run --env-file .env python scripts/verify_data_import.py
```

使用随机独立 schema，并清理或回滚；不向 public 业务表写入数据。数据导入检查需要 psql / uv，并使用合成命盘与合成语料验证事务、幂等及向量复用。

## 浏览器与在线模型

浏览器脚本需另装 Playwright，例如：

```sh
uv run --with playwright==1.48.0 playwright install chromium
uv run --env-file .env --with playwright==1.48.0 python scripts/verify_workspace_ui.py
```

部分浏览器脚本创建临时账号并在结束时清理。请先检查脚本使用的本地 URL，开发环境需运行应用。`verify_live_chat.py`、`verify_answer_policy.py`、`verify_streaming.py`、`verify_tianji_live.py`、`verify_tianji_chat.py` 等会实际调用模型，产生费用；不放入默认 CI。

## 发布包

```sh
uv run python scripts/package_source.py --output /tmp/ziwei-agent-source.tar.gz
```

发布工具使用允许清单打包，排除本地环境、凭据、证书、业务数据和缓存。仓库没有可读 Git 历史时，不能据此判断历史提交是否含密钥；将来推送已有历史仍需另行审查。
