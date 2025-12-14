from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Optional

from .app import DogudaApp, default_app


def load_app_from_target(target: str, *, attribute: str = "app") -> DogudaApp:
    """
    Import a module and return a DogudaApp instance.
    The target can be "module" or "module:attribute".
    If no explicit DogudaApp is found, fall back to the default_app that decorators register to.
    """
    module_name, explicit_attr = _split_target(target, attribute)
    module = importlib.import_module(module_name)
    _import_submodules(module)
    app = _extract_app(module, explicit_attr)
    if app:
        return app
    if default_app.registry:
        return default_app
    raise RuntimeError(
        f"Could not find a DogudaApp in '{target}'. "
        "Expose a DogudaApp instance (e.g. 'app = DogudaApp()') or use the default @doguda decorator."
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
        importlib.import_module(name)


def _extract_app(module, attr_name: str) -> Optional[DogudaApp]:
    candidate = getattr(module, attr_name, None)
    if isinstance(candidate, DogudaApp):
        return candidate

    for _, value in inspect.getmembers(module):
        if isinstance(value, DogudaApp):
            return value
    return None
