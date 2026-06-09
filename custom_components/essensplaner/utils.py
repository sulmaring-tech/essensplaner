"""Utility functions for Essensplaner."""

from __future__ import annotations

import re
import unicodedata
import uuid


def generate_id() -> str:
    """Generate a unique ID."""
    return str(uuid.uuid4())


def slugify(text: str) -> str:
    """Create a URL-safe slug from text."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "-", text).strip("-") or generate_id()[:8]


def unique_slug(base: str, existing: set[str]) -> str:
    """Return a unique slug."""
    slug = slugify(base)
    if slug not in existing:
        return slug
    counter = 2
    while f"{slug}-{counter}" in existing:
        counter += 1
    return f"{slug}-{counter}"
