from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Optional

from .app import DogudaApp


from pathlib import Path
from typing import Dict, List


def discover_apps(search_path: Path) -> Dict[str, DogudaApp]:
    """
    Scan the search_path for potential Doguda modules and load any DogudaApp instances found.
    Returns a dictionary mapping module names to DogudaApp instances.
    """
    apps: Dict[str, DogudaApp] = {}
    

    if not search_path.exists():
        return apps
        
    candidate_modules = _find_candidate_modules(search_path)

    
    for mod_name in candidate_modules:
        try:
            # We use load_app_from_target which handles import and extraction
            # But we need to handle the case where it fails gracefully here
            module = importlib.import_module(mod_name)
            # Recursively import submodules if it's a package
            _import_submodules(module)
            
            # Use the existing extraction logic
            # We try 'app' attribute first, then search
            app = _extract_app(module, "app")
            if app:
                apps[mod_name] = app

        except (ImportError, RuntimeError, Exception) as e:
            # Discovery should be loose; if a module is broken or not a doguda app, skip it.
            continue
            
    return apps


def _find_candidate_modules(base_dir: Path) -> List[str]:
    """
    Find python modules (files) in the base_dir recursively.
    Returns a list of dotted module names (e.g. 'my_script', 'my_pkg.submod').
    """
    return _recursive_find(base_dir, "")


def _recursive_find(path: Path, prefix: str) -> List[str]:
    candidates = []
    
    if not path.is_dir():
        return candidates

    for item in path.iterdir():
        # Skip hidden files/dirs and explicitly excluded names, BUT allow __init__.py
        if item.name.startswith((".", "_")) and item.name != "__init__.py":
            continue
        if item.name == "setup.py":
            continue
            
        if item.is_dir():
             # Recurse into directory
             # Ensure directory name is a valid identifier to be part of module path
             if not item.name.isidentifier():
                 continue
                 
             new_prefix = f"{prefix}{item.name}."
             candidates.extend(_recursive_find(item, new_prefix))
             
        elif item.is_file() and item.suffix == ".py":
            if item.name == "__init__.py":
                # It represents the package itself.
                # Remove the trailing dot from prefix if present
                mod_name = prefix.rstrip(".")
                if mod_name:
                    candidates.append(mod_name)
            else:
                candidates.append(f"{prefix}{item.stem}")
            
    # Sort for deterministic order at this level
    candidates.sort()
    return candidates


def load_app_from_target(target: str, *, attribute: str = "app") -> DogudaApp:
    """
    Import a module and return a DogudaApp instance.
    The target can be "module" or "module:attribute".
    """
    module_name, explicit_attr = _split_target(target, attribute)
    module = importlib.import_module(module_name)
    _import_submodules(module)
    app = _extract_app(module, explicit_attr)
    if app:
        return app
    raise RuntimeError(
        f"Could not find a DogudaApp in '{target}'. "
        "Expose a DogudaApp instance (e.g. 'app = DogudaApp()')."
    )


def _split_target(target: str, default_attr: str) -> tuple[str, str]:
    if ":" in target:
        module_name, attr = target.split(":", 1)
        return module_name, attr or default_attr
    return target, default_attr


def _import_submodules(module) -> None:
    """Eagerly import submodules when the target is a package."""
    package_path = getattr(module, "__path__", None)
    if package_path is None:
        return
    prefix = module.__name__ + "."
    for finder, name, is_pkg in pkgutil.walk_packages(package_path, prefix):
        try:
            importlib.import_module(name)
        except Exception as e:
             # Just warn and continue, don't crash the whole app
            print(f"Warning: Failed to import submodule '{name}': {e}")


def _extract_app(module, attr_name: str) -> Optional[DogudaApp]:
    candidate = getattr(module, attr_name, None)
    if isinstance(candidate, DogudaApp):
        return candidate

    for _, value in inspect.getmembers(module):
        if isinstance(value, DogudaApp):
            return value
    return None
