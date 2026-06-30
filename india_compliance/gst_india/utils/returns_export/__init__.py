# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""
Raw GSTN payload access for the GST Return Export tool.

The payload is persisted on the period's GST Return Log row. This module is the thin public read API
the exporter calls, plus the in-memory merge helper for 2B split files.
"""

from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    get_raw_return_data,
)


def get_raw_payload(gstin, return_type, return_period):
    """Return the stored verbatim GSTN payload (parsed), or None if not synced yet."""
    return get_raw_return_data(gstin, return_type, return_period)


def merge_raw(existing, new):
    """Merge two raw payload chunks in memory (GSTR-2B split files)."""
    if isinstance(existing, dict) and isinstance(new, dict):
        merged = dict(existing)
        for key, value in new.items():
            if isinstance(merged.get(key), list) and isinstance(value, list):
                merged[key] = merged[key] + value
            else:
                merged[key] = value
        return merged

    if isinstance(existing, list) and isinstance(new, list):
        return existing + new

    return new
