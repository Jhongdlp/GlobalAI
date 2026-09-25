from sqlalchemy import select, update

from app.api.v1.auth import TERMS_VERSION
from app.core.db import SessionLocal
from app.models import User
from tests.conftest import STUDENT


async def test_login_requires_terms_until_accepted_and_records_version(anon):
    async with SessionLocal() as session, session.begin():
        await session.execute(
            update(User).where(User.email == STUDENT["email"]).values(terms_version=None)
        )
    creds = {"email": STUDENT["email"], "password": STUDENT["password"]}

    response = await anon.post("/auth/login", json=creds)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "terms_required"
    # Contraseña mala: 401 como siempre, sin revelar que la cuenta tiene consentimiento pendiente.
    assert (await anon.post("/auth/login", json=creds | {"password": "x"})).status_code == 401

    assert (await anon.post("/auth/login", json=creds | {"accept_terms": True})).status_code == 200
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == STUDENT["email"]))
    assert user.terms_version == TERMS_VERSION and user.terms_accepted_at
    # Ya aceptada la versión vigente, no se vuelve a exigir.
    assert (await anon.post("/auth/login", json=creds)).status_code == 200
