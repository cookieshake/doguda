from typer.testing import CliRunner

from dogu.runner import _attach_registered_commands, cli


def test_ping_command_executes_and_returns_payload():
    _attach_registered_commands("dogu_app")

    runner = CliRunner()
    result = runner.invoke(cli, ["exec", "ping", "3"])

    assert result.exit_code == 0
    assert '"markdown": "ping 3"' in result.stdout
