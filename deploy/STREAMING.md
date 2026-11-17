# AI 对话流式输出

最终回答使用 DeepSeek Chat Completions 的 `stream=true` 和思考模式。
工具规划、检索改写和会话标题仍使用非思考模式；最终回答阶段不再调用工具。
历史工具调用补齐空的 `reasoning_content` 字段，已有思考内容随历史保存。

模型的 `reasoning_content` / `content` 增量分别映射为 SSE 的
`reasoning_delta` / `answer_delta`。增量按约 150ms 或 512 字符批次保存到
PostgreSQL 的 chat_message（kind=stream），事件 ID 复用会话 seq 支持重放。
流式记录不参与上下文与摘要；完整回答、核验后的引用和思考内容保存在 final 消息中。

前端思考面板默认展开，首次正文增量到达时折叠，历史面板默认折叠。
没有返回思考内容的模型直接显示正文，不生成虚假的思考文本。
导航接口 timeline 仅查询用户消息，点击刻度仍定位原用户消息。

验证：加载服务器 .env 后运行 `.venv/bin/python scripts/verify_streaming.py`。
脚本通过本机 Nginx 发起两轮真实模型请求，检查增量事件顺序、历史、导航、
SSE 断点重放，并自动删除临时账号。该脚本会使用已配置的模型 API 配额。
