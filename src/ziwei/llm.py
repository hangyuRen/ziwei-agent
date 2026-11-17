import asyncio
import json

import httpx

from .config import Settings


class LLM:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(90, connect=15))

    async def close(self):
        await self.client.aclose()

    async def stream_answer(self, messages):
        """Stream the provider's reasoning/content deltas; never simulate typing."""
        if not self.settings.llm_api_key or not self.settings.llm_model:
            raise RuntimeError('LLM_API_KEY and LLM_MODEL are required for chat')
        messages = [*messages, {'role':'system','content':'本轮工具检索已经完成。现在只生成最终自然语言回答，不再调用工具，也不输出工具调用协议。使用已有资料支持论述时，按[天纪#数字编号]引用提供的真实片段。'}]
        payload = {'model': self.settings.llm_model, 'messages': messages, 'stream': True, 'tool_choice':'none'}
        if self.settings.llm_model.startswith('deepseek-'):
            payload['thinking'] = {'type': 'enabled'}
            # Earlier tool planning ran with thinking disabled. An explicit empty
            # field represents that fact; DeepSeek rejects omitted fields on calls.
            payload['messages'] = [dict(message, reasoning_content=message.get('reasoning_content', ''))
                                   if message['role'] == 'assistant' else message for message in messages]
        finished = False
        async with self.client.stream('POST', f"{self.settings.llm_base_url.rstrip('/')}/chat/completions",
                json=payload, headers={'Authorization': f'Bearer {self.settings.llm_api_key}'}) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith('data:'):
                    continue
                raw = line[5:].strip()
                if raw == '[DONE]':
                    break
                event = json.loads(raw)
                if event.get('error'):
                    raise RuntimeError('模型流式接口返回错误')
                for choice in event.get('choices', []):
                    delta = choice.get('delta') or {}
                    for field, kind in [('reasoning_content', 'reasoning_delta'), ('content', 'answer_delta')]:
                        if delta.get(field):
                            yield kind, delta[field]
                    reason = choice.get('finish_reason')
                    if reason and reason != 'stop':
                        raise RuntimeError(f'模型回答未正常完成：{reason}')
                    finished |= reason == 'stop'
        if not finished:
            raise RuntimeError('模型流式连接提前中断，请重试')

    async def chat(self, messages: list[dict], tools: list[dict] | None = None, json_mode: bool = False):
        if not self.settings.llm_api_key or not self.settings.llm_model:
            raise RuntimeError("LLM_API_KEY and LLM_MODEL are required for chat")
        payload = {"model": self.settings.llm_model, "messages": messages, "temperature": 0.2}
        if self.settings.llm_model.startswith('deepseek-'):
            payload['thinking'] = {'type': 'disabled'}
        if tools:
            payload['tools'] = tools
            payload['tool_choice'] = 'auto'
        if json_mode:
            payload['response_format'] = {"type": "json_object"}
        for attempt in range(3):
            try:
                r = await self.client.post(f"{self.settings.llm_base_url.rstrip('/')}/chat/completions", json=payload,
                                           headers={"Authorization": f"Bearer {self.settings.llm_api_key}"})
                if r.status_code == 429 or r.status_code >= 500:
                    r.raise_for_status()
                r.raise_for_status()
                return r.json()['choices'][0]['message']
            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as exc:
                if attempt == 2 or isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500 and exc.response.status_code != 429:
                    raise
                await asyncio.sleep(2 ** attempt)
