## Doguda quickstart

Define your commands in `doguda_app.py` so the `doguda` CLI can find them:

```python
# doguda_app.py
from pydantic import BaseModel

from doguda import DogudaApp, doguda


class UrlToMarkdownResponse(BaseModel):
    markdown: str


app = DogudaApp()


@doguda  # registers on the default Doguda app
async def url_to_markdown(url: str) -> UrlToMarkdownResponse:
    return UrlToMarkdownResponse(markdown=f"received: {url}")

# Doguda will use your function's return annotation as the FastAPI response model,
# so you can shape responses with your own Pydantic models.
```

### CLI

```bash
doguda url_to_markdown --url "https://example.com"
```

Set a different module with `DOGUDA_MODULE=my_module` or `--module my_module`.

### HTTP

Start the FastAPI server (defaults to `doguda_app` in the current directory):

```bash
doguda serve
```

Then POST to your function at `/v1/doguda/<function_name>`:

```bash
curl -X POST http://localhost:8000/v1/doguda/url_to_markdown \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

### Organizing commands in a package

You can also make `doguda_app` a package to auto-load submodules that register commands:

```
doguda_app/
  __init__.py
  urls.py       # contains @doguda functions
  reports.py    # contains @doguda functions
```

The loader imports all submodules, so any `@doguda` usages inside `doguda_app/*` are registered without extra wiring. Keep `DOGUDA_MODULE=doguda_app` (or `--module doguda_app`) and run `doguda serve` or `doguda <command>` as usual.

### Running with uv (and flox)

If you're using `uv` from the flox env, activate it (or prefix with `flox run`) and keep the cache inside the repo to avoid permission issues:

```bash
UV_CACHE_DIR=$PWD/.flox/cache/uv uv run python -m doguda serve --module doguda_app
```
