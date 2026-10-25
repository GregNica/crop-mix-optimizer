"""
numbers.py — the one "is this a real number" test every input check shares.

Lives in utils so validation and perennials both call it: a fix to it (the NaN case was one,
/code-review max #9) then reaches every check, instead of the copy that happened to be patched.
"""

import math


def is_number(v) -> bool:
    """A real, finite number — not a bool (which Python counts as an int), not None, not NaN."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
