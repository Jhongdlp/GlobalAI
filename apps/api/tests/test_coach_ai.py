from app.schemas.attempt import AttemptResultOut
from app.services.coach_ai import build_prompt
from tests.test_attempts_api import start


async def test_prompt_contains_mistakes_but_no_personal_data(student):
    attempt = await start(student)
    await student.post(f"/attempts/{attempt['id']}/submit", json={"answers": {}})
    result = await student.get(f"/attempts/{attempt['id']}/result")
    prompt = build_prompt(AttemptResultOut.model_validate(result.json()))

    assert "Puntaje global: 0%" in prompt
    assert "(sin responder)" in prompt
    # "Laura" aparece en la lectura; lo que no debe viajar es la identidad del estudiante.
    for pii in ("Laura Gómez", "estudiante@globalai.demo"):
        assert pii not in prompt
