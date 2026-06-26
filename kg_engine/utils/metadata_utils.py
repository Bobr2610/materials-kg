"""Metadata utilities for document processing."""
from __future__ import annotations

import re
from datetime import datetime, timezone


def _epoch_to_iso(epoch: int) -> str:
    """Convert epoch timestamp to UTC ISO string.

    Args:
        epoch: Unix timestamp in seconds

    Returns:
        ISO 8601 formatted string in UTC timezone
    """
    return datetime.utcfromtimestamp(epoch).replace(tzinfo=timezone.utc).isoformat()


def extract_numeric_kbid(kb_id: str | int | None) -> str | None:
    """Extract the first numeric sequence from kbId, handling suffixes like '4578-toc'.

    Args:
        kb_id: kbId value (can be string, int, or None)

    Returns:
        String with just the numeric part, or None if no numeric sequence found
    """
    if kb_id is None:
        return None
    match = re.match(r'^(\d+)', str(kb_id))
    return match.group(1) if match else None


def parse_frontmatter_timestamp(updated_str: str) -> tuple[int | None, str | None]:
    """Parse frontmatter updated field to timestamp.

    Supports formats like '2024-06-14 12:33:36' (no timezone, assumed UTC).

    Args:
        updated_str: String representation of date/time

    Returns:
        Tuple of (epoch: int, iso_string: str) or (None, None) on parse failure
    """
    try:
        # Try common formats
        formats = [
            "%Y-%m-%d %H:%M:%S",  # '2024-06-14 12:33:36'
            "%Y-%m-%d",  # '2024-06-14'
            "%Y-%m-%dT%H:%M:%S",  # ISO-like without timezone
            "%Y-%m-%dT%H:%M:%S%z",  # ISO with timezone
        ]

        dt = None
        for fmt in formats:
            try:
                dt = datetime.strptime(updated_str.strip(), fmt)
                break
            except ValueError:
                continue

        if dt is None:
            return None, None

        # If no timezone info, assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        epoch = int(dt.timestamp())
        iso_string = _epoch_to_iso(epoch)
        return epoch, iso_string
    except Exception:  # noqa: BLE001
        return None, None

