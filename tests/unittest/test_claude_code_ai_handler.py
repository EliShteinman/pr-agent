import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from pr_agent.algo.ai_handlers.claude_code.errors import (
    ClaudeCodeAuthError,
    ClaudeCodeTimeoutError,
    ClaudeCodeTransientError,
)
from pr_agent.algo.ai_handlers.claude_code.runner import CliOutcome
from pr_agent.algo.ai_handlers.claude_code_ai_handler import ClaudeCodeAIHandler
from pr_agent.algo.run_details import init_run_details
from tests.unittest._claude_code_helpers import build_settings, envelope_json, write_fake_cli

SUCCESS = CliOutcome(
    stdout=envelope_json(result="answer", stop_reason="end_turn", total_cost_usd=0.5,
                         usage={"input_tokens": 4, "output_tokens": 6}),
    stderr="",
    return_code=0,
)


@pytest.fixture
def runner() -> AsyncMock:
    mock = AsyncMock()
    mock.run.return_value = SUCCESS
    return mock


@pytest.fixture
def handler(runner: AsyncMock) -> ClaudeCodeAIHandler:
    return ClaudeCodeAIHandler(settings=build_settings(retry_attempts=2), runner=runner)


async def _complete(handler: ClaudeCodeAIHandler) -> tuple[str, str]:
    return await handler.chat_completion(model="anthropic/claude", system="sys", user="usr")


async def test_returns_cli_result(handler):
    assert (await _complete(handler))[0] == "answer"


async def test_returns_finish_reason(handler):
    assert (await _complete(handler))[1] == "stop"


async def test_forwards_both_prompts_to_runner(handler, runner):
    await _complete(handler)

    assert runner.run.await_args.args[:2] == ("sys", "usr")


async def test_has_no_deployment_id(handler):
    assert handler.deployment_id is None


async def test_retries_transient_failure_on_same_model(handler, runner):
    runner.run.side_effect = [ClaudeCodeTransientError("503"), SUCCESS]

    await _complete(handler)

    assert runner.run.await_count == 2


async def test_stops_after_configured_attempts(handler, runner):
    runner.run.side_effect = ClaudeCodeTransientError("503")

    with pytest.raises(ClaudeCodeTransientError):
        await _complete(handler)


@pytest.mark.parametrize("error", [ClaudeCodeAuthError("401"), ClaudeCodeTimeoutError("slow")])
async def test_does_not_retry_auth_or_timeout(handler, runner, error):
    runner.run.side_effect = error

    with pytest.raises(type(error)):
        await _complete(handler)

    assert runner.run.await_count == 1


async def test_records_ai_call_in_run_details(handler):
    details = init_run_details()

    await _complete(handler)

    assert details.num_ai_calls == 1


async def test_records_prompt_tokens_in_run_details(handler):
    details = init_run_details()

    await _complete(handler)

    assert details.prompt_tokens == 4


async def test_end_to_end_cli_receives_operator_settings_file(tmp_path: Path):
    settings_file: Path = tmp_path / "settings.json"
    settings_file.write_text("{}", encoding="utf-8")
    handler = ClaudeCodeAIHandler(settings=build_settings(
        executable=str(write_fake_cli(tmp_path)), settings_file=str(settings_file),
    ))

    response, _ = await handler.chat_completion(model="ignored", system="sys", user="usr")
    argv: list[str] = json.loads(response)["argv"]

    assert argv[argv.index("--settings") + 1] == str(settings_file.resolve())
