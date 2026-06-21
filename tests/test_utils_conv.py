"""Coverage for to_int / to_float edge cases."""

from __future__ import annotations

import pytest

from custom_components.sws12500.utils import to_float, to_int


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
