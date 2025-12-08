from __future__ import annotations

import importlib
import inspect
from typing import Optional

from .app import DoguApp, default_app


def load_app_from_target(target: str, *, attribute: str = "app") -> DoguApp:
    """
    Import a module and return a DoguApp instance.
    The target can be "module" or "module:attribute".
    If no explicit DoguApp is found, fall back to the default_app that decorators register to.
    """
    module_name, explicit_attr = _split_target(target, attribute)
    module = importlib.import_module(module_name)
    app = _extract_app(module, explicit_attr)
    if app:
        return app
    if default_app.registry:
        return default_app
    raise RuntimeError(
        f"Could not find a DoguApp in '{target}'. "
        "Expose a DoguApp instance (e.g. 'app = DoguApp()') or use the default @doguda decorator."
    )


def _split_target(target: str, default_attr: str) -> tuple[str, str]:
    if ":" in target:
        module_name, attr = target.split(":", 1)
        return module_name, attr or default_attr
    return target, default_attr


def _extract_app(module, attr_name: str) -> Optional[DoguApp]:
    candidate = getattr(module, attr_name, None)
    if isinstance(candidate, DoguApp):
        return candidate

    for _, value in inspect.getmembers(module):
        if isinstance(value, DoguApp):
            return value
    return None
