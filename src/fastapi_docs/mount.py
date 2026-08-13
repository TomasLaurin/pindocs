"""Attaching the console to an app.

    import fastapi_docs
    fastapi_docs.mount(app, path="/myapp")

Everything the console needs is served from that one prefix, and the requests it
sends go straight from the browser to the app's own routes. That is the whole
reason this is a *mounted* console rather than a standalone viewer: same origin
means no CORS, no proxy in the middle rewriting things, and the cookies and
headers you are debugging are the real ones.

The console is a development affordance and writes to disk. Gate it the way you
already gate ``/docs`` — see the ``enabled`` argument.
"""

from __future__ import annotations

import mimetypes
from importlib import resources
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from fastapi_docs.capture import parameter_names, variables_from_response
from fastapi_docs.groups import TagGroup, resolve_groups
from fastapi_docs.state import StateStore

DEFAULT_PATH = "/console"
DEFAULT_STATE_FILE = ".fastapi-docs.json"

_ASSETS = {"console.js", "console.css"}


def _asset(name: str) -> str:
    return resources.files("fastapi_docs").joinpath("static", name).read_text(encoding="utf-8")


def mount(
    app: FastAPI,
    *,
    path: str = DEFAULT_PATH,
    groups: list[TagGroup] | None = None,
    state_file: str | Path = DEFAULT_STATE_FILE,
    title: str | None = None,
    theme: str | None = None,
    enabled: bool = True,
) -> None:
    """Serve the console at ``path`` on ``app``.

    ``groups`` overrides whatever the schema declares; leave it out and the
    document's own ``x-tagGroups`` (or OpenAPI 3.2 ``parent`` fields) are used.
    ``state_file`` is where pinned and captured values live between restarts —
    a normal file you can read, commit, or delete.

    ``theme`` is CSS appended after the console's own, for a host application
    that wants the console to look like the rest of it. Every colour, size and
    radius is a ``--fd-`` custom property, so restyling is a block of variables
    rather than a fork:

        fastapi_docs.mount(app, theme=":root { --fd-primary: #7c3aed }")

    ``enabled=False`` makes this a no-op, so the call can stay unconditional at
    the call site and the decision can live in settings:

        fastapi_docs.mount(app, enabled=not settings.is_production)
    """
    if not enabled:
        return

    prefix = "/" + path.strip("/")
    store = StateStore(Path(state_file))
    router = APIRouter()

    @router.get(prefix, include_in_schema=False)
    async def console() -> HTMLResponse:
        page = _asset("index.html")
        page = page.replace("__FASTAPI_DOCS_BASE__", prefix)
        page = page.replace("__FASTAPI_DOCS_TITLE__", title or app.title or "API console")
        page = page.replace("__FASTAPI_DOCS_THEME__", f"<style>{theme}</style>" if theme else "")
        return HTMLResponse(page, headers={"cache-control": "no-store"})

    @router.get(prefix + "/assets/{name}", include_in_schema=False)
    async def asset(name: str) -> Response:
        if name not in _ASSETS:
            return Response(status_code=404)
        media_type = mimetypes.guess_type(name)[0] or "text/plain"
        return Response(_asset(name), media_type=media_type, headers={"cache-control": "no-store"})

    @router.get(prefix + "/spec", include_in_schema=False)
    async def spec() -> JSONResponse:
        """The app's own document, plus the grouping the console renders from.

        Resolved here rather than in the browser so there is one implementation
        of "which section does this tag belong to", and it is the tested one.
        """
        schema = dict(app.openapi())
        schema["x-tagGroups"] = resolve_groups(schema, groups)
        return JSONResponse(schema, headers={"cache-control": "no-store"})

    @router.get(prefix + "/state", include_in_schema=False)
    async def read_state() -> JSONResponse:
        return JSONResponse(store.load())

    @router.put(prefix + "/state", include_in_schema=False)
    async def write_state(request: Request) -> JSONResponse:
        return JSONResponse(store.save(await request.json()))

    @router.post(prefix + "/capture", include_in_schema=False)
    async def capture(request: Request) -> JSONResponse:
        """Fold a response's ids into the store.

        The browser posts back what it received rather than extracting the
        values itself: the naming rules are the subtle part, and they belong
        somewhere a unit test can reach them.
        """
        payload: dict[str, Any] = await request.json()
        state = store.load()
        if not state["capture"]:
            return JSONResponse(state)

        variables = variables_from_response(
            payload.get("path", ""), payload.get("body"), known_parameters=parameter_names(app.openapi())
        )
        if not variables:
            return JSONResponse(state)
        return JSONResponse(store.merge_captured(variables, source=payload.get("operation", "")))

    app.include_router(router, include_in_schema=False)
