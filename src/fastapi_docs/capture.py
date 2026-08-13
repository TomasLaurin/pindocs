"""Turning a response into variables you can use in the next request.

The useful case is the obvious one: ``POST /v1/runs`` answers ``{"id": "run_9"}``
and the next call wants a ``run_id``. So the naming problem is the whole problem
— a bare ``id`` is meaningless two requests later, and storing it under ``id``
means the next resource you create overwrites it.

The fix is to read the name off the path the response came from: ``/v1/runs`` is
a collection of runs, so its ``id`` is a ``run_id``. Everything else follows from
being conservative — only scalars, only names the API itself would accept back.
"""

from __future__ import annotations

import re
from typing import Any

# One level of unwrapping for the common envelope shapes. Deeper than this and a
# "captured" value is more likely to surprise than to help.
_ENVELOPE_KEYS = ("data", "items", "results")

_MAX_SCALAR = 2048


# Words that end in `s` without being plural. Stripping these is the one wrong
# guess that would look like a typo rather than an inflection — `/status` giving
# you a `statu_id` reads as a bug in the tool.
_NOT_PLURAL = ("ss", "us", "is", "os")


def singular(word: str) -> str:
    """``runs`` → ``run``. Naive on purpose.

    Nothing downstream breaks when it guesses wrong: you get a variable under a
    slightly odd name, notice it in the rail, and pin the right one. That is a
    better trade than an inflection dependency in a dev tool.
    """
    for suffix, replacement in (("ies", "y"), ("ses", "s"), ("xes", "x"), ("zes", "z"), ("ches", "ch"), ("shes", "sh")):
        if word.endswith(suffix) and len(word) > len(suffix):
            return word[: -len(suffix)] + replacement
    if word.endswith("s") and not word.endswith(_NOT_PLURAL):
        return word[:-1]
    return word


def resource_from_path(path: str) -> str | None:
    """The thing a path addresses: ``/v1/projects/{id}/runs`` → ``run``.

    Reads right to left past templated segments and past the ``:verb`` suffix
    some APIs hang off a collection (``/runs/metrics:query``), because the last
    *static* segment is what names the resource.
    """
    for segment in reversed([part for part in path.split("/") if part]):
        if segment.startswith("{"):
            continue
        segment = segment.split(":", 1)[0]
        if not segment or not re.match(r"^[A-Za-z][A-Za-z0-9_-]*$", segment):
            continue
        # A bare version prefix names nothing — /v1 is not a resource.
        if re.fullmatch(r"v\d+", segment):
            continue
        return singular(segment.replace("-", "_"))
    return None


def _scalar(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if not isinstance(value, str | int | float):
        return None
    text = str(value)
    return text if text and len(text) <= _MAX_SCALAR else None


def _unwrap(body: Any, depth: int = 0) -> dict[str, Any] | None:
    """The object a response is really about.

    A list is the listing case — its first element is the newest or the only
    thing you asked for, and either way it is the one you would have copied by
    hand. Envelopes are peeled, but only a few layers: past that, whatever is
    down there is not what the request was about.
    """
    if depth > 3:
        return body if isinstance(body, dict) else None
    if isinstance(body, list):
        return next((item for item in body if isinstance(item, dict)), None)
    if not isinstance(body, dict):
        return None
    if _looks_like_resource(body):
        return body
    for key in _ENVELOPE_KEYS:
        nested = body.get(key)
        if isinstance(nested, list | dict):
            return _unwrap(nested, depth + 1)
    return body


def _looks_like_resource(body: dict[str, Any]) -> bool:
    """An envelope carries a payload; a resource carries an identity."""
    return "id" in body or any(key.endswith("_id") for key in body)


def variables_from_response(path: str, body: Any, *, known_parameters: set[str] | None = None) -> dict[str, str]:
    """The variables a response is worth remembering.

    Ids are always taken — that is the whole feature. Anything else is taken only
    if the API elsewhere *accepts* a parameter by that name, which is a cheap way
    of saying "this value is addressable" without guessing.
    """
    resource = _unwrap(body)
    if not resource:
        return {}

    accepted = known_parameters or set()
    captured: dict[str, str] = {}

    for key, value in resource.items():
        if not isinstance(key, str):
            continue
        text = _scalar(value)
        if text is None:
            continue

        if key == "id":
            name = resource_from_path(path)
            if name:
                captured[f"{name}_id"] = text
        elif key.endswith(("_id", "Id")) or key in accepted:
            captured[key] = text

    return captured


def parameter_names(schema: dict[str, Any]) -> set[str]:
    """Every name the API takes as a path or query parameter, anywhere."""
    names: set[str] = set()
    for operations in schema.get("paths", {}).values():
        if not isinstance(operations, dict):
            continue
        shared = operations.get("parameters", [])
        for operation in operations.values():
            if not isinstance(operation, dict):
                continue
            for parameter in [*shared, *operation.get("parameters", [])]:
                if isinstance(parameter, dict) and parameter.get("in") in {"path", "query"}:
                    name = parameter.get("name")
                    if isinstance(name, str):
                        names.add(name)
    return names
