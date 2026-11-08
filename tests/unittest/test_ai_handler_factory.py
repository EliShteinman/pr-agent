import pytest

from pr_agent.agent.pr_agent import PRAgent
from pr_agent.algo.ai_handlers.claude_code_ai_handler import ClaudeCodeAIHandler
from pr_agent.algo.ai_handlers.handler_factory import UnknownAiHandlerError, get_ai_handler_class
from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from pr_agent.config_loader import get_settings


@pytest.fixture
def ai_handler_setting():
    original = get_settings().config.get("ai_handler")

    def apply(value: str) -> None:
        get_settings().set("config.ai_handler", value)

    yield apply
    get_settings().set("config.ai_handler", original)


def test_default_handler_is_litellm():
    assert get_ai_handler_class() is LiteLLMAIHandler


@pytest.mark.parametrize("configured", ["claude_code", " Claude_Code "])
def test_selects_claude_code_handler(ai_handler_setting, configured):
    ai_handler_setting(configured)

    assert get_ai_handler_class() is ClaudeCodeAIHandler


def test_unknown_handler_fails_instead_of_falling_back(ai_handler_setting):
    ai_handler_setting("claude-cod")

    with pytest.raises(UnknownAiHandlerError):
        get_ai_handler_class()


def test_agent_resolves_handler_when_a_command_runs(ai_handler_setting):
    agent = PRAgent()
    ai_handler_setting("claude_code")

    assert agent.ai_handler is ClaudeCodeAIHandler


def test_agent_keeps_injected_handler(ai_handler_setting):
    ai_handler_setting("claude_code")

    assert PRAgent(ai_handler=LiteLLMAIHandler).ai_handler is LiteLLMAIHandler
