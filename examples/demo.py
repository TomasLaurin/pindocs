"""A small API that shows what the console is for.

    uv run uvicorn examples.demo:app --reload
    open http://localhost:8000/myapp

Create a run, and watch ``run_id`` appear in the rail — every operation that
takes one is pre-filled from then on, including after you restart the server.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel

import fastapi_docs
from fastapi_docs import TagGroup

app = FastAPI(title="Demo API")


class CreateRun(BaseModel):
    project_id: str
    name: str
    tags: list[str] = []


class Run(BaseModel):
    id: str
    project_id: str
    name: str
    status: str


RUNS: dict[str, Run] = {}


@app.post("/v1/projects/{project_id}/runs", tags=["runs"], summary="Start a run")
async def create_run(project_id: str, body: CreateRun) -> Run:
    run = Run(id=f"run_{uuid4().hex[:8]}", project_id=project_id, name=body.name, status="running")
    RUNS[run.id] = run
    return run


@app.get("/v1/runs/{run_id}", tags=["runs"], summary="Read a run")
async def read_run(run_id: str) -> Run | None:
    return RUNS.get(run_id)


@app.post("/v1/runs/{run_id}/finish", tags=["runs"], summary="Finish a run")
async def finish_run(run_id: str) -> Run | None:
    run = RUNS.get(run_id)
    if run:
        run.status = "finished"
    return run


@app.get("/v1/projects/{project_id}/models", tags=["models"], summary="List models")
async def list_models(project_id: str, limit: int = 20) -> list[dict]:
    return [{"id": "model_1", "project_id": project_id, "name": "resnet"}][:limit]


@app.get("/v1/workspaces", tags=["workspaces"], summary="List workspaces")
async def list_workspaces() -> list[dict]:
    return [{"id": "ws_1", "name": "Acme"}]


@app.get("/health", tags=["ops"], summary="Liveness")
async def health() -> dict[str, str]:
    return {"status": "ok"}


fastapi_docs.mount(
    app,
    path="/myapp",
    groups=[TagGroup("Lifecycle", ["runs"]), TagGroup("Registry", ["models"]), TagGroup("Account", ["workspaces"])],
)
