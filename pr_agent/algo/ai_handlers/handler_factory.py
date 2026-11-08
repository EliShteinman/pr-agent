from pr_agent.algo.ai_handlers.base_ai_handler import BaseAiHandler
from pr_agent.algo.ai_handlers.claude_code_ai_handler import ClaudeCodeAIHandler
from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from pr_agent.config_loader import get_settings

DEFAULT_AI_HANDLER = "litellm"

AI_HANDLERS_BY_NAME: dict[str, type[BaseAiHandler]] = {
    "litellm": LiteLLMAIHandler,
    "claude_code": ClaudeCodeAIHandler,
}


class UnknownAiHandlerError(ValueError):
    """config.ai_handler names no known handler."""


def get_ai_handler_class() -> type[BaseAiHandler]:
    """Return the handler class named by config.ai_handler.

    An unknown name fails instead of falling back to LiteLLM: a deployment that asked for a
    specific client must never have its traffic silently sent through a different one.
    """
    configured: str = str(get_settings().config.get("ai_handler", DEFAULT_AI_HANDLER))
    handler_name: str = configured.strip().lower()
    handler_class: type[BaseAiHandler] | None = AI_HANDLERS_BY_NAME.get(handler_name)
    if handler_class is None:
        raise UnknownAiHandlerError(
            f"Unknown config.ai_handler '{configured}'. Supported values: {sorted(AI_HANDLERS_BY_NAME)}"
        )
    return handler_class
