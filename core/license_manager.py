"""License/activation removed for this open build of Nyx Suite v5.

The original machine-bound activation has been stripped from this release: the
runners start unconditionally and the dashboard always reports "activated". This
module is kept as a tiny stub so the few callers that display activation status
(the bridge endpoints and the product controllers) keep working without changes.
"""
from __future__ import annotations


def is_activated() -> bool:
    return True


def get_request_code() -> str:
    return ""


def save_activation_code(code):
    # No activation needed in the open build — accept anything.
    return {"activated": True, "open_build": True}


def get_activation_summary() -> dict:
    return {
        "activated": True,
        "open_build": True,
        "device_id": "open-build",
        "license_device_id": "open-build",
        "request_code": "",
        "duration_days": None,
        "expires_at": None,
        "expires_at_display": "",
        "days_remaining": None,
        "expired": False,
        "accepted_device_ids": [],
    }


def format_activation_summary(summary=None) -> str:
    return "Activated (open build — no license required)."
