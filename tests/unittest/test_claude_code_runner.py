import asyncio
import json
from pathlib import Path

import pytest

from pr_agent.algo.ai_handlers.claude_code.command import ClaudeCodeCommand
from pr_agent.algo.ai_handlers.claude_code.errors import ClaudeCodeTimeoutError
from pr_agent.algo.ai_handlers.claude_code.process_slots import ProcessSlots
from pr_agent.algo.ai_handlers.claude_code.runner import WORKDIR_PREFIX, ClaudeCodeRunner, cli_environment
from tests.unittest._claude_code_helpers import build_settings, write_fake_cli

TIMEOUT_SECONDS = 20.0
LARGE_SYSTEM_PROMPT = "S" * 300_000


@pytest.fixture
def runner(tmp_path: Path) -> ClaudeCodeRunner:
    command = ClaudeCodeCommand(build_settings(executable=str(write_fake_cli(tmp_path))))
    return ClaudeCodeRunner(command, ProcessSlots(), max_concurrent_calls=2)


async def _echo(runner: ClaudeCodeRunner, system: str = "sys", user: str = "usr") -> dict[str, object]:
    outcome = await runner.run(system, user, TIMEOUT_SECONDS)
    return json.loads(json.loads(outcome.stdout)["result"])


async def test_user_prompt_reaches_cli_stdin(runner):
    assert (await _echo(runner, user="the diff"))["user"] == "the diff"


async def test_system_prompt_reaches_cli_through_file(runner):
    assert (await _echo(runner, system="the instructions"))["system"] == "the instructions"


async def test_system_prompt_beyond_argument_size_limit_is_delivered(runner):
    assert (await _echo(runner, system=LARGE_SYSTEM_PROMPT))["system"] == LARGE_SYSTEM_PROMPT


async def test_empty_system_prompt_sends_no_file(runner):
    assert (await _echo(runner, system=""))["system"] is None


async def test_runs_in_throwaway_directory(runner):
    assert Path(str((await _echo(runner))["cwd"])).name.startswith(WORKDIR_PREFIX)


async def test_throwaway_directory_is_removed_after_run(runner):
    workdir = Path(str((await _echo(runner))["cwd"]))

    assert not workdir.exists()


async def test_reports_exit_code(runner, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "auth")

    assert (await runner.run("sys", "usr", TIMEOUT_SECONDS)).return_code == 1


async def test_slow_cli_is_killed_with_timeout_error(runner, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "sleep")

    with pytest.raises(ClaudeCodeTimeoutError):
        await runner.run("sys", "usr", 0.5)


async def test_process_slots_cap_concurrency():
    slots = ProcessSlots()
    active: list[int] = [0]
    peak: list[int] = [0]

    async def occupy() -> None:
        async with slots.for_running_loop(2):
            active[0] += 1
            peak[0] = max(peak[0], active[0])
            await asyncio.sleep(0.01)
            active[0] -= 1

    await asyncio.gather(*(occupy() for _ in range(6)))

    assert peak[0] == 2


@pytest.mark.parametrize("environment, expected", [
    ({"SSL_CERT_FILE": "/ca/bundle.crt"}, "/ca/bundle.crt"),
    ({"SSL_CERT_FILE": "/ca/bundle.crt", "NODE_EXTRA_CA_CERTS": "/ca/explicit.crt"}, "/ca/explicit.crt"),
    ({"SSL_CERT_FILE": ""}, None),
    ({}, None),
])
def test_cli_trusts_pr_agent_ca_bundle(environment, expected):
    assert cli_environment(environment).get("NODE_EXTRA_CA_CERTS") == expected


def test_cli_environment_keeps_other_variables():
    assert cli_environment({"HOME": "/home/claude-code"})["HOME"] == "/home/claude-code"


async def test_ca_bundle_reaches_cli_process(runner, monkeypatch):
    monkeypatch.delenv("NODE_EXTRA_CA_CERTS", raising=False)
    monkeypatch.setenv("SSL_CERT_FILE", "/ca/bundle.crt")

    assert (await _echo(runner))["extra_ca"] == "/ca/bundle.crt"
