"""Where an operation lands in the sidebar.

OpenAPI keeps ``tags`` flat, so any nesting a reader sees has to be declared
somewhere else. Three places declare it, and they are read in order of how
deliberate they are: what the caller passed to :func:`~fastapi_docs.mount`, then
the ``x-tagGroups`` extension, then OpenAPI 3.2's ``parent`` field.

Whatever the source, one rule holds: **a tag no group claims is not dropped.**
Redoc drops it — a whole feature can leave the docs because someone forgot to
file a router — and in a console you use to *call* those endpoints, silently
hiding them is worse than ugly. Leftovers land in :data:`UNGROUPED`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

UNGROUPED = "Other"


@dataclass
class TagGroup:
    """A sidebar section and the tags it gathers."""

    name: str
    tags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "tags": list(self.tags)}


def tags_in_use(schema: dict[str, Any]) -> list[str]:
    """Every tag some operation is actually filed under.

    Ordered by the document's own ``tags`` array first — that is where the
    descriptions and the author's intended reading order live — with anything
    an operation uses but the array omits appended in path order.
    """
    used: dict[str, None] = {}
    for operations in schema.get("paths", {}).values():
        for operation in operations.values():
            if not isinstance(operation, dict):
                continue
            for tag in operation.get("tags", []):
                used.setdefault(tag, None)

    declared = [tag["name"] for tag in schema.get("tags", []) if tag.get("name") in used]
    return declared + [tag for tag in used if tag not in set(declared)]


def _from_parent_field(schema: dict[str, Any]) -> list[TagGroup]:
    """OpenAPI 3.2 hierarchy: tags naming a ``parent``.

    The parent is itself a tag entry (conventionally ``kind: nav``) that no
    operation uses, which is exactly how it stays out of :func:`tags_in_use`.
    """
    order: dict[str, TagGroup] = {}
    for tag in schema.get("tags", []):
        parent = tag.get("parent")
        if not parent:
            continue
        order.setdefault(parent, TagGroup(name=parent)).tags.append(tag["name"])
    return list(order.values())


def _declared_groups(schema: dict[str, Any], configured: list[TagGroup] | None) -> list[TagGroup]:
    if configured:
        return [TagGroup(name=group.name, tags=list(group.tags)) for group in configured]

    extension = schema.get("x-tagGroups")
    if isinstance(extension, list) and extension:
        return [TagGroup(name=group["name"], tags=list(group.get("tags", []))) for group in extension if group.get("name")]

    return _from_parent_field(schema)


def resolve_groups(schema: dict[str, Any], configured: list[TagGroup] | None = None) -> list[dict[str, Any]]:
    """The sidebar, as a list of ``{"name", "tags"}`` sections.

    Every tag in use appears exactly once. A tag claimed by two groups keeps its
    first claim, a group left with nothing real is dropped, and whatever no
    group claimed is gathered under :data:`UNGROUPED` rather than vanishing.
    """
    used = tags_in_use(schema)
    remaining = dict.fromkeys(used)

    sections: list[dict[str, Any]] = []
    for group in _declared_groups(schema, configured):
        claimed = [tag for tag in group.tags if tag in remaining]
        for tag in claimed:
            del remaining[tag]
        if claimed:
            sections.append({"name": group.name, "tags": claimed})

    if remaining:
        # Not an error worth refusing to start over — a tag with no home is
        # usually a router added this morning, and the console should show it.
        sections.append({"name": UNGROUPED, "tags": list(remaining)})

    return sections
