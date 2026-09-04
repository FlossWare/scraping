from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class AcquiredResource:
    """A durable acquisition record independent of storage implementation."""

    uri: str
    media_type: str
    content_hash: str
    raw_path: str
    size: int
    retrieved_at: str
    discovered_by: str = "explicit"

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()
