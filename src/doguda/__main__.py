import importlib.util
import os
import sys
from pathlib import Path
from typing import List, Optional

import typer
import uvicorn

from .app import default_app
from .loader import load_app_from_target


DEFAULT_MODULE_NAME = "dogudas"
DEFAULT_MODULE = os.environ.get("DOGUDA_MODULE", DEFAULT_MODULE_NAME)
DOGUDA_PATH = os.environ.get("DOGUDA_PATH")

if DOGUDA_PATH:
    sys.path.insert(0, DOGUDA_PATH)

cli = typer.Typer(help="Expose @doguda functions over CLI and HTTP.")
exec_cli = typer.Typer(help="Execute registered @doguda commands.")
cli.add_typer(exec_cli, name="exec")


def _resolve_modules(modules_str: str) -> List[str]:
    resolved_modules = []
    
    # Base directory for auto-discovery
    base_dir = Path(DOGUDA_PATH) if DOGUDA_PATH else Path.cwd()
    
    for module_name in modules_str.split(","):
        module_name = module_name.strip()
        if not module_name:
            continue
            
        spec = None
        try:
            spec = importlib.util.find_spec(module_name)
        except (ImportError, ValueError):
            pass

        if spec is not None:
            resolved_modules.append(module_name)
            continue

        # Only try auto-discovery if using the default name
        if module_name != DEFAULT_MODULE_NAME:
            # Keep meaningful errors: if user typed explicit name and it's missing, keep it so loader fails later
            resolved_modules.append(module_name)
            continue

        # Scan base_dir for possible modules
        candidates = []
        if base_dir.exists():
            # Check for packages first
            for item in base_dir.iterdir():
                if item.is_dir() and (item / "__init__.py").exists():
                    if not item.name.startswith((".", "_")):
                        candidates.append(item.name)
                elif item.is_file() and item.suffix == ".py":
                    if not item.name.startswith((".", "_")) and item.name != "setup.py":
                        candidates.append(item.stem)

        if candidates:
            # Determine deterministic order
            candidates.sort()
            resolved_modules.append(candidates[0])
        else:
             resolved_modules.append(module_name)

    return resolved_modules


@cli.command()
def serve(
    module: str = typer.Option(DEFAULT_MODULE, help="Module(s) that register @doguda commands (comma-separated)."),
    host: str = typer.Option("0.0.0.0", help="Host for the FastAPI server."),
    port: int = typer.Option(8000, help="Port for the FastAPI server."),
):
    resolved_modules = _resolve_modules(module)
    typer.secho(f"Using modules: {', '.join(resolved_modules)}", fg=typer.colors.GREEN)

    # Load all modules. We assume they register to the same default_app or compatible apps.
    # The last loaded 'app' object might be used to build fastapi, assuming they share state (like default_app).
    final_app = None
    for mod in resolved_modules:
        try:
            final_app = load_app_from_target(mod)
        except Exception as exc:  # noqa: BLE001
            typer.secho(f"Failed to load Doguda app from '{mod}': {exc}", fg=typer.colors.RED)
            raise typer.Exit(code=1) from exc
    
    if final_app:
        api = final_app.build_fastapi()
        uvicorn.run(api, host=host, port=port)
    else:
        typer.secho("No Doguda app loaded.", fg=typer.colors.RED)
        raise typer.Exit(code=1)


def _attach_registered_commands(app_modules: List[str]) -> None:
    for mod in app_modules:
        try:
            app = load_app_from_target(mod)
            app.register_cli_commands(exec_cli)
        except Exception as exc:  # noqa: BLE001
            # Warn but maybe not exit? For robust CLI usage if one module is bad?
            # Existing behavior was strict. Let's keep it strict.
            typer.secho(f"Failed to load Doguda app from '{mod}': {exc}", fg=typer.colors.RED)
            raise typer.Exit(code=1) from exc


def main():
    modules = _resolve_modules(DEFAULT_MODULE)
    
    if "serve" not in sys.argv:
         typer.secho(f"Using modules: {', '.join(modules)}", fg=typer.colors.BRIGHT_BLACK, err=True)
         _attach_registered_commands(modules)
    
    cli()


if __name__ == "__main__":
    main()
