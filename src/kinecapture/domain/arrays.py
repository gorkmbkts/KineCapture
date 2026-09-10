"""Array ownership at asynchronous/backend boundaries; no Qt or SDK types."""

from typing import Any

import numpy as np


def owned_snapshot(values: Any, dtype: Any) -> np.ndarray:
    """Detach from producer scratch memory and prohibit downstream mutation."""
    result = np.array(values, dtype=dtype, order="C", copy=True)
    result.setflags(write=False)
    return result


def retain_snapshot(values: Any, dtype: Any) -> np.ndarray:
    """Retain an owned immutable array, otherwise take a defensive snapshot.

    Public writers accept mutable input. Backend packets can transfer their
    already detached, read-only arrays without a second full image copy.
    Callers must not re-enable writes on an array after transferring it.
    """
    array = np.asarray(values, dtype=dtype)
    if array.flags.owndata and array.flags.c_contiguous and not array.flags.writeable:
        return array
    return owned_snapshot(array, dtype)
