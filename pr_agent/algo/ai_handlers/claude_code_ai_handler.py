from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt

from pr_agent.algo.ai_handlers.base_ai_handler import BaseAiHandler
from pr_agent.algo.ai_handlers.claude_code.cli_settings import ClaudeCodeSettings
from pr_agent.algo.ai_handlers.claude_code.command import ClaudeCodeCommand
from pr_agent.algo.ai_handlers.claude_code.envelope import ClaudeCodeEnvelope, EnvelopeInterpreter
from pr_agent.algo.ai_handlers.claude_code.errors import ClaudeCodeTransientError
from pr_agent.algo.ai_handlers.claude_code.process_slots import CLAUDE_CODE_PROCESS_SLOTS
from pr_agent.algo.ai_handlers.claude_code.runner import ClaudeCodeRunner
from pr_agent.algo.run_details import record_ai_call
from pr_agent.config_loader import get_settings
from pr_agent.log import get_logger


class ClaudeCodeAIHandler(BaseAiHandler):
    """Produce each completion by running the Claude Code CLI instead of calling a model API.

    For gateways that only accept traffic from a genuine Claude Code client. The CLI loads the
    operator's settings file (gateway URL, credentials, model) and makes the request itself.
    """

    def __init__(
        self,
        settings: ClaudeCodeSettings | None = None,
        runner: ClaudeCodeRunner | None = None,
        interpreter: EnvelopeInterpreter | None = None,
    ):
        self._settings: ClaudeCodeSettings = settings or ClaudeCodeSettings.from_dynaconf(get_settings())
        self._runner: ClaudeCodeRunner = runner or ClaudeCodeRunner(
            ClaudeCodeCommand(self._settings), CLAUDE_CODE_PROCESS_SLOTS, self._settings.max_concurrent_calls
        )
        self._interpreter: EnvelopeInterpreter = interpreter or EnvelopeInterpreter()

    @property
    def deployment_id(self) -> None:
        return None

    async def chat_completion(
        self, model: str, system: str, user: str, temperature: float = 0.2, img_path: str | None = None
    ) -> tuple[str, str]:
        if img_path:
            get_logger().warning(f"The Claude Code handler sends text only; ignoring image {img_path}")
        get_logger().debug(f"The Claude Code CLI does not accept a temperature; ignoring {temperature}")
        envelope: ClaudeCodeEnvelope = await self._complete_with_retry(system, user)
        reported_model: str = self._settings.model or model
        record_ai_call(
            envelope.usage.as_run_details_usage(), model=reported_model, cost_usd=envelope.total_cost_usd
        )
        get_logger().info(
            "AI response", response=envelope.result, finish_reason=envelope.finish_reason, model=reported_model
        )
        return envelope.result, envelope.finish_reason

    async def _complete_with_retry(self, system: str, user: str) -> ClaudeCodeEnvelope:
        retrying = AsyncRetrying(
            retry=retry_if_exception_type(ClaudeCodeTransientError),
            stop=stop_after_attempt(self._settings.retry_attempts),
            reraise=True,
        )
        async for attempt in retrying:
            with attempt:
                return await self._complete_once(system, user)

    async def _complete_once(self, system: str, user: str) -> ClaudeCodeEnvelope:
        timeout_seconds: float = float(get_settings().config.get("ai_timeout", 120))
        try:
            outcome = await self._runner.run(system, user, timeout_seconds)
            return self._interpreter.interpret(outcome)
        except ClaudeCodeTransientError as error:
            get_logger().warning(f"Transient Claude Code failure: {error}")
            raise
