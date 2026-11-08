from pr_agent.algo.token_budget import FallbackEligibleError


class ClaudeCodeError(Exception):
    """The Claude Code CLI did not produce a usable completion."""


class ClaudeCodeConfigurationError(ClaudeCodeError, ValueError):
    """The [claude_code] settings cannot start the CLI on this host."""


class ClaudeCodeAuthError(ClaudeCodeError):
    """The gateway rejected the credentials; no retry or fallback model can fix that."""


class ClaudeCodeRequestError(ClaudeCodeError, FallbackEligibleError):
    """The gateway rejected this request; a fallback model may still succeed."""


class ClaudeCodeTransientError(ClaudeCodeError, FallbackEligibleError):
    """A failure that the same request may survive when sent again."""


class ClaudeCodeTimeoutError(ClaudeCodeError, FallbackEligibleError):
    """The CLI did not finish within config.ai_timeout."""
