from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Type, get_type_hints


import typer
from fastapi import FastAPI
from pydantic import BaseModel, create_model


@dataclass
class ProviderInfo:
    func: Callable[..., Any]
    return_type: Optional[Type[Any]]
    always: bool = False
    priority: int = 0


class DogudaApp:
    """Holds registered commands and builds CLI/FastAPI surfaces."""

    def __init__(self, name: str) -> None:
        self._registry: Dict[str, Callable[..., Any]] = {}
        self._providers: Dict[Type[Any], ProviderInfo] = {}
        self._always_providers: List[ProviderInfo] = []
        self.name = name

    def command(self, func: Optional[Callable[..., Any]] = None, *, name: Optional[str] = None):
        """Decorator to register a function as a Doguda command."""

        def decorator(fn: Callable[..., Any]):
            cmd_name = name or fn.__name__
            self._registry[cmd_name] = fn
            return fn

        if func is None:
            return decorator
        return decorator(func)

    # Alias to match the requested decorator name.
    doguda = command

    def provide(
        self,
        func: Optional[Callable[..., Any]] = None,
        *,
        always: bool = False,
        priority: int = 0,
    ):
        """Decorator to register a function as a dependency provider."""

        def decorator(fn: Callable[..., Any]):
            try:
                type_hints = get_type_hints(fn)
            except Exception:
                sig = inspect.signature(fn)
                return_type = sig.return_annotation
                if return_type is inspect._empty:
                    return_type = None
            else:
                return_type = type_hints.get("return")
                if return_type is type(None):
                    return_type = None

            if return_type is None and not always:
                raise ValueError(
                    f"Lazy provider '{fn.__name__}' must have a return type hint. "
                    "Only 'always=True' providers can omit the return type hint (for side-effects)."
                )

            info = ProviderInfo(func=fn, return_type=return_type, always=always, priority=priority)

            if return_type is not None:
                self._providers[return_type] = info
            if always:
                self._always_providers.append(info)

            return fn

        if func is None:
            return decorator
        return decorator(func)

    @property
    def registry(self) -> Dict[str, Callable[..., Any]]:
        return self._registry

    @property
    def providers(self) -> Dict[Type[Any], ProviderInfo]:
        return self._providers

    @property
    def always_providers(self) -> List[ProviderInfo]:
        return self._always_providers

    async def _resolve_dependencies(
        self,
        fn: Callable[..., Any],
        kwargs: Dict[str, Any],
        cache: Dict[Type[Any], Any],
        executed_always: Set[int],
    ) -> Dict[str, Any]:
        """Recursively resolve dependencies for a function."""
        sig = inspect.signature(fn)
        try:
            type_hints = get_type_hints(fn)
        except Exception:
            type_hints = {p.name: p.annotation for p in sig.parameters.values()}

        full_kwargs = kwargs.copy()
        for param_name, param in sig.parameters.items():
            if param_name in full_kwargs:
                continue

            annotation = type_hints.get(param_name, Any)
            if annotation in self._providers:
                if annotation not in cache:
                    info = self._providers[annotation]
                    provider = info.func
                    # Recursively resolve provider's own dependencies
                    provider_kwargs = await self._resolve_dependencies(
                        provider, {}, cache, executed_always
                    )
                    result = provider(**provider_kwargs)
                    if inspect.isawaitable(result):
                        result = await result
                    cache[annotation] = result
                    if info.always:
                        executed_always.add(id(info))
                full_kwargs[param_name] = cache[annotation]

        return full_kwargs

    def _build_request_model(self, name: str, fn: Callable[..., Any]) -> type[BaseModel]:
        sig = inspect.signature(fn)
        try:
            type_hints = get_type_hints(fn)
        except Exception:
            type_hints = {p.name: p.annotation for p in sig.parameters.values()}

        fields = {}
        for param_name, param in sig.parameters.items():
            annotation = type_hints.get(param_name, Any)

            # Skip the parameter if it's provided by a registered provider.
            if annotation in self._providers:
                continue

            field_annotation = annotation if annotation is not inspect._empty else Any
            default = param.default if param.default is not inspect._empty else ...
            fields[param.name] = (field_annotation, default)
        model = create_model(f"{name}_Payload", **fields)  # type: ignore[arg-type]
        return model

    async def execute_async(self, name: str, kwargs: Dict[str, Any]) -> Any:
        """Execute a registered command by name asynchronously."""
        if name not in self._registry:
            raise KeyError(f"Command '{name}' not found in app '{self.name}'")
        fn = self._registry[name]
        return await self._execute_async(fn, kwargs)

    def execute_sync(self, name: str, kwargs: Dict[str, Any]) -> Any:
        """Execute a registered command by name synchronously."""
        if name not in self._registry:
            raise KeyError(f"Command '{name}' not found in app '{self.name}'")
        fn = self._registry[name]
        return self._execute_sync(fn, kwargs)

    def _convert_params(self, fn: Callable[..., Any], kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Convert string arguments to the types expected by the function signature."""
        sig = inspect.signature(fn)
        try:
            type_hints = get_type_hints(fn)
        except Exception:
            type_hints = {p.name: p.annotation for p in sig.parameters.values()}

        converted = kwargs.copy()
        for name, value in converted.items():
            if name not in sig.parameters:
                continue
            
            param = sig.parameters[name]
            annotation = type_hints.get(name, param.annotation)
            
            if annotation in (inspect._empty, Any):
                continue
            
            if isinstance(value, str):
                try:
                    if annotation is int:
                        converted[name] = int(value)
                    elif annotation is float:
                        converted[name] = float(value)
                    elif annotation is bool:
                        converted[name] = value.lower() in ("true", "1", "yes", "on")
                    elif hasattr(annotation, "__origin__") and annotation.__origin__ is list:
                        # Simple comma-separated list support
                        item_type = annotation.__args__[0] if annotation.__args__ else str
                        converted[name] = [item_type(x.strip()) for x in value.split(",")]
                except (ValueError, TypeError) as e:
                    raise ValueError(f"Failed to convert parameter '{name}' to {annotation.__name__ if hasattr(annotation, '__name__') else annotation}: {value}") from e
        return converted

    async def _execute_async(self, fn: Callable[..., Any], kwargs: Dict[str, Any]) -> Any:
        cache: Dict[Type[Any], Any] = {}
        executed_always: Set[int] = set()

        # Type conversion for input kwargs (especially for CLI strings)
        kwargs = self._convert_params(fn, kwargs)

        # Execute 'always' providers first, sorted by priority (higher first)
        sorted_always = sorted(self._always_providers, key=lambda x: x.priority, reverse=True)
        for p in sorted_always:
            # If it has a return type and is already in cache, it was executed
            if p.return_type is not None and p.return_type in cache:
                continue

            # If it's a side-effect only provider (None), we still only want to run it once
            if id(p) in executed_always:
                continue

            p_kwargs = await self._resolve_dependencies(p.func, {}, cache, executed_always)
            res = p.func(**p_kwargs)
            if inspect.isawaitable(res):
                res = await res

            executed_always.add(id(p))
            if p.return_type is not None:
                cache[p.return_type] = res

        full_kwargs = await self._resolve_dependencies(fn, kwargs, cache, executed_always)
        result = fn(**full_kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    def _execute_sync(self, fn: Callable[..., Any], kwargs: Dict[str, Any]) -> Any:
        # Type conversion for input kwargs (especially for CLI strings)
        kwargs = self._convert_params(fn, kwargs)
        
        cache: Dict[Type[Any], Any] = {}
        executed_always: Set[int] = set()

        async def _run():
            # Execute 'always' providers first, sorted by priority (higher first)
            sorted_always = sorted(self._always_providers, key=lambda x: x.priority, reverse=True)
            for p in sorted_always:
                if p.return_type is not None and p.return_type in cache:
                    continue
                if id(p) in executed_always:
                    continue

                p_kwargs = await self._resolve_dependencies(p.func, {}, cache, executed_always)
                res = p.func(**p_kwargs)
                if inspect.isawaitable(res):
                    res = await res

                executed_always.add(id(p))
                if p.return_type is not None:
                    cache[p.return_type] = res

            full_kwargs = await self._resolve_dependencies(fn, kwargs, cache, executed_always)
            result = fn(**full_kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        return asyncio.run(_run())

    def build_fastapi(self, prefix: str = "/v1/doguda") -> FastAPI:
        api = FastAPI()
        for name, fn in self._registry.items():
            payload_model = self._build_request_model(name, fn)
            response_model = self._resolve_response_model(fn)

            api.post(f"{prefix}/{name}", response_model=response_model)(
                self._build_endpoint(fn, payload_model, response_model)
            )
        return api

    def _build_endpoint(
        self,
        fn: Callable[..., Any],
        payload_model: type[BaseModel],
        response_model: Optional[Any],
    ):
        async def endpoint(payload: payload_model):  # type: ignore[name-defined]
            data = payload.model_dump()
            return await self._execute_async(fn, data)

        # FastAPI inspects annotations; ensure it sees the real class, not a forward ref string.
        endpoint.__annotations__ = {"payload": payload_model}
        if response_model is not None:
            endpoint.__annotations__["return"] = response_model
        return endpoint

    def _resolve_response_model(self, fn: Callable[..., Any]) -> Optional[Any]:
        """
        Use the original function's return annotation as the FastAPI response model.
        """
        try:
            annotation = get_type_hints(fn).get("return", inspect._empty)
        except Exception:
            annotation = inspect.signature(fn).return_annotation

        if annotation in (inspect._empty, None, type(None)):
            return None
        return annotation

    def register_cli_commands(self, app: typer.Typer) -> None:
        for name, fn in self._registry.items():
            wrapper = self._build_cli_wrapper(fn)
            wrapper.__name__ = name
            wrapper.__doc__ = fn.__doc__

            # Filter signature to exclude dependencies provided by @provide
            sig = inspect.signature(fn)
            try:
                type_hints = get_type_hints(fn)
            except Exception:
                type_hints = {p.name: p.annotation for p in sig.parameters.values()}

            new_params = []
            for param in sig.parameters.values():
                annotation = type_hints.get(param.name, Any)
                if annotation not in self._providers:
                    new_params.append(param)

            wrapper.__signature__ = sig.replace(parameters=new_params) # type: ignore[attr-defined]
            # Annotations help Typer with types, filter them too.
            wrapper.__annotations__ = {
                k: v for k, v in type_hints.items() if k != "return" and v not in self._providers
            }
            app.command(name)(wrapper)

    def _build_cli_wrapper(self, fn: Callable[..., Any]):
        def _sync_wrapper(**kwargs):
            result = self._execute_sync(fn, kwargs)
            self._echo_result(result)

        return _sync_wrapper

    def _echo_result(self, result: Any) -> None:
        if isinstance(result, BaseModel):
            typer.echo(result.model_dump_json(indent=2))
            return
        if isinstance(result, (dict, list, tuple)):
            typer.echo(json.dumps(result, indent=2, default=str))
            return
        typer.echo(result)


