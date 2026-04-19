from types import SimpleNamespace

from tokenmind.providers.custom_provider import CustomProvider


def test_custom_provider_parse_handles_empty_choices() -> None:
    provider = CustomProvider()
    response = SimpleNamespace(choices=[])

    result = provider._parse_response(response)

    assert result.finish_reason == "error"
    assert "empty choices" in result.content
