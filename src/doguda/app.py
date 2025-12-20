from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any, Callable, Dict, Generic, Optional, Type, TypeVar, get_type_hints

TContext = TypeVar("TContext")


import typer
from fastapi import FastAPI
from pydantic import BaseModel, create_model


class DogudaApp(Generic[TContext]):
    """Holds registered commands and builds CLI/FastAPI surfaces."""

    def __init__(self, name: str, context: Optional[TContext] = None) -> None:
        self._registry: Dict[str, Callable[..., Any]] = {}
        self.name = name
        self.context = context


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

    @property
    def registry(self) -> Dict[str, Callable[..., Any]]:
        return self._registry

    def set_context(self, context: TContext) -> None:
        """Set the context instance for dependency injection."""
        self.context = context

    def _inject_context(self, fn: Callable[..., Any], kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Inject the context into the function arguments if requested by type hint."""
        if self.context is None:
            return kwargs

        full_kwargs = kwargs.copy()
        sig = inspect.signature(fn)
        try:
            type_hints = get_type_hints(fn)
        except Exception:
            type_hints = {p.name: p.annotation for p in sig.parameters.values()}

        for param_name, param in sig.parameters.items():
            if param_name in full_kwargs:
                continue

            annotation = type_hints.get(param_name, Any)
            if annotation is Any or annotation is inspect._empty:
                continue

            # Check if self.context is an instance of the annotated type.
            # We use a try-except to handle potential issues with complex annotations.
            try:
                if isinstance(self.context, annotation):
                    full_kwargs[param_name] = self.context
            except TypeError:
                # Some types (like Union or generics) might fail in isinstance
                # if not handled correctly. In those cases, we skip or do more complex check.
                pass

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

            # Skip the parameter if it's the context to be injected.
            if self.context is not None:
                try:
                    if isinstance(self.context, annotation):
                        continue
                except TypeError:
                    pass

            field_annotation = annotation if annotation is not inspect._empty else Any
            default = param.default if param.default is not inspect._empty else ...
            fields[param.name] = (field_annotation, default)
        model = create_model(f"{name}_Payload", **fields)  # type: ignore[arg-type]
        return model


    async def _execute_async(self, fn: Callable[..., Any], kwargs: Dict[str, Any]) -> Any:
        full_kwargs = self._inject_context(fn, kwargs)
        result = fn(**full_kwargs)
        if inspect.isawaitable(result):
            return await result
        return result


    def _execute_sync(self, fn: Callable[..., Any], kwargs: Dict[str, Any]) -> Any:
        full_kwargs = self._inject_context(fn, kwargs)
        if inspect.iscoroutinefunction(fn):
            return asyncio.run(fn(**full_kwargs))
        result = fn(**full_kwargs)
        if inspect.isawaitable(result):
            async def _wrapper():
                return await result

            return asyncio.run(_wrapper())
        return result


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
        Allows @doguda functions to define their own response schema instead of relying
        on a shared UResponse.
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
            wrapper.__signature__ = inspect.signature(fn)  # type: ignore[attr-defined]
            wrapper.__annotations__ = fn.__annotations__
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

