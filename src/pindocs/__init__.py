"""A grouped, try-it-out API console for FastAPI, with values that outlive restarts.

>>> import pindocs
>>> app = FastAPI()
>>> pindocs.mount(app, path="/myapp")   # → http://localhost:8000/myapp
"""

from pindocs.groups import UNGROUPED, TagGroup
from pindocs.mount import DEFAULT_PATH, DEFAULT_STATE_FILE, mount

__version__ = "0.1.0"

__all__ = ["DEFAULT_PATH", "DEFAULT_STATE_FILE", "UNGROUPED", "TagGroup", "mount"]
