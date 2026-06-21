"""Coverage for to_int / to_float edge cases and anonymize() masking."""

from __future__ import annotations

import pytest

from custom_components.sws12500.utils import anonymize, to_float, to_int


def test_anonymize_masks_all_known_secrets() -> None:
    raw = {
        "ID": "id",
        "PASSWORD": "pw",
        "wsid": "ws",
        "wspw": "wp",
        "passkey": "ecowitt-secret",
        "PASSKEY": "ecowitt-secret",
        "tempf": "68",
    }
    out = anonymize(raw)
    for key in ("ID", "PASSWORD", "wsid", "wspw", "passkey", "PASSKEY"):
        assert out[key] == "***"
    # Non-secret values pass through unchanged.
    assert out["tempf"] == "68"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("x", None),
        ("5", 5),
        (7, 7),
    ],
)
def test_to_int_edge_cases(value, expected) -> None:
    assert to_int(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("x", None),
        ("5.5", 5.5),
        (7, 7.0),
    ],
)
def test_to_float_edge_cases(value, expected) -> None:
    assert to_float(value) == expected
