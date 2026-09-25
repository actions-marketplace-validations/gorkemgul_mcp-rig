import pytest

from mcp_rig.client import CallOutcome, ServerSpec


def test_server_spec_splits_a_shell_like_command():
    spec = ServerSpec.from_command_line('python server.py --name "my server"')

    assert spec.command == "python"
    assert spec.args == ["server.py", "--name", "my server"]


def test_server_spec_rejects_an_empty_command():
    with pytest.raises(ValueError, match="server command is empty"):
        ServerSpec.from_command_line("   ")


def test_server_spec_argument_defaults_are_independent():
    first = ServerSpec("python")
    second = ServerSpec("node")

    first.args.append("server.py")

    assert second.args == []


def test_call_outcome_prefers_structured_content():
    outcome = CallOutcome(False, '{"fallback": true}', {"result": 5}, 1.0)

    assert outcome.json() == {"result": 5}


def test_call_outcome_parses_json_text_when_structured_content_is_missing():
    outcome = CallOutcome(False, '{"name": "Ada"}', None, 1.0)

    assert outcome.json() == {"name": "Ada"}


def test_call_outcome_rejects_non_json_text():
    outcome = CallOutcome(False, "plain text", None, 1.0)

    with pytest.raises(ValueError):
        outcome.json()
