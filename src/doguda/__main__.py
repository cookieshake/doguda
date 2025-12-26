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
_apps_merged = False

def _load_apps(merge: bool = True):
    global discovered_apps, _apps_loaded, _apps_merged
    
    if not _apps_loaded:
        base_dir = Path(DOGUDA_PATH) if DOGUDA_PATH else Path.cwd()
        raw_apps = discover_apps(base_dir)
        _apps_loaded = True
        
        # Merge apps by name (explicit name or module path)
        grouped_apps: Dict[str, DogudaApp] = {}
        for mod_name, app in raw_apps.items():
            display_name = app.name
            if display_name not in grouped_apps:
                grouped_apps[display_name] = app
            else:
                target_app = grouped_apps[display_name]
                if target_app is not app:
                    target_app.registry.update(app.registry)
                    # We still need to collect all providers for the final pool
                    target_app.providers.update(app.providers)
                    for p in app.always_providers:
                        if p not in target_app.always_providers:
                            target_app.always_providers.append(p)
        
        discovered_apps = dict(sorted(grouped_apps.items()))

    if merge and not _apps_merged:
        # Final pass: Share all providers across all apps to enable cross-app DI
        all_combined_providers = {}
        all_combined_always = []
        
        for app in discovered_apps.values():
            all_combined_providers.update(app.providers)
            for p in app.always_providers:
                if p not in all_combined_always:
                    all_combined_always.append(p)
        
        for app in discovered_apps.values():
            app.providers.update(all_combined_providers)
            for p in all_combined_always:
                if p not in app.always_providers:
                    app.always_providers.append(p)
        
        _apps_merged = True

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
            
    # Merge all providers from all apps into master_app
    for app in discovered_apps.values():
        master_app.providers.update(app.providers)
        for p in app.always_providers:
            if p not in master_app.always_providers:
                master_app.always_providers.append(p)
            
    api = master_app.build_fastapi()
    uvicorn.run(api, host=host, port=port)


@cli.command(name="list")
def list_commands():
    """List all registered doguda commands from all discovered apps."""
    _load_apps(merge=False)
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


@cli.command(name="exec", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def exec_command(
    ctx: typer.Context,
    task_name: str = typer.Argument(..., help="The name of the task to execute."),
):
    """Execute a registered @doguda command."""
    _load_apps(merge=True)
    
    # Collect additional arguments as kwargs
    kwargs = {}
    for arg in ctx.args:
        if "=" in arg:
            key, value = arg.split("=", 1)
            kwargs[key] = value
        else:
            typer.secho(f"Warning: Ignoring malformed argument '{arg}'. Use key=value format.", fg=typer.colors.YELLOW)

    # Find the app that has this command
    target_app = None
    for app in discovered_apps.values():
        if task_name in app.registry:
            target_app = app
            break
            
    if not target_app:
        typer.secho(f"Error: Command '{task_name}' not found in any discovered apps.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
        
    # We need to handle type conversion if possible.
    # But for now, let's just pass strings and see.
    # Ideally we'd inspect the signature and convert.
    result = target_app.execute_sync(task_name, kwargs)
    target_app._echo_result(result)


def main():
    # Only load apps for commands that need them.
    # We check sys.argv to see if we are running 'exec', 'serve', or 'list'.
    # If it's just 'doguda' or 'doguda --help', we skip loading to avoid side effects and be faster.
    
    cli()


if __name__ == "__main__":
    main()
