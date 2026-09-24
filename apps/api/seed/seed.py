"""Carga idempotente del catálogo, usuarios demo y evaluaciones.

Uso: uv run python -m seed.seed
Se puede ejecutar varias veces: hace upsert por claves naturales (code, slug, email).
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal, engine
from app.core.security import hash_password
from app.models import (
    Assessment,
    AssessmentQuestion,
    Level,
    Question,
    Skill,
    Stimulus,
    User,
)

DATA_DIR = Path(__file__).parent / "data"


async def upsert(session: AsyncSession, model: type, rows: list[dict[str, Any]], key: str) -> None:
    if not rows:
        return
    stmt = insert(model).values(rows)
    update_cols = {c: stmt.excluded[c] for c in rows[0] if c != key}
    await session.execute(stmt.on_conflict_do_update(index_elements=[key], set_=update_cols))


async def seed_catalog(session: AsyncSession) -> None:
    data = json.loads((DATA_DIR / "catalog.json").read_text())
    await upsert(session, Level, data["levels"], "code")
    await upsert(session, Skill, data["skills"], "code")

    users = [
        {
            "email": u["email"],
            "password_hash": hash_password(u["password"]),
            "full_name": u["full_name"],
            "role": u["role"],
        }
        for u in data["users"]
    ]
    # Usuarios: no pisamos contraseñas existentes.
    await session.execute(
        insert(User).values(users).on_conflict_do_nothing(index_elements=["email"])
    )


async def seed_assessment(session: AsyncSession, path: Path) -> str:
    data = json.loads(path.read_text())

    await upsert(session, Stimulus, data["stimuli"], "code")
    stimulus_ids = dict((await session.execute(select(Stimulus.code, Stimulus.id))).all())

    questions = []
    for q in data["questions"]:
        q = dict(q)
        stimulus_code = q.pop("stimulus_code", None)
        q["stimulus_id"] = stimulus_ids[stimulus_code] if stimulus_code else None
        questions.append(q)
    await upsert(session, Question, questions, "code")

    await upsert(session, Assessment, [data["assessment"]], "slug")
    assessment_id = await session.scalar(
        select(Assessment.id).where(Assessment.slug == data["assessment"]["slug"])
    )
    question_ids = dict(
        (
            await session.execute(
                select(Question.code, Question.id).where(
                    Question.code.in_([q["code"] for q in questions])
                )
            )
        ).all()
    )

    # La composición de la evaluación se reemplaza completa (orden = orden del JSON).
    await session.execute(
        delete(AssessmentQuestion).where(AssessmentQuestion.assessment_id == assessment_id)
    )
    session.add_all(
        AssessmentQuestion(
            assessment_id=assessment_id,
            question_id=question_ids[q["code"]],
            position=i,
            points=1,
        )
        for i, q in enumerate(questions, start=1)
    )
    return data["assessment"]["slug"]


async def main() -> None:
    async with SessionLocal() as session, session.begin():
        await seed_catalog(session)
        for path in sorted(DATA_DIR.glob("*.json")):
            if path.name != "catalog.json":
                slug = await seed_assessment(session, path)
                print(f"✓ assessment {slug}")
    await engine.dispose()
    print("✓ seed completo")


if __name__ == "__main__":
    asyncio.run(main())
