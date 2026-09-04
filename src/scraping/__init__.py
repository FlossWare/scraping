"""FlossWare resource acquisition and scraping capability."""

from .models import AcquiredResource
from .uri import normalize_uri

__all__ = ["AcquiredResource", "normalize_uri"]
