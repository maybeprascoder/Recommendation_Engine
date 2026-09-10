"""Locate versioned configuration in editable and wheel installations."""

from importlib.resources import files
from pathlib import Path

# pip installs these resources as ordinary files. The explicit package mapping
# points to the original data/ directory in editable installs, so local edits
# remain visible without copying or rebuilding configuration.
DATA_ROOT = Path(str(files("unihive._data")))
