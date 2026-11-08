import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pr_agent.algo.ai_handlers.claude_code.errors import (
    ClaudeCodeAuthError,
    ClaudeCodeError,
    ClaudeCodeRequestError,
    ClaudeCodeTransientError,
)
from pr_agent.algo.ai_handlers.claude_code.runner import CliOutcome

AUTH_FAILURE_STATUSES: frozenset[int] = frozenset({401, 403})
TOO_MANY_REQUESTS = 429
CLIENT_ERROR_RANGE = range(400, 500)
DIAGNOSTIC_TAIL_CHARS = 500
# PR-Agent's tools follow the OpenAI vocabulary; Claude reports "max_tokens" for a cut-off answer.
FINISH_REASON_BY_STOP_REASON: dict[str, str] = {"max_tokens": "length"}
DEFAULT_FINISH_REASON = "stop"


class ClaudeCodeUsage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    output_tokens: int = 0

    def as_run_details_usage(self) -> dict[str, int]:
        # The CLI reports only uncached tokens as input_tokens; summing the cache counters keeps
        # the prompt total honest once the system prompt starts being cached.
        prompt_tokens: int = self.input_tokens + self.cache_creation_input_tokens + self.cache_read_input_tokens
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": self.output_tokens,
            "total_tokens": prompt_tokens + self.output_tokens,
        }


class ClaudeCodeEnvelope(BaseModel):
    """The JSON object `claude --print --output-format json` writes, on success and on API failure."""

    model_config = ConfigDict(extra="ignore")

    is_error: bool = False
    result: str | None = None
    subtype: str | None = None
    stop_reason: str | None = None
    api_error_status: int | None = None
    total_cost_usd: float | None = None
    usage: ClaudeCodeUsage = Field(default_factory=ClaudeCodeUsage)

    @property
    def finish_reason(self) -> str:
        return FINISH_REASON_BY_STOP_REASON.get(self.stop_reason or "", DEFAULT_FINISH_REASON)


class EnvelopeInterpreter:
    """Turn a finished CLI run into a usable envelope, or the narrowest error it justifies."""

    def interpret(self, outcome: CliOutcome) -> ClaudeCodeEnvelope:
        envelope: ClaudeCodeEnvelope = self._parse(outcome)
        if envelope.is_error or outcome.return_code != 0:
            raise self._classify(envelope, outcome.return_code)
        if not envelope.result or not envelope.result.strip():
            raise ClaudeCodeTransientError(f"Claude Code CLI returned no result text (subtype: {envelope.subtype})")
        return envelope

    def _parse(self, outcome: CliOutcome) -> ClaudeCodeEnvelope:
        try:
            return ClaudeCodeEnvelope.model_validate(json.loads(outcome.stdout))
        except (json.JSONDecodeError, ValidationError) as error:
            raise ClaudeCodeTransientError(
                f"Claude Code CLI exited with code {outcome.return_code} without a JSON result ({error}). "
                f"stdout: {_tail(outcome.stdout)} stderr: {_tail(outcome.stderr)}"
            ) from error

    @staticmethod
    def _classify(envelope: ClaudeCodeEnvelope, return_code: int) -> ClaudeCodeError:
        status: int | None = envelope.api_error_status
        detail: str = (
            f"Claude Code CLI failed (exit {return_code}, api status {status}): "
            f"{_tail(envelope.result or envelope.subtype or 'no detail')}"
        )
        if status in AUTH_FAILURE_STATUSES:
            return ClaudeCodeAuthError(detail)
        if status in CLIENT_ERROR_RANGE and status != TOO_MANY_REQUESTS:
            return ClaudeCodeRequestError(detail)
        return ClaudeCodeTransientError(detail)


def _tail(text: str) -> str:
    return text.strip()[-DIAGNOSTIC_TAIL_CHARS:]
