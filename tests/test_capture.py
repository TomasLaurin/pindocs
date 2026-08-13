"""Naming is the whole problem: a bare ``id`` is useless two requests later."""

from fastapi_docs.capture import parameter_names, resource_from_path, singular, variables_from_response


def test_a_bare_id_is_named_after_the_collection_it_came_from() -> None:
    assert variables_from_response("/v1/runs", {"id": "run_9"}) == {"run_id": "run_9"}


def test_ids_that_already_carry_their_name_keep_it() -> None:
    body = {"id": "run_9", "project_id": "proj_1", "workspace_id": "ws_2"}

    assert variables_from_response("/v1/runs", body) == {
        "run_id": "run_9",
        "project_id": "proj_1",
        "workspace_id": "ws_2",
    }


def test_the_collection_is_read_past_templated_segments() -> None:
    # The id belongs to the thing being created, not to the project it hangs off.
    assert variables_from_response("/v1/projects/{project_id}/runs", {"id": "run_9"}) == {"run_id": "run_9"}


def test_a_verb_suffix_does_not_become_the_resource() -> None:
    assert resource_from_path("/v1/runs/{run_id}/metrics:query") == "metric"


def test_a_version_prefix_names_nothing() -> None:
    assert resource_from_path("/v1/{id}") is None


def test_a_listing_offers_its_first_element() -> None:
    body = [{"id": "run_9"}, {"id": "run_8"}]

    assert variables_from_response("/v1/runs", body) == {"run_id": "run_9"}


def test_an_envelope_is_peeled() -> None:
    body = {"items": [{"id": "run_9"}], "total": 2}

    assert variables_from_response("/v1/runs", body) == {"run_id": "run_9"}


def test_a_resource_that_merely_owns_a_data_field_is_not_peeled() -> None:
    body = {"id": "model_1", "data": {"id": "something_else"}}

    assert variables_from_response("/v1/models", body) == {"model_id": "model_1"}


def test_non_ids_are_taken_only_when_the_api_accepts_them_by_that_name() -> None:
    body = {"id": "run_9", "status": "running", "notes": "a long human sentence"}

    assert variables_from_response("/v1/runs", body, known_parameters={"status"}) == {
        "run_id": "run_9",
        "status": "running",
    }


def test_values_that_are_not_scalars_are_left_alone() -> None:
    body = {"id": "run_9", "config_id": {"nested": 1}, "ok_id": True, "missing_id": None}

    assert variables_from_response("/v1/runs", body) == {"run_id": "run_9"}


def test_a_body_that_is_not_an_object_captures_nothing() -> None:
    assert variables_from_response("/v1/runs", "just a string") == {}
    assert variables_from_response("/v1/runs", None) == {}
    assert variables_from_response("/v1/runs", []) == {}


def test_singular_covers_the_shapes_real_paths_use() -> None:
    assert [singular(word) for word in ("runs", "entries", "statuses", "boxes", "batches")] == [
        "run",
        "entry",
        "status",
        "box",
        "batch",
    ]


def test_a_segment_that_merely_ends_in_s_is_left_alone() -> None:
    # `/status` is a path, not a plural, and `statu_id` would read as a bug.
    assert [singular(word) for word in ("status", "address", "analysis", "chaos")] == [
        "status",
        "address",
        "analysis",
        "chaos",
    ]


def test_parameter_names_collects_what_the_api_addresses_things_by() -> None:
    schema = {
        "paths": {
            "/v1/runs": {
                "parameters": [{"name": "trace", "in": "header"}],
                "get": {"parameters": [{"name": "limit", "in": "query"}]},
            },
            "/v1/runs/{run_id}": {"get": {"parameters": [{"name": "run_id", "in": "path"}]}},
        }
    }

    assert parameter_names(schema) == {"limit", "run_id"}, "a header is not something you address a resource by"
