from __future__ import annotations

import os
from typing import Optional

import typer
import uvicorn

from .app import default_app
from .loader import load_app_from_target


DEFAULT_MODULE = os.environ.get("DOGUDA_MODULE", "doguda_app")

cli = typer.Typer(help="Expose @doguda functions over CLI and HTTP.")
exec_cli = typer.Typer(help="Execute registered @doguda commands.")
cli.add_typer(exec_cli, name="exec")


@cli.command()
def serve(
    module: str = typer.Option(DEFAULT_MODULE, help="Module that registers @doguda commands."),
    host: str = typer.Option("0.0.0.0", help="Host for the FastAPI server."),
    port: int = typer.Option(8000, help="Port for the FastAPI server."),
):
    try:
        app = load_app_from_target(module)
    except Exception as exc:  # noqa: BLE001
        typer.secho(f"Failed to load Doguda app from '{module}': {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    api = app.build_fastapi()
    uvicorn.run(api, host=host, port=port)


def _attach_registered_commands(app_module: str) -> None:
    try:
        app = load_app_from_target(app_module)
    except Exception as exc:  # noqa: BLE001
        typer.secho(f"Failed to load Doguda app from '{app_module}': {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    app.register_cli_commands(exec_cli)


def main():
    module = DEFAULT_MODULE
    _attach_registered_commands(module)
    cli()


if __name__ == "__main__":
    main()
