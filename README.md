# pindocs

An API console for FastAPI that groups your endpoints properly, sends real requests, and remembers the ids you are working with — across restarts.

```python
from fastapi import FastAPI
import pindocs

app = FastAPI()
pindocs.mount(app)
```

Open `http://localhost:8000/pindocs`.

![The console: grouped operations, a request pre-filled from pinned values, and the variables rail](https://raw.githubusercontent.com/TomasLaurin/fastapi_docs/main/docs/screenshot.png)

## Why

Swagger UI sends requests but cannot group tags — a hundred endpoints arrive as one flat list. Redoc groups beautifully but is read-only, and silently *hides* any tag no group claimed. Neither remembers that every request you make needs the same `workspace_id`, and neither notices that the `run_id` you need was in the response you just got.

## What it does

**Groups tags, without losing any.** Reads `x-tagGroups`, OpenAPI 3.2 `parent` fields, or an explicit config. A tag no group claims goes to `Other` rather than disappearing.

```python
from pindocs import TagGroup

pindocs.mount(
    app,
    groups=[
        TagGroup("Workspaces", ["workspaces", "invitations", "billing"]),
        TagGroup("Registry", ["models", "handlers"]),
        TagGroup("Lifecycle", ["experiments", "runs", "deployments"]),
    ],
)
```

**Sends real requests.** The console is served *by your app*, so requests are same-origin: no CORS, no proxy, real cookies and headers.

**Remembers values between restarts.** Pin `workspace_id` once and every operation taking one is pre-filled — this run, and next Tuesday. Pinned values live in a plain JSON file (`.pindocs.json`) you can read, commit, or delete.

**Captures ids from responses.** With capture on, `POST /v1/runs` returning `{"id": "run_9"}` stores `run_id = run_9`, and the next operation needing a `run_id` already has it. The name comes from the path — `/v1/runs` is a collection of runs — because a variable called `id` is worthless two requests later.

**Lets you curate the rail.** Every captured value has its own ✕ — drop the one stale id without losing the rest. `Clear captured` empties the whole set and always asks first. Pinned values are touched by neither; unpin removes them the same way, one at a time.

Precedence is **pinned > captured > schema default > example**. A value you pinned deliberately is never overwritten by a response.

## Install

```bash
pip install pindocs
```

```bash
uv add --group dev pindocs
```

## Configuration

```python
pindocs.mount(
    app,
    path="/pindocs",  # where the console is served
    groups=[...],  # overrides whatever the schema declares
    state_file=".pindocs.json",  # pinned + captured values
    title="My API",  # defaults to app.title
    theme=":root { --pd-primary: #7c3aed }",  # every colour/size/radius is a --pd-* variable
    enabled=not settings.is_production,
)
```

### Do not ship it to production

The console writes to disk and exposes your whole surface with a send button. Gate it exactly like you gate `/docs`:

```python
pindocs.mount(app, enabled=settings.environment != "production")
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
uv run uvicorn examples.demo:app --reload   # → http://localhost:8000/pindocs
```

## Releasing

A `v*` tag publishes to PyPI through `.github/workflows/publish.yml` (uv build + PyPI trusted publishing — no token in the repository):

```bash
git tag v0.1.0 && git push origin v0.1.0
```

## License

MIT
