from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["local", "test", "production"] = "local"
    database_url: str = "postgresql+asyncpg://globalai:globalai@localhost:5432/globalai"
    # Pool por proceso: con N réplicas de la API, conexiones totales = N * (size + overflow).
    db_pool_size: int = 10
    db_max_overflow: int = 10
    # True si la URL apunta a un pooler en modo transacción (PgBouncer / Neon "-pooler"):
    # asyncpg debe desactivar su caché de prepared statements.
    db_use_pgbouncer: bool = False

    jwt_secret: str = "change-me-in-production-please-32b"
    jwt_expires_minutes: int = 60 * 8
    cookie_name: str = "gai_session"

    cors_origins: list[str] = ["http://localhost:4321"]

    # Proveedores externos (opcionales: sin key se usan los mocks)
    ai_provider: Literal["openai", "mock"] = "mock"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    tts_provider: Literal["elevenlabs", "none"] = "none"
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str | None = None

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def async_database_url(self) -> tuple[str, bool]:
        """Normaliza la URL para asyncpg.

        Neon/Supabase entregan `postgres://...?sslmode=require`; asyncpg no entiende
        `sslmode`, así que lo quitamos y devolvemos si hay que activar SSL.
        """
        url = self.database_url
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                url = "postgresql+asyncpg://" + url[len(prefix) :]
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query))
        ssl = query.pop("sslmode", None) in {"require", "verify-ca", "verify-full"}
        query.pop("channel_binding", None)
        return urlunsplit(parts._replace(query=urlencode(query))), ssl


@lru_cache
def get_settings() -> Settings:
    return Settings()
