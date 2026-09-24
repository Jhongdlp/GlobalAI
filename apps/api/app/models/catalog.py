from sqlalchemy import SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Level(Base):
    """Nivel MCER (PRE_A1, A1 … C1). Es un dato, no un enum: agregar niveles no requiere migrar."""

    __tablename__ = "levels"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    rank: Mapped[int] = mapped_column(SmallInteger, unique=True)  # orden de dificultad
    description: Mapped[str | None] = mapped_column(String(500))


class Skill(Base):
    """Habilidad evaluada (grammar, vocabulary, reading, listening, speaking)."""

    __tablename__ = "skills"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
