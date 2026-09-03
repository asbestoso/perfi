"""Shared list-pagination dependency: ?limit=&offset= -> (limit, offset)."""
from fastapi import HTTPException

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def pagination(limit=DEFAULT_LIMIT, offset=0):
    try:
        limit = int(limit)
        offset = int(offset)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="limit and offset must be integers")
    limit = max(1, min(limit, MAX_LIMIT))
    offset = max(0, offset)
    return limit, offset
