import asyncio
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pr_agent.algo.ai_handlers.claude_code.command import ClaudeCodeCommand
from pr_agent.algo.ai_handlers.claude_code.errors import ClaudeCodeTimeoutError, ClaudeCodeTransientError
from pr_agent.algo.ai_handlers.claude_code.process_slots import ProcessSlots
from pr_agent.log import get_logger

WORKDIR_PREFIX = "pr-agent-claude-code-"
SYSTEM_PROMPT_FILENAME = "system_prompt.txt"
PROMPT_ENCODING = "utf-8"


class CliOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    stdout: str
    stderr: str
    return_code: int


class ClaudeCodeRunner:
    """Run one CLI process per completion in a throwaway working directory.

    The system prompt goes through a file and the user prompt through stdin, so neither is
    bound by the per-argument size limit; the empty directory keeps the run from picking up
    files from wherever PR-Agent was started.
    """

    def __init__(self, command: ClaudeCodeCommand, slots: ProcessSlots, max_concurrent_calls: int):
        self._command = command
        self._slots = slots
        self._max_concurrent_calls = max_concurrent_calls

    async def run(self, system_prompt: str, user_prompt: str, timeout_seconds: float) -> CliOutcome:
        with tempfile.TemporaryDirectory(prefix=WORKDIR_PREFIX) as workdir:
            system_prompt_file: Path | None = self._write_system_prompt(Path(workdir), system_prompt)
            argv: list[str] = self._command.build(system_prompt_file)
            async with self._slots.for_running_loop(self._max_concurrent_calls):
                return await self._execute(argv, workdir, user_prompt, timeout_seconds)

    @staticmethod
    def _write_system_prompt(workdir: Path, system_prompt: str) -> Path | None:
        if not system_prompt:
            return None
        path: Path = workdir / SYSTEM_PROMPT_FILENAME
        path.write_text(system_prompt, encoding=PROMPT_ENCODING)
        return path

    async def _execute(self, argv: list[str], workdir: str, user_prompt: str, timeout_seconds: float) -> CliOutcome:
        get_logger().debug(f"Running Claude Code CLI with {len(argv)} arguments in {workdir}")
        try:
            process: asyncio.subprocess.Process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
            )
        except OSError as error:
            raise ClaudeCodeTransientError(f"Failed to start the Claude Code CLI: {error}") from error
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(user_prompt.encode(PROMPT_ENCODING)), timeout=timeout_seconds
            )
        except asyncio.TimeoutError as error:
            await self._kill(process)
            raise ClaudeCodeTimeoutError(f"Claude Code CLI timed out after {timeout_seconds}s") from error
        return CliOutcome(
            stdout=stdout.decode(PROMPT_ENCODING, errors="replace"),
            stderr=stderr.decode(PROMPT_ENCODING, errors="replace"),
            return_code=process.returncode,
        )

    @staticmethod
    async def _kill(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            process.kill()
        except ProcessLookupError:
            return
        await process.wait()
