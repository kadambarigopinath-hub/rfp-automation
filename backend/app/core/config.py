from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    All config comes from environment variables. This is the ONE place that reads
    them — nothing else in the app should call os.getenv() directly. That's what
    makes moving from local Docker to Render (or any other host) a config change,
    not a code change.
    """
    database_url: str
    session_secret: str = "change_me_to_a_long_random_string"

    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket_kb_permanent: str = "kb-permanent"
    s3_bucket_staging: str = "staging"

    anthropic_api_key: str
    claude_model: str = "claude-sonnet-4-6"

    embedding_provider: str = "local"   # "local" or "none" (skips Stage 3 + RAG embedding)
    local_embedding_model: str = "BAAI/bge-large-en-v1.5"
    near_duplicate_simhash_threshold: int = 6   # Hamming distance; lower = stricter match
    near_duplicate_cosine_threshold: float = 0.90

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
