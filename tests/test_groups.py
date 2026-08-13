"""The sidebar is built from tags, and the failure that matters is silent."""

from fastapi_docs.groups import UNGROUPED, TagGroup, resolve_groups, tags_in_use


def schema(*tags: str, declared: list[dict] | None = None, extension: list[dict] | None = None) -> dict:
    document: dict = {
        "paths": {f"/{tag}": {"get": {"tags": [tag]}} for tag in tags},
    }
    if declared is not None:
        document["tags"] = declared
    if extension is not None:
        document["x-tagGroups"] = extension
    return document


def test_a_tag_no_group_claims_is_still_reachable() -> None:
    # Redoc drops it. In a console you use to call endpoints, a whole router
    # quietly disappearing is the worst thing this could do.
    groups = resolve_groups(schema("models", "handlers", "workers"), [TagGroup("Registry", ["models", "handlers"])])

    assert groups == [{"name": "Registry", "tags": ["models", "handlers"]}, {"name": UNGROUPED, "tags": ["workers"]}]


def test_every_tag_lands_in_exactly_one_section() -> None:
    groups = resolve_groups(schema("models", "runs"), [TagGroup("Registry", ["models", "runs"]), TagGroup("Lifecycle", ["runs"])])

    placements = [tag for group in groups for tag in group["tags"]]

    assert sorted(placements) == ["models", "runs"], "a tag claimed twice keeps its first claim"


def test_a_group_that_outlived_its_routes_is_dropped() -> None:
    groups = resolve_groups(schema("models"), [TagGroup("Registry", ["models"]), TagGroup("Fleet", ["workers"])])

    assert groups == [{"name": "Registry", "tags": ["models"]}]


def test_the_extension_is_read_when_nothing_is_configured() -> None:
    document = schema("models", "handlers", extension=[{"name": "Registry", "tags": ["models", "handlers"]}])

    assert resolve_groups(document) == [{"name": "Registry", "tags": ["models", "handlers"]}]


def test_openapi_32_parents_build_the_same_tree() -> None:
    document = schema(
        "models",
        "handlers",
        declared=[
            {"name": "Registry", "kind": "nav"},
            {"name": "models", "parent": "Registry"},
            {"name": "handlers", "parent": "Registry"},
        ],
    )

    assert resolve_groups(document) == [{"name": "Registry", "tags": ["models", "handlers"]}]


def test_configuration_wins_over_what_the_document_declares() -> None:
    document = schema("models", "handlers", extension=[{"name": "Everything", "tags": ["models", "handlers"]}])

    groups = resolve_groups(document, [TagGroup("Registry", ["models"])])

    assert groups == [{"name": "Registry", "tags": ["models"]}, {"name": UNGROUPED, "tags": ["handlers"]}]


def test_declared_order_leads_and_undeclared_tags_follow() -> None:
    document = schema("beta", "alpha", declared=[{"name": "alpha"}])

    # The document's own array is the author's reading order; anything only an
    # operation mentions is appended rather than sorted in.
    assert tags_in_use(document) == ["alpha", "beta"]


def test_an_untagged_api_still_renders() -> None:
    assert resolve_groups({"paths": {"/health": {"get": {}}}}) == []
