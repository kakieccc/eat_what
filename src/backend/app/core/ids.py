from __future__ import annotations

import hashlib
import json
from uuid import uuid4


def uid() -> str:
    return str(uuid4())


def lock_id(value: str) -> int:
    return int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], "big", signed=True)


def request_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


__all__ = ["lock_id", "request_hash", "uid"]
