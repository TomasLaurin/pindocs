"""The file is meant to be hand-edited and committed, so it has to survive both."""

import json

from pindocs.state import StateStore


def store(tmp_path) -> StateStore:
    return StateStore(tmp_path / "state.json")


def test_values_outlive_the_process(tmp_path) -> None:
    store(tmp_path).save({"pinned": {"workspace_id": "ws_1"}})

    # A second store is the next `uvicorn` — same file, same values.
    assert store(tmp_path).load()["pinned"] == {"workspace_id": "ws_1"}


def test_a_pin_is_never_overwritten_by_a_response(tmp_path) -> None:
    state = store(tmp_path)
    state.save({"pinned": {"workspace_id": "ws_mine"}})

    state.merge_captured({"workspace_id": "ws_theirs", "run_id": "run_9"}, source="POST /v1/runs")

    remembered = state.load()
    assert remembered["pinned"]["workspace_id"] == "ws_mine"
    assert remembered["captured"]["run_id"]["value"] == "run_9"
    assert "workspace_id" not in remembered["captured"]


def test_the_newest_response_wins_among_captured(tmp_path) -> None:
    state = store(tmp_path)
    state.merge_captured({"run_id": "run_1"}, source="POST /v1/runs")
    state.merge_captured({"run_id": "run_2"}, source="POST /v1/runs")

    assert state.load()["captured"]["run_id"]["value"] == "run_2"


def test_where_a_value_came_from_is_remembered(tmp_path) -> None:
    state = store(tmp_path)
    state.merge_captured({"run_id": "run_1"}, source="POST /v1/runs")

    entry = state.load()["captured"]["run_id"]
    assert entry["source"] == "POST /v1/runs"
    assert entry["at"].startswith("20")


def test_a_hand_mangled_file_costs_you_the_bad_line_not_the_console(tmp_path) -> None:
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"pinned": {"good": "kept", "not a name!": "x", "blob": "y" * 5000}}))

    assert StateStore(path).load()["pinned"] == {"good": "kept"}


def test_unreadable_json_starts_clean_rather_than_raising(tmp_path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{ this is not json")

    assert StateStore(path).load() == {"version": 1, "capture": True, "pinned": {}, "captured": {}}


def test_a_missing_file_is_not_an_error(tmp_path) -> None:
    assert store(tmp_path).load()["pinned"] == {}


def test_values_are_stored_as_strings_because_they_go_into_urls(tmp_path) -> None:
    state = store(tmp_path)
    state.save({"pinned": {"limit": 50, "ratio": 1.5, "flag": True, "nothing": None}})

    assert state.load()["pinned"] == {"limit": "50", "ratio": "1.5"}


def test_writing_leaves_no_temp_files_behind(tmp_path) -> None:
    store(tmp_path).save({"pinned": {"a": "1"}})

    assert [path.name for path in tmp_path.iterdir()] == ["state.json"]
