"""The integration: one call, and the console is there."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import pindocs
from pindocs import TagGroup


@pytest.fixture
def app(tmp_path) -> FastAPI:
    application = FastAPI(title="Demo")

    @application.post("/v1/runs", tags=["runs"])
    async def create_run() -> dict:
        return {"id": "run_9"}

    @application.get("/v1/models", tags=["models"])
    async def list_models() -> list:
        return []

    pindocs.mount(
        application,
        path="/myapp",
        groups=[TagGroup("Lifecycle", ["runs"]), TagGroup("Registry", ["models"])],
        state_file=tmp_path / "state.json",
    )
    return application


def test_the_console_is_served_where_it_was_mounted(app) -> None:
    response = TestClient(app).get("/myapp")

    assert response.status_code == 200
    assert "console.js" in response.text
    assert "/myapp/assets/console.js" in response.text, "the base path has to be baked in, not guessed"


def test_the_assets_are_served_and_nothing_else_is(app) -> None:
    client = TestClient(app)

    assert client.get("/myapp/assets/console.js").status_code == 200
    assert client.get("/myapp/assets/console.css").status_code == 200
    assert client.get("/myapp/assets/../../etc/passwd").status_code == 404


def test_the_spec_carries_the_grouping(app) -> None:
    spec = TestClient(app).get("/myapp/spec").json()

    assert spec["x-tagGroups"] == [{"name": "Lifecycle", "tags": ["runs"]}, {"name": "Registry", "tags": ["models"]}]


def test_the_console_does_not_document_itself(app) -> None:
    paths = TestClient(app).get("/openapi.json").json()["paths"]

    assert not [path for path in paths if path.startswith("/myapp")]


def test_a_response_becomes_a_variable_the_next_request_can_use(app) -> None:
    client = TestClient(app)

    created = client.post("/v1/runs").json()
    state = client.post("/myapp/capture", json={"operation": "POST /v1/runs", "path": "/v1/runs", "body": created}).json()

    assert state["captured"]["run_id"]["value"] == "run_9"
    assert client.get("/myapp/state").json()["captured"]["run_id"]["value"] == "run_9"


def test_deleting_one_captured_value_keeps_the_rest(app) -> None:
    """The rail's per-item delete writes the state back minus exactly one name."""
    client = TestClient(app)
    client.post("/myapp/capture", json={"operation": "POST /v1/runs", "path": "/v1/runs", "body": {"id": "run_9"}})
    client.post("/myapp/capture", json={"operation": "GET /v1/models", "path": "/v1/models", "body": {"id": "model_1"}})

    state = client.get("/myapp/state").json()
    del state["captured"]["run_id"]
    saved = client.put("/myapp/state", json=state).json()

    assert "run_id" not in saved["captured"]
    assert saved["captured"]["model_id"]["value"] == "model_1"
    assert client.get("/myapp/state").json()["captured"].keys() == {"model_id"}


def test_capture_off_means_nothing_is_written(app) -> None:
    client = TestClient(app)
    client.put("/myapp/state", json={"capture": False})

    client.post("/myapp/capture", json={"operation": "POST /v1/runs", "path": "/v1/runs", "body": {"id": "run_9"}})

    assert client.get("/myapp/state").json()["captured"] == {}


def test_pinned_values_survive_a_restart(app, tmp_path) -> None:
    TestClient(app).put("/myapp/state", json={"pinned": {"workspace_id": "ws_1"}})

    # A brand new app object on the same state file is the restart.
    restarted = FastAPI()
    pindocs.mount(restarted, path="/myapp", state_file=tmp_path / "state.json")

    assert TestClient(restarted).get("/myapp/state").json()["pinned"] == {"workspace_id": "ws_1"}


def test_the_default_path_is_pindocs(tmp_path) -> None:
    application = FastAPI()
    pindocs.mount(application, state_file=tmp_path / "state.json")

    assert TestClient(application).get("/pindocs").status_code == 200


def test_disabled_mounts_nothing(tmp_path) -> None:
    application = FastAPI()
    pindocs.mount(application, path="/myapp", enabled=False, state_file=tmp_path / "state.json")

    assert TestClient(application).get("/myapp").status_code == 404
