import shutil
from pathlib import Path

from pr_agent.algo.ai_handlers.claude_code.cli_settings import ClaudeCodeSettings
from pr_agent.algo.ai_handlers.claude_code.errors import ClaudeCodeConfigurationError

# One headless answer as a JSON envelope, nothing kept on disk, and an empty tool list so the
# model cannot act beyond answering the prompt: the semantics of a direct completion call.
HEADLESS_COMPLETION_FLAGS: tuple[str, ...] = (
    "--print",
    "--output-format", "json",
    "--no-session-persistence",
    "--tools", "",
)


class ClaudeCodeCommand:
    """Build the argv of one Claude Code completion from validated host settings."""

    def __init__(self, settings: ClaudeCodeSettings):
        self._settings = settings
        self._executable = self._resolve_executable(settings.executable)
        self._settings_file = self._resolve_settings_file(settings.settings_file)

    @property
    def executable(self) -> str:
        return self._executable

    def build(self, system_prompt_file: Path | None) -> list[str]:
        argv: list[str] = [self._executable, *HEADLESS_COMPLETION_FLAGS]
        if self._settings.bare:
            argv.append("--bare")
        if self._settings_file:
            argv += ["--settings", self._settings_file]
        if self._settings.model:
            argv += ["--model", self._settings.model]
        if system_prompt_file is not None:
            argv += ["--system-prompt-file", str(system_prompt_file)]
        argv += self._settings.extra_args
        return argv

    @staticmethod
    def _resolve_executable(executable: str) -> str:
        resolved: str | None = shutil.which(executable)
        if resolved is None:
            raise ClaudeCodeConfigurationError(
                f"Claude Code executable '{executable}' was not found. Install the CLI in the runtime "
                f"image or set claude_code.executable to its absolute path."
            )
        return resolved

    @staticmethod
    def _resolve_settings_file(settings_file: str) -> str:
        if not settings_file:
            return ""
        path = Path(settings_file).expanduser()
        if not path.is_file():
            raise ClaudeCodeConfigurationError(f"claude_code.settings_file '{settings_file}' is not a readable file")
        # Not resolve(): a Kubernetes Secret mount is a symlink into a timestamped directory that a
        # Secret update deletes, while the symlink itself keeps pointing at the current file.
        return str(path.absolute())
