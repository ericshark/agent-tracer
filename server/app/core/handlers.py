"""Imports every module that registers background-job handlers.

Both the API process (inline worker) and `python -m app.worker` import this so
the handler registry is complete before the first job is claimed.
"""

from app.core import experiments  # noqa: F401
