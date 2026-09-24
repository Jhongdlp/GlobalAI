# Global AI — Mini English Assessment

Prototipo funcional de un módulo de evaluación de inglés para Global AI.

> README completo en construcción. Estructura:
>
> - `apps/api` — FastAPI + SQLAlchemy + PostgreSQL
> - `apps/web` — Astro (frontend)
> - `docs/` — decisiones técnicas

## Arranque rápido (API)

```bash
cd apps/api
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run python -m seed.seed
uv run uvicorn app.main:app --reload
# Swagger: http://localhost:8000/docs
```

O con Docker: `docker compose up --build`.

Credenciales demo: `estudiante@globalai.demo` / `Demo1234!`
