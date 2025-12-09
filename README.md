## Dogu quickstart

Define your commands in `dogu_app.py` so the `dogu` CLI can find them:

```python
# dogu_app.py
from pydantic import BaseModel

from dogu import DoguApp, doguda


class UrlToMarkdownResponse(BaseModel):
    markdown: str


app = DoguApp()


@doguda  # registers on the default Dogu app
async def url_to_markdown(url: str) -> UrlToMarkdownResponse:
    return UrlToMarkdownResponse(markdown=f"received: {url}")

# Dogu will use your function's return annotation as the FastAPI response model,
# so you can shape responses with your own Pydantic models.
```

### CLI

```bash
dogu url_to_markdown --url "https://example.com"
```

Set a different module with `DOGU_MODULE=my_module` or `--module my_module`.

### HTTP

Start the FastAPI server (defaults to `dogu_app` in the current directory):

```bash
dogu serve
```

Then POST to your function at `/v1/dogu/<function_name>`:

```bash
curl -X POST http://localhost:8000/v1/dogu/url_to_markdown \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

### Organizing commands in a package

You can also make `dogu_app` a package to auto-load submodules that register commands:

```
dogu_app/
  __init__.py
  urls.py       # contains @doguda functions
  reports.py    # contains @doguda functions
```

The loader imports all submodules, so any `@doguda` usages inside `dogu_app/*` are registered without extra wiring. Keep `DOGU_MODULE=dogu_app` (or `--module dogu_app`) and run `dogu serve` or `dogu <command>` as usual.

### Running with uv (and flox)

If you're using `uv` from the flox env, activate it (or prefix with `flox run`) and keep the cache inside the repo to avoid permission issues:

```bash
UV_CACHE_DIR=$PWD/.flox/cache/uv uv run python -m dogu.runner serve --module dogu_app
```
