## Dogu quickstart

Define your commands in `dogu_app.py` so the `dogu` CLI can find them:

```python
# dogu_app.py
from dogu import DoguApp, UResponse, doguda

app = DoguApp()


@doguda  # registers on the default Dogu app
async def url_to_markdown(url: str) -> UResponse:
    return UResponse(markdown=f"received: {url}")
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
