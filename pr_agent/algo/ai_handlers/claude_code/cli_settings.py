from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pr_agent.algo.ai_handlers.claude_code.errors import ClaudeCodeConfigurationError

CLAUDE_CODE_SECTION = "claude_code"


class ClaudeCodeSettings(BaseModel):
    """The validated [claude_code] section; defaults live in configuration.toml."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    executable: str = Field(min_length=1)
    settings_file: str
    model: str
    bare: bool
    max_concurrent_calls: int = Field(ge=1)
    retry_attempts: int = Field(ge=1)
    extra_args: list[str]

    @classmethod
    def from_dynaconf(cls, settings: Any) -> "ClaudeCodeSettings":
        section = settings.get(CLAUDE_CODE_SECTION) or {}
        values: dict[str, Any] = {name: section.get(name) for name in cls.model_fields if name in section}
        try:
            return cls.model_validate(values)
        except ValidationError as error:
            raise ClaudeCodeConfigurationError(f"Invalid [{CLAUDE_CODE_SECTION}] settings: {error}") from error
