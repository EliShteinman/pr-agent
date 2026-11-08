import pytest

from pr_agent.algo.ai_handlers.claude_code.envelope import ClaudeCodeUsage, EnvelopeInterpreter
from pr_agent.algo.ai_handlers.claude_code.errors import (
    ClaudeCodeAuthError,
    ClaudeCodeRequestError,
    ClaudeCodeTransientError,
)
from pr_agent.algo.ai_handlers.claude_code.runner import CliOutcome
from pr_agent.algo.token_budget import FallbackEligibleError
from tests.unittest._claude_code_helpers import envelope_json


@pytest.fixture
def interpreter() -> EnvelopeInterpreter:
    return EnvelopeInterpreter()


def _outcome(stdout: str, return_code: int = 0) -> CliOutcome:
    return CliOutcome(stdout=stdout, stderr="", return_code=return_code)


def _failure(status: int | None) -> CliOutcome:
    return _outcome(envelope_json(is_error=True, api_error_status=status, result="API Error"), return_code=1)


def test_successful_run_yields_result(interpreter):
    envelope = interpreter.interpret(_outcome(envelope_json(result="answer", stop_reason="end_turn")))

    assert envelope.result == "answer"


@pytest.mark.parametrize("stop_reason, finish_reason", [
    ("end_turn", "stop"),
    ("max_tokens", "length"),
    (None, "stop"),
])
def test_maps_stop_reason_to_finish_reason(interpreter, stop_reason, finish_reason):
    envelope = interpreter.interpret(_outcome(envelope_json(result="answer", stop_reason=stop_reason)))

    assert envelope.finish_reason == finish_reason


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_is_fatal(interpreter, status):
    with pytest.raises(ClaudeCodeAuthError):
        interpreter.interpret(_failure(status))


def test_auth_failure_does_not_trigger_fallback_models(interpreter):
    with pytest.raises(Exception) as raised:
        interpreter.interpret(_failure(401))

    assert not isinstance(raised.value, FallbackEligibleError)


@pytest.mark.parametrize("status", [400, 404, 413])
def test_other_client_error_is_a_request_error(interpreter, status):
    with pytest.raises(ClaudeCodeRequestError):
        interpreter.interpret(_failure(status))


@pytest.mark.parametrize("status", [429, 500, 503, None])
def test_rate_limit_server_error_and_unknown_are_transient(interpreter, status):
    with pytest.raises(ClaudeCodeTransientError):
        interpreter.interpret(_failure(status))


def test_non_zero_exit_with_clean_envelope_is_transient(interpreter):
    with pytest.raises(ClaudeCodeTransientError):
        interpreter.interpret(_outcome(envelope_json(result="answer"), return_code=1))


@pytest.mark.parametrize("stdout", ["", "not json", "[1, 2]"])
def test_unreadable_output_is_transient(interpreter, stdout):
    with pytest.raises(ClaudeCodeTransientError):
        interpreter.interpret(_outcome(stdout))


@pytest.mark.parametrize("result", [None, "", "   "])
def test_empty_result_is_transient(interpreter, result):
    with pytest.raises(ClaudeCodeTransientError):
        interpreter.interpret(_outcome(envelope_json(result=result)))


def test_usage_counts_cached_prompt_tokens():
    usage = ClaudeCodeUsage(input_tokens=5, cache_creation_input_tokens=100, cache_read_input_tokens=900)

    assert usage.as_run_details_usage()["prompt_tokens"] == 1005


def test_usage_total_adds_completion_tokens():
    usage = ClaudeCodeUsage(input_tokens=5, output_tokens=7)

    assert usage.as_run_details_usage()["total_tokens"] == 12
