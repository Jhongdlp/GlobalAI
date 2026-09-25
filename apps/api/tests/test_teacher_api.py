from datetime import UTC, datetime

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import User
from tests.conftest import STUDENT
from tests.test_attempts_api import start


async def _submit_with_events(student, kinds: list[str]) -> dict:
    """Envía un intento en blanco (0 %) tras registrar eventos de integridad."""
    attempt = await start(student)
    now = datetime.now(UTC).isoformat()
    events = [{"type": k, "occurred_at": now} for k in kinds]
    await student.post(f"/attempts/{attempt['id']}/events", json={"events": events})
    await student.post(f"/attempts/{attempt['id']}/submit", json={"answers": {}})
    return attempt


async def test_all_teacher_routes_reject_students(student):
    attempt = await _submit_with_events(student, [])
    async with SessionLocal() as session:
        student_id = await session.scalar(select(User.id).where(User.email == STUDENT["email"]))
    for path in (
        "/teacher/overview",
        f"/teacher/attempts/{attempt['id']}",
        f"/teacher/students/{student_id}",
    ):
        assert (await student.get(path)).status_code == 403, path


async def test_overview_raises_alerts_from_server_rules(student, teacher):
    attempt = await _submit_with_events(student, ["tab_hidden", "tab_hidden", "paste"])

    data = (await teacher.get("/teacher/overview")).json()

    row = next(s for s in data["students"] if s["email"] == STUDENT["email"])
    assert row["attempts"] == 1
    assert row["last_score_pct"] == 0.0
    assert row["integrity_flags"] == 3
    assert row["alert"] == "high"
    alert = next(a for a in data["alerts"] if a["attempt_id"] == attempt["id"])
    assert {r["kind"] for r in alert["reasons"]} == {"integrity", "low_score", "rushed"}
    assert alert["events"] == {"tab_hidden": 2, "paste": 1}
    assert data["flagged_attempts"] >= 1
    assert len(data["activity"]) == 14
    assert data["activity"][-1]["attempts"] >= 1  # el intento de hoy


async def test_reconnecting_is_not_an_integrity_signal(student, teacher):
    await _submit_with_events(student, ["resumed", "resumed", "resumed"])

    data = (await teacher.get("/teacher/overview")).json()

    row = next(s for s in data["students"] if s["email"] == STUDENT["email"])
    assert row["integrity_flags"] == 0


async def test_teacher_sees_full_review_and_integrity_timeline(student, teacher):
    attempt = await _submit_with_events(student, ["paste"])

    detail = (await teacher.get(f"/teacher/attempts/{attempt['id']}")).json()

    assert detail["student"]["email"] == STUDENT["email"]
    assert [e["type"] for e in detail["events"]] == ["paste"]
    assert len(detail["attempt"]["review"]) == len(attempt["questions"])
    assert all(item["correct_answer"] for item in detail["attempt"]["review"])


async def test_teacher_cannot_peek_open_attempt(student, teacher):
    attempt = await start(student)
    assert (await teacher.get(f"/teacher/attempts/{attempt['id']}")).status_code == 409


async def test_student_detail_only_for_students(teacher):
    me = (await teacher.get("/auth/me")).json()
    assert (await teacher.get(f"/teacher/students/{me['id']}")).status_code == 404
