"""Category-A value fault families (synthetic perturbations of public weather data).

Each family transforms ONE window of ONE station. The functions are pure: the input
window is never mutated, a new array is returned, and all randomness comes from the
``numpy.random.Generator`` passed in, so a scenario is reproducible from its seed.

Window semantics follow the design spec section 5. Fault sizes are in units of
``sigma`` (the station's sigma_ref); precipitation families ignore ``sigma``.

Not implemented here (later plan tasks): ``realistic_replace``, ``cycle_shaped``,
``network_bias``.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

# Family names are plain strings here so this module does not depend on attacks.schema.
Params = dict[str, float]
_Fault = Callable[[np.ndarray, Params, float, np.random.Generator, float], np.ndarray]

BLOCK_STEPS = 12  # intermittent_offset block length: 12 x 5 min = 1 h


def _offset(x, params, sigma, rng, prev):
    return x + params["k"] * sigma


def _drift(x, params, sigma, rng, prev):
    return x + np.linspace(0.0, params["k"] * sigma, len(x))


def _spike_positions(n_points: int, n_spikes: int, rng: np.random.Generator) -> np.ndarray:
    """n distinct positions, mutually non-adjacent whenever the window is long enough.

    Non-adjacent sampling is uniform: draw n sorted distinct slots from
    ``n_points - (n_spikes - 1)`` and shift the i-th by i.
    """
    slots = n_points - (n_spikes - 1)
    if slots >= n_spikes:
        base = np.sort(rng.choice(slots, size=n_spikes, replace=False))
        return base + np.arange(n_spikes)
    return rng.choice(n_points, size=n_spikes, replace=False)  # too short to isolate


def _spike(x, params, sigma, rng, prev):
    n_spikes = min(int(params["n"]), len(x))
    if n_spikes <= 0:
        return x
    positions = _spike_positions(len(x), n_spikes, rng)
    signs = np.where(rng.random(n_spikes) < 0.5, -1.0, 1.0)
    out = x.copy()
    out[positions] += signs * params["k"] * sigma
    return out


def _noise(x, params, sigma, rng, prev):
    return x + rng.normal(0.0, params["k"] * sigma, size=len(x))


def _flatline(x, params, sigma, rng, prev):
    window = max(int(params["w_steps"]), 1)
    smooth = pd.Series(x).rolling(window, center=True, min_periods=1).mean().to_numpy()
    return np.where(np.isnan(x), np.nan, smooth)  # a missing cell stays missing


def _stuck(x, params, sigma, rng, prev):
    if not np.isfinite(prev):
        raise ValueError("stuck needs a finite `prev` (last value before the window)")
    return np.full(len(x), prev, dtype=np.float64)


def _gain(x, params, sigma, rng, prev):
    centre = np.nanmean(x)
    return centre + params["g"] * (x - centre)


def _intermittent_offset(x, params, sigma, rng, prev):
    faulted = (np.arange(len(x)) // BLOCK_STEPS) % 2 == 0  # blocks 0, 2, 4, ...
    return x + faulted * (params["k"] * sigma)


def _rain_scale(x, params, sigma, rng, prev):
    return x * params["f"]


def _rain_suppress(x, params, sigma, rng, prev):
    return np.where(np.isnan(x), np.nan, 0.0)


def _triangle(duration: int, total_mm: float) -> np.ndarray:
    """Triangular hyetograph: strictly positive, symmetric, peaking mid-event, sums to total."""
    mid = duration / 2.0
    weights = 1.0 - np.abs(np.arange(duration) + 0.5 - mid) / mid  # min weight is 1/duration
    return weights * (total_mm / weights.sum())


def _rain_inject(x, params, sigma, rng, prev):
    duration = min(max(int(params["duration_steps"]), 1), len(x))
    start = int(rng.integers(0, len(x) - duration + 1))
    out = x.copy()
    out[start : start + duration] += _triangle(duration, params["total_mm"])
    return out


_FAULTS: dict[str, _Fault] = {
    "offset": _offset,
    "drift": _drift,
    "spike": _spike,
    "noise": _noise,
    "flatline": _flatline,
    "stuck": _stuck,
    "multi_offset": _offset,  # per-station effect is a plain offset; the injector fans out stations
    "gain": _gain,
    "intermittent_offset": _intermittent_offset,
    "rain_scale": _rain_scale,
    "rain_suppress": _rain_suppress,
    "rain_inject": _rain_inject,
}
FAMILIES = tuple(_FAULTS)


def apply_fault(
    family: str,
    x: np.ndarray,
    params: Params,
    sigma: float,
    rng: np.random.Generator,
    prev: float,
) -> np.ndarray:
    """Return the faulted copy of window ``x`` (same length; ``x`` is not modified).

    ``prev`` is the last clean value before the window; only ``stuck`` uses it.
    Physical clipping is a separate step (``clip_physical``).
    """
    try:
        fault = _FAULTS[family]
    except KeyError:
        raise ValueError(
            f"family {family!r} is not an implemented value family; choose from {FAMILIES}"
        ) from None
    x = np.asarray(x)
    if x.ndim != 1:
        raise ValueError(f"expected a 1-D window, got shape {x.shape}")
    out_dtype = np.result_type(x.dtype, np.float32)  # float32 stays float32
    out = fault(x.astype(np.float64), params, float(sigma), rng, float(prev))
    return np.asarray(out, dtype=out_dtype).copy()


def clip_physical(variable: str, x: np.ndarray) -> np.ndarray:
    """Clip to the physical range: RH to [0, 100], precipitation to >= 0, temperature as is."""
    if variable == "relative_humidity":
        return np.clip(x, 0, 100)
    if variable == "precipitation":
        return np.maximum(x, 0)
    if variable == "air_temperature":
        return np.array(x, copy=True)
    raise ValueError(f"unknown variable {variable!r}")


def delta_onset(family: str, injected_delta: np.ndarray, sigma: float) -> int:
    """Index of the first step where ``|delta| >= sigma``; only drift has a late onset.

    Returns 0 for every other family, and ``len(injected_delta)`` for a drift whose ramp
    never reaches 1 sigma inside the window (the caller should treat that as "no onset").
    """
    if family != "drift":
        return 0
    reached = np.flatnonzero(np.abs(injected_delta) >= sigma)
    return int(reached[0]) if len(reached) else len(injected_delta)
