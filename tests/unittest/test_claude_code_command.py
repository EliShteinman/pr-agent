from pathlib import Path

import pytest

from pr_agent.algo.ai_handlers.claude_code.command import HEADLESS_COMPLETION_FLAGS, ClaudeCodeCommand
from pr_agent.algo.ai_handlers.claude_code.errors import ClaudeCodeConfigurationError
from tests.unittest._claude_code_helpers import build_settings

SYSTEM_PROMPT_FILE = Path("/tmp/system_prompt.txt")


@pytest.fixture
def settings_file(tmp_path: Path) -> Path:
    path: Path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    return path


def _value_after(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


def test_starts_with_resolved_executable():
    command = ClaudeCodeCommand(build_settings())

    assert command.build(None)[0] == command.executable


def test_always_runs_headless_without_tools():
    argv: list[str] = ClaudeCodeCommand(build_settings()).build(None)

    assert argv[1:1 + len(HEADLESS_COMPLETION_FLAGS)] == list(HEADLESS_COMPLETION_FLAGS)


def test_disables_every_tool():
    argv: list[str] = ClaudeCodeCommand(build_settings()).build(None)

    assert _value_after(argv, "--tools") == ""


def test_adds_bare_when_enabled():
    assert "--bare" in ClaudeCodeCommand(build_settings(bare=True)).build(None)


def test_omits_bare_when_disabled():
    assert "--bare" not in ClaudeCodeCommand(build_settings(bare=False)).build(None)


def test_passes_settings_file_as_absolute_path(settings_file: Path):
    argv: list[str] = ClaudeCodeCommand(build_settings(settings_file=str(settings_file))).build(None)

    assert _value_after(argv, "--settings") == str(settings_file.absolute())


def test_omits_settings_flag_when_no_file_configured():
    assert "--settings" not in ClaudeCodeCommand(build_settings()).build(None)


def test_passes_configured_model():
    argv: list[str] = ClaudeCodeCommand(build_settings(model="opus")).build(None)

    assert _value_after(argv, "--model") == "opus"


def test_leaves_model_to_settings_file_when_not_configured():
    assert "--model" not in ClaudeCodeCommand(build_settings()).build(None)


def test_passes_system_prompt_file():
    argv: list[str] = ClaudeCodeCommand(build_settings()).build(SYSTEM_PROMPT_FILE)

    assert _value_after(argv, "--system-prompt-file") == str(SYSTEM_PROMPT_FILE)


def test_omits_system_prompt_flag_without_file():
    assert "--system-prompt-file" not in ClaudeCodeCommand(build_settings()).build(None)


def test_appends_extra_args_last():
    argv: list[str] = ClaudeCodeCommand(build_settings(extra_args=["--effort", "high"])).build(SYSTEM_PROMPT_FILE)

    assert argv[-2:] == ["--effort", "high"]


def test_missing_executable_is_a_configuration_error():
    with pytest.raises(ClaudeCodeConfigurationError):
        ClaudeCodeCommand(build_settings(executable="definitely-not-a-claude-binary"))


def test_missing_settings_file_is_a_configuration_error(tmp_path: Path):
    with pytest.raises(ClaudeCodeConfigurationError):
        ClaudeCodeCommand(build_settings(settings_file=str(tmp_path / "absent.json")))


def test_keeps_symlinked_settings_file_path(tmp_path: Path, settings_file: Path):
    mounted: Path = tmp_path / "mounted-settings.json"
    mounted.symlink_to(settings_file)

    argv: list[str] = ClaudeCodeCommand(build_settings(settings_file=str(mounted))).build(None)

    assert _value_after(argv, "--settings") == str(mounted)
