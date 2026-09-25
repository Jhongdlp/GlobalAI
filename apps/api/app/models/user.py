from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPk, str_enum


class Role(StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[Role] = mapped_column(str_enum(Role), default=Role.STUDENT)
    is_active: Mapped[bool] = mapped_column(default=True)
    # Consentimiento: qué versión de Términos/Privacidad aceptó y cuándo (prueba ante un reclamo).
    terms_version: Mapped[str | None] = mapped_column(String(16))
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
