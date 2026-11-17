import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "")
    elasticsearch_url: str = os.getenv("ELASTICSEARCH_URL", "")
    elasticsearch_api_key: str = os.getenv("ELASTICSEARCH_API_KEY", "")
    elasticsearch_user: str = os.getenv("ELASTICSEARCH_USER", "")
    elasticsearch_password: str = os.getenv("ELASTICSEARCH_PASSWORD", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "")
    zhipu_api_key: str = os.getenv("ZHIPU_API_KEY", "")
    zhipu_embedding_url: str = os.getenv("ZHIPU_EMBEDDING_URL", "https://open.bigmodel.cn/api/paas/v4/embeddings")
    zhipu_embedding_model: str = os.getenv("ZHIPU_EMBEDDING_MODEL", "embedding-3")
    zhipu_embedding_dimensions: int = int(os.getenv("ZHIPU_EMBEDDING_DIMENSIONS", "1024"))
    zhipu_rerank_url: str = os.getenv("ZHIPU_RERANK_URL", "https://open.bigmodel.cn/api/paas/v4/rerank")
    zhipu_rerank_model: str = os.getenv("ZHIPU_RERANK_MODEL", "rerank")
    api_token: str = os.getenv("API_TOKEN", "")
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    jwt_issuer: str = os.getenv("JWT_ISSUER", "ziwei-agent")
    jwt_audience: str = os.getenv("JWT_AUDIENCE", "ziwei-web")
    prompt_token_budget: int = int(os.getenv("PROMPT_TOKEN_BUDGET", "24000"))
    summary_trigger_ratio: float = float(os.getenv("SUMMARY_TRIGGER_RATIO", "0.8"))
