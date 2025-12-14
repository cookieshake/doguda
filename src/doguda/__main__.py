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

print(f"[Doguda Debug] DOGUDA_PATH: {DOGUDA_PATH}")
print(f"[Doguda Debug] CWD: {os.getcwd()}")

if DOGUDA_PATH:
    sys.path.insert(0, DOGUDA_PATH)
elif os.getcwd() not in sys.path:
     print(f"[Doguda Debug] Adding CWD to sys.path: {os.getcwd()}")
     sys.path.insert(0, os.getcwd())

print(f"[Doguda Debug] sys.path[0]: {sys.path[0]}")

cli = typer.Typer(help="Expose @doguda functions over CLI and HTTP.")
exec_cli = typer.Typer(help="Execute registered @doguda commands.")
# We don't add exec_cli immediately because we need to discover commands first at runtime
# or we just use a dynamic command for 'exec' that does the lookup.
# Actually, the original code used 'cli.add_typer(exec_cli, name="exec")' which registers subcommands.
# But 'exec' was also a command group? No, "cli.add_typer(exec_cli, name='exec')" makes 'doguda exec' a group.
# But we can't pre-register commands if we don't know them until runtime and we want to allow 
# running without specifying module in arguments (so discovery happens inside the command execution).
# 
# However, Typer builds the CLI at import/definition time usually.
# If we want 'doguda exec <cmd_name>', we can make 'exec' a command that takes a 'command_name' argument?
# OR we continue to use add_typer but we populate it dynamically? 
# Typer doesn't easily support dynamic commands added *after* the app is defined if we want them to show in help 
# before running.
# BUT, the request says "DOGUDA_PATH에 있는 App들을 모두 찾은다음에... command를 어떻게 찾을지는 너가 잘 생각해서 행동해봐".
#
# Strategy:
# 1. 'serve' and 'list' are static commands. They do discovery when run.
# 2. 'exec' can be a command that takes the target command name as an argument.
#    e.g. `doguda exec <command_name> [args]...` 
#    But passing args to the inner command is tricky with Typer if we don't define the signature.
#
# Alternative Strategy (preserving `doguda exec cmd --arg val`):
# Only discovery during `main()` execution.
# scan apps -> register commands to exec_cli -> then run cli().
# This might be slow if there are many files, but it's "auto discovery".
# Let's try this approach: Discover at startup of CLI.

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
    # This allows `doguda exec hello --name world` to work with proper help generation
    _load_apps()
    
    if discovered_apps:
        # Register commands to exec_cli
        # We need to handle duplicates in exec_cli
        # If duplicates exist, we might namespace them or just fail on ambiguous call?
        # Typer needs unique command names.
        
        # We will register them. If name collision, we might prefix with module name?
        # e.g. 'exec hello' AND 'exec other_module:hello'?
        # For simplicity, we register straightforwardly. If collision, last one wins (or we skip).
        # We'll detect collisions and maybe register an error-command?
        
        # Actually, let's register all unique commands. 
        # If there's a collision, we can't easily support both under the same name.
        # We will check for collisions first.
        
        params_map = {} # name -> function
        
        for mod_name, app in discovered_apps.items():
            for name, fn in app.registry.items():
                if name in params_map:
                    # Collision
                    existing_mod = params_map[name][1]
                    # We can't register simple name. 
                    # We could register 'mod:name' for both?
                    # For now, just print warning and maybe don't register the second one?
                    # Or register with module prefix?
                    continue
                params_map[name] = (fn, mod_name)
        
        # Reregister
        for mod_name, app in discovered_apps.items():
             app.register_cli_commands(exec_cli)
             
    cli.add_typer(exec_cli, name="exec")
    cli()


if __name__ == "__main__":
    main()
