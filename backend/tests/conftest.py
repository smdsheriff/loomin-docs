"""Test configuration.

Point the app at a throwaway SQLite database and scratch directories BEFORE any
application module (which reads settings at import time) is imported.
"""

import os
import pathlib
import tempfile

_tmp = pathlib.Path(tempfile.gettempdir()) / "loomin_test"
_tmp.mkdir(exist_ok=True)

os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{(_tmp / 'test.db').as_posix()}")
os.environ.setdefault("FAISS_INDEX_PATH", (_tmp / "faiss").as_posix())
os.environ.setdefault("UPLOAD_DIR", (_tmp / "uploads").as_posix())
