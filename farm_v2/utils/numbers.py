"""
numbers.py — the "is this a real number" test and the two money-input refusals built on it.

Lives in utils so validation and perennials both call it: a fix to it (the NaN case was one,
/code-review max #9) then reaches every check, instead of the copy that happened to be patched.
"""

import math


def is_number(v) -> bool:
    """A real, finite number — not a bool (which Python counts as an int), not None, not NaN."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def check_nonneg(val, name: str) -> None:
    """For values charged straight into money: NaN poisons the profit and a negative pays the farm,
    so both are refused rather than coerced."""
    if not (is_number(val) and val >= 0):
        raise ValueError(f"{name} must be a number ≥ 0, got {val!r}.")


def check_positive(val, name: str) -> None:
    # is_number, not `val <= 0`: NaN compares False to everything, so it passed (/code-review max #9).
    if not (is_number(val) and val > 0):
        raise ValueError(f"{name} must be positive, got {val!r}.")
