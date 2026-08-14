"""What the console remembers between restarts.

Two stores, deliberately separate, because they answer to different owners:

``pinned``
    Values you set on purpose — ``workspace_id`` for the workspace you always
    work in. They survive restarts, they are the point of the file, and nothing
    automatic is allowed to overwrite them.

``captured``
    Values the last response handed back. ``POST /v1/runs`` returns an id and the
    next call that wants a ``run_id`` should already have it. Most-recent-wins,
    and disposable — clearing them costs nothing.

Bearer tokens are in neither. They live in the browser's ``localStorage``, never
on disk, because this file is meant to be committed and shared by a team.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = 1

# Long enough for a URL-shaped id or a JWT-ish opaque handle, short enough that a
# response body accidentally shaped like a blob does not end up in the file.
MAX_VALUE_LENGTH = 2048

_VALID_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*$")


def _empty() -> dict[str, Any]:
    return {"version": VERSION, "capture": True, "pinned": {}, "captured": {}}


def _clean_value(value: Any) -> str | None:
    """A stored value is always a string — it is going into a URL or a form."""
    if isinstance(value, bool) or value is None:
        return None
    if not isinstance(value, str | int | float):
        return None
    text = str(value)
    return text if text and len(text) <= MAX_VALUE_LENGTH else None


def _clean_names(values: Any) -> dict[str, str]:
    if not isinstance(values, dict):
        return {}
    cleaned: dict[str, str] = {}
    for name, value in values.items():
        text = _clean_value(value)
        if isinstance(name, str) and _VALID_NAME.match(name) and text is not None:
            cleaned[name] = text
    return cleaned


def _clean_captured(values: Any) -> dict[str, dict[str, str]]:
    if not isinstance(values, dict):
        return {}
    cleaned: dict[str, dict[str, str]] = {}
    for name, entry in values.items():
        if not (isinstance(name, str) and _VALID_NAME.match(name)):
            continue
        raw = entry.get("value") if isinstance(entry, dict) else entry
        text = _clean_value(raw)
        if text is None:
            continue
        source = entry.get("source") if isinstance(entry, dict) else None
        at = entry.get("at") if isinstance(entry, dict) else None
        cleaned[name] = {
            "value": text,
            "source": str(source) if source else "",
            "at": str(at) if at else _now(),
        }
    return cleaned


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalise(raw: Any) -> dict[str, Any]:
    """Coerce anything that came off disk or off the wire into a valid state.

    Never raises: a hand-edited file with one bad line should cost you that line,
    not the console. Whatever survives is what gets written back.
    """
    if not isinstance(raw, dict):
        return _empty()
    return {
        "version": VERSION,
        "capture": bool(raw.get("capture", True)),
        "pinned": _clean_names(raw.get("pinned")),
        "captured": _clean_captured(raw.get("captured")),
    }


@dataclass
class StateStore:
    """The JSON file, read and written whole.

    Small enough that partial updates would buy nothing, and rewriting whole
    means the file on disk is always a complete valid document. Writes go
    through a temp file in the same directory so a crash mid-write cannot leave
    a truncated one.
    """

    path: Path
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    def load(self) -> dict[str, Any]:
        with self._lock:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return _empty()
            return normalise(raw)

    def save(self, state: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            clean = normalise(state)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Same directory as the target, so the rename below is atomic rather
            # than a cross-device copy.
            descriptor, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp")
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                    json.dump(clean, file, indent=2, sort_keys=True)
                    file.write("\n")
                os.replace(temporary, self.path)
            except BaseException:
                Path(temporary).unlink(missing_ok=True)
                raise
            return clean

    def merge_captured(self, variables: dict[str, str], source: str) -> dict[str, Any]:
        """Fold a response's variables in, most-recent-wins.

        Pinned names are skipped outright rather than shadowed: a pin is a
        deliberate choice, and a console that quietly replaced it would be
        unusable for the exact case pins exist for.
        """
        with self._lock:
            state = self.load()
            stamp = _now()
            for name, value in variables.items():
                if name in state["pinned"]:
                    continue
                text = _clean_value(value)
                if text is not None:
                    state["captured"][name] = {"value": text, "source": source, "at": stamp}
            return self.save(state)
