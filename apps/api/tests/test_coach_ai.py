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


def test_provider_is_chosen_by_env_only(monkeypatch):
    from app.core.config import get_settings
    from app.services.coach_ai import AnthropicProvider, OpenAIProvider, get_provider

    def with_env(**env):
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()
        return get_provider()

    try:
        claude = with_env(AI_PROVIDER="anthropic", ANTHROPIC_API_KEY="k")
        assert isinstance(claude, AnthropicProvider)
        groq = with_env(
            AI_PROVIDER="openai",
            OPENAI_API_KEY="k",
            OPENAI_BASE_URL="https://api.groq.com/openai/v1/",
        )
        assert (
            isinstance(groq, OpenAIProvider) and groq.base_url == "https://api.groq.com/openai/v1"
        )
        assert with_env(AI_PROVIDER="mock") is None
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
