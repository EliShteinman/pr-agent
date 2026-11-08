import pytest
from dynaconf import Dynaconf

from pr_agent.algo.ai_handlers.claude_code.cli_settings import ClaudeCodeSettings
from pr_agent.algo.ai_handlers.claude_code.errors import ClaudeCodeConfigurationError
from pr_agent.config_loader import get_settings


def _dynaconf_with(section: dict[str, object]) -> Dynaconf:
    settings = Dynaconf()
    settings.set("claude_code", section)
    return settings


def test_shipped_defaults_validate():
    settings = ClaudeCodeSettings.from_dynaconf(get_settings())

    assert settings.executable == "claude"


def test_shipped_defaults_enable_bare_mode():
    assert ClaudeCodeSettings.from_dynaconf(get_settings()).bare is True


def test_missing_section_is_a_configuration_error():
    with pytest.raises(ClaudeCodeConfigurationError):
        ClaudeCodeSettings.from_dynaconf(Dynaconf())


@pytest.mark.parametrize("field, value", [
    ("max_concurrent_calls", 0),
    ("retry_attempts", 0),
    ("executable", ""),
    ("extra_args", "--effort high"),
])
def test_invalid_value_is_a_configuration_error(field, value):
    section: dict[str, object] = dict(get_settings().get("claude_code"))
    section[field] = value

    with pytest.raises(ClaudeCodeConfigurationError):
        ClaudeCodeSettings.from_dynaconf(_dynaconf_with(section))


def test_settings_are_immutable():
    settings = ClaudeCodeSettings.from_dynaconf(get_settings())

    with pytest.raises(ValueError):
        settings.model = "opus"
