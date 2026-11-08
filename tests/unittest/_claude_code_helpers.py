import json
import stat
import sys
from pathlib import Path

from pr_agent.algo.ai_handlers.claude_code.cli_settings import ClaudeCodeSettings

# A stand-in `claude` executable: echoes what it was given inside a JSON envelope, or fails on
# demand, so the runner and handler can be exercised against a real subprocess.
FAKE_CLI_SOURCE = """\
import json, os, sys, time
argv = sys.argv[1:]
user = sys.stdin.read()
system = None
if "--system-prompt-file" in argv:
    with open(argv[argv.index("--system-prompt-file") + 1], encoding="utf-8") as handle:
        system = handle.read()
mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
if mode == "sleep":
    time.sleep(30)
if mode == "garbage":
    print("not json")
    sys.exit(2)
if mode == "auth":
    print(json.dumps({"is_error": True, "api_error_status": 401, "result": "Failed to authenticate"}))
    sys.exit(1)
echo = {"argv": argv, "user": user, "system": system, "cwd": os.getcwd()}
print(json.dumps({"is_error": False, "result": json.dumps(echo), "stop_reason": "end_turn",
                  "total_cost_usd": 0.01, "usage": {"input_tokens": 3, "output_tokens": 2}}))
"""


def build_settings(**overrides: object) -> ClaudeCodeSettings:
    values: dict[str, object] = {
        "executable": sys.executable,
        "settings_file": "",
        "model": "",
        "bare": True,
        "max_concurrent_calls": 2,
        "retry_attempts": 2,
        "extra_args": [],
    }
    values.update(overrides)
    return ClaudeCodeSettings.model_validate(values)


def write_fake_cli(directory: Path) -> Path:
    script: Path = directory / "claude"
    script.write_text(f"#!{sys.executable}\n{FAKE_CLI_SOURCE}", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def envelope_json(**fields: object) -> str:
    return json.dumps(fields)
