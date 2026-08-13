# fastapi-docs

An API console for FastAPI that groups your endpoints properly, sends real requests, and remembers the ids you are working with — across restarts.

```python
from fastapi import FastAPI
import fastapi_docs

app = FastAPI()
fastapi_docs.mount(app, path="/myapp")
```

Open `http://localhost:8000/myapp`.

## Why

Swagger UI sends requests but cannot group tags — a hundred endpoints arrive as one flat list. Redoc groups beautifully but is read-only, and silently *hides* any tag no group claimed. Neither remembers that every request you make needs the same `workspace_id`, and neither notices that the `run_id` you need was in the response you just got.

## What it does

**Groups tags, without losing any.** Reads `x-tagGroups`, OpenAPI 3.2 `parent` fields, or an explicit config. A tag no group claims goes to `Other` rather than disappearing.

```python
from fastapi_docs import TagGroup

fastapi_docs.mount(
    app,
    path="/myapp",
    groups=[
        TagGroup("Workspaces", ["workspaces", "invitations", "billing"]),
        TagGroup("Registry", ["models", "handlers"]),
        TagGroup("Lifecycle", ["experiments", "runs", "deployments"]),
    ],
)
```

**Sends real requests.** The console is served *by your app*, so requests are same-origin: no CORS, no proxy, real cookies and headers.

**Remembers values between restarts.** Pin `workspace_id` once and every operation taking one is pre-filled — this run, and next Tuesday. Pinned values live in a plain JSON file (`.fastapi-docs.json`) you can read, commit, or delete.

**Captures ids from responses.** With capture on, `POST /v1/runs` returning `{"id": "run_9"}` stores `run_id = run_9`, and the next operation needing a `run_id` already has it. The name comes from the path — `/v1/runs` is a collection of runs — because a variable called `id` is worthless two requests later.

Precedence is **pinned > captured > schema default > example**. A value you pinned deliberately is never overwritten by a response.

## Install

```bash
pip install fastapi-docs
```

## Configuration

```python
fastapi_docs.mount(
    app,
    path="/myapp",  # where the console is served
    groups=[...],  # overrides whatever the schema declares
    state_file=".fastapi-docs.json",  # pinned + captured values
    title="My API",  # defaults to app.title
    enabled=not settings.is_production,
)
```

### Do not ship it to production

The console writes to disk and exposes your whole surface with a send button. Gate it exactly like you gate `/docs`:

```python
fastapi_docs.mount(app, enabled=settings.environment != "production")
```

### Tokens

Bearer tokens are kept in the browser's `localStorage`, never in the state file — the file is meant to be committed, and a token is not.

## The state file

```json
{
  "version": 1,
  "capture": true,
  "pinned": { "workspace_id": "ws_1" },
  "captured": {
    "run_id": { "value": "run_9", "source": "POST /v1/runs", "at": "2026-08-12T09:31:04+00:00" }
  }
}
```

Commit it to share a team's defaults, or leave it gitignored for personal ones.

## Development

```bash
uv sync --group dev
uv run pytest
uv run uvicorn examples.demo:app --reload
```

## License

MIT
