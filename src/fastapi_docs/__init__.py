"""A grouped, try-it-out API console for FastAPI, with values that outlive restarts.

>>> import fastapi_docs
>>> app = FastAPI()
>>> fastapi_docs.mount(app, path="/myapp")   # → http://localhost:8000/myapp
"""

from fastapi_docs.groups import UNGROUPED, TagGroup
from fastapi_docs.mount import DEFAULT_PATH, DEFAULT_STATE_FILE, mount

__version__ = "0.1.0"

__all__ = ["DEFAULT_PATH", "DEFAULT_STATE_FILE", "UNGROUPED", "TagGroup", "mount"]
