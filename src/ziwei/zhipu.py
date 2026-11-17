"""智谱文本向量与重排接口。"""
import asyncio
import math

import httpx

from .config import Settings


class Zhipu:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(60, connect=15))

    async def close(self):
        await self.client.aclose()

    async def _post(self, url: str, payload: dict):
        if not self.settings.zhipu_api_key:
            raise RuntimeError('ZHIPU_API_KEY is required')
        for attempt in range(3):
            try:
                response = await self.client.post(url, json=payload,
                    headers={'Authorization': f'Bearer {self.settings.zhipu_api_key}'})
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as exc:
                if attempt == 2 or isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500 and exc.response.status_code != 429:
                    raise
                await asyncio.sleep(2 ** attempt)

    async def embed(self, texts: list[str]):
        if not 1 <= len(texts) <= 64 or any(not text.strip() for text in texts):
            raise ValueError('embedding 输入必须为 1 至 64 条非空文本')
        data = await self._post(self.settings.zhipu_embedding_url, {
            'model': self.settings.zhipu_embedding_model, 'input': texts,
            'dimensions': self.settings.zhipu_embedding_dimensions})
        rows = data['data']
        if len(rows) != len(texts) or {row['index'] for row in rows} != set(range(len(texts))):
            raise ValueError('embedding 返回的索引不完整')
        vectors = [row['embedding'] for row in sorted(rows, key=lambda row: row['index'])]
        if any(len(vector) != self.settings.zhipu_embedding_dimensions or
               any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in vector)
               for vector in vectors):
            raise ValueError('embedding 返回的向量维度或数值无效')
        return vectors

    async def rerank(self, query: str, documents: list[str], top_n: int):
        if not documents:
            return []
        data = await self._post(self.settings.zhipu_rerank_url, {
            'model': self.settings.zhipu_rerank_model, 'query': query,
            'documents': documents, 'top_n': min(top_n, len(documents))})
        results = data['results']
        indexes = [row['index'] for row in results]
        if len(indexes) != len(set(indexes)) or any(type(index) is not int or
                not 0 <= index < len(documents) for index in indexes):
            raise ValueError('rerank 返回的索引无效')
        if any(not isinstance(row.get('relevance_score'), (int, float)) or
                not math.isfinite(row['relevance_score']) for row in results):
            raise ValueError('rerank 返回的分数无效')
        return sorted(results, key=lambda row: row['relevance_score'], reverse=True)
