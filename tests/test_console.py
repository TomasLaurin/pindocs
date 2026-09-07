"""The variables rail, driven in node — the one part of the console that is not Python.

``PUT /state`` writes the file whole, so the browser has to be sure it never has
two writes in flight at once: each builds its document from the state it can
see, and the second to land is a document that never heard of the first. Pinning
five variables faster than one round trip used to leave one.

``tests/console_writes.mjs`` is the harness. It loads the real ``console.js``,
clicks the real buttons, and prints the document the app it was talking to ended
up holding; the assertions are here.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HARNESS = Path(__file__).parent / "console_writes.mjs"

# A checkout without node still tests all the Python.
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="the console is JavaScript, and node runs it")


@pytest.fixture(scope="module")
def written() -> dict:
    """One run of the harness — both scenarios below happen on the same page."""
    node = subprocess.run(["node", str(HARNESS)], capture_output=True, text=True, timeout=120, check=False)
    assert node.returncode == 0, node.stderr
    return json.loads(node.stdout)


def test_pins_made_faster_than_one_round_trip_all_survive(written) -> None:
    pinned = {"run_id": "v_0", "workspace_id": "v_1", "model_id": "v_2", "dataset_id": "v_3", "job_id": "v_4"}

    assert written["afterPinning"]["pinned"] == pinned, "a write in flight swallowed one"


def test_two_values_unpinned_at_once_both_go_and_the_rest_stay(written) -> None:
    assert written["afterUnpinning"]["pinned"] == {"run_id": "v_0", "model_id": "v_2", "job_id": "v_4"}
