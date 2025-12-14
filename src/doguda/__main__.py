import importlib.util
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

import typer
import uvicorn
from fastapi import FastAPI

from .app import DogudaApp
from .loader import discover_apps, load_app_from_target


DOGUDA_PATH = os.environ.get("DOGUDA_PATH")



if DOGUDA_PATH:
    sys.path.insert(0, DOGUDA_PATH)
elif os.getcwd() not in sys.path:
     sys.path.insert(0, os.getcwd())



cli = typer.Typer(help="Expose @doguda functions over CLI and HTTP.")
exec_cli = typer.Typer(help="Execute registered @doguda commands.")

discovered_apps: Dict[str, DogudaApp] = {}

_apps_loaded = False

def _load_apps():
    global discovered_apps, _apps_loaded
    if _apps_loaded:
        return
        
    base_dir = Path(DOGUDA_PATH) if DOGUDA_PATH else Path.cwd()
    raw_apps = discover_apps(base_dir)
    _apps_loaded = True
    
    # Merge apps by name (explicit name or module path)
    grouped_apps: Dict[str, DogudaApp] = {}
    
    for mod_name, app in raw_apps.items():
        # Use explicit app name (now mandatory)
        display_name = app.name
        
        if display_name not in grouped_apps:
            grouped_apps[display_name] = app
        else:
            # Merge commands into existing app found with the same name
            target_app = grouped_apps[display_name]
            # Avoid self-merge if it's the same instance
            if target_app is not app:
                target_app.registry.update(app.registry)

    discovered_apps = dict(sorted(grouped_apps.items()))

@cli.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Host for the FastAPI server."),
    port: int = typer.Option(8000, help="Port for the FastAPI server."),
):
    """Start the HTTP server with all discovered commands."""
    _load_apps()
    
    if not discovered_apps:
        typer.secho("No Doguda apps found.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho(f"Found {len(discovered_apps)} apps: {', '.join(discovered_apps.keys())}", fg=typer.colors.GREEN)
    
    # Merge all apps into one master app for serving
    master_app = DogudaApp("DogudaServer")
    
    for mod_name, app in discovered_apps.items():
        for name, fn in app.registry.items():
            if name in master_app.registry:
                # Handle connection: overwrite or warn? 
                # For now, warn and skip/overwrite. Let's overwrite but warn.
                typer.secho(f"Warning: Command '{name}' from '{mod_name}' overrides existing command.", fg=typer.colors.YELLOW)
            master_app.registry[name] = fn
            
    api = master_app.build_fastapi()
    uvicorn.run(api, host=host, port=port)


@cli.command(name="list")
def list_commands():
    """List all registered doguda commands from all discovered apps."""
    _load_apps()
    import inspect
    
    if not discovered_apps:
        typer.secho("No Doguda apps found.", fg=typer.colors.YELLOW)
        return

    for mod_name, app in discovered_apps.items():
        if not app.registry:
            continue
            
        typer.secho(f"\n📦 {mod_name}", fg=typer.colors.CYAN, bold=True)
        
        for name, fn in app.registry.items():
            sig = inspect.signature(fn)
            params = ", ".join(
                f"{p.name}: {p.annotation.__name__ if hasattr(p.annotation, '__name__') else str(p.annotation)}"
                for p in sig.parameters.values()
            )
            typer.secho(f"  • {name}({params})", fg=typer.colors.GREEN)
            
            if fn.__doc__:
                doc_line = fn.__doc__.strip().split("\n")[0]
                typer.secho(f"      {doc_line}", fg=typer.colors.BRIGHT_BLACK)


def main():
    # Perform discovery BEFORE invoking the CLI to populate 'exec' subcommands
    _load_apps()
    
    if discovered_apps:
        # Register commands to exec_cli
        
        params_map = {} # name -> function
        
        for mod_name, app in discovered_apps.items():
            for name, fn in app.registry.items():
                if name in params_map:
                    # Collision
                    continue
                params_map[name] = (fn, mod_name)
        
        # Reregister
        for mod_name, app in discovered_apps.items():
             app.register_cli_commands(exec_cli)
             
    cli.add_typer(exec_cli, name="exec")
    cli()


if __name__ == "__main__":
    main()
