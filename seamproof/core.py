"""Core seam-fixing and seam-measuring algorithms for seamproof.

Everything here is classical image processing on CPU (numpy only):

* One shared *geometry* per image size: a half-size roll that moves the
  wrap-around edges to the centre cross, a cosine-tapered mirror blend
  across that cross, and the inverse roll.  Every map in a PBR set is
  processed with the identical geometry (same offset, same band, same
  blend weights), so the maps stay registered with each other.
* An optional toroidal low-frequency detrend (FFT Gaussian on the torus)
  that removes vignette / global gradient from colour maps, so the
  low-frequency mismatch does not reappear as a visible tiling grid.
* A published seam score: mean absolute discontinuity between opposite
  edge strips, measured on a lightly blurred image (see README).
"""

from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _as_float(arr: np.ndarray) -> np.ndarray:
    a = np.asarray(arr, dtype=np.float64)
    if a.ndim == 2:
        a = a[:, :, None]
    return a


def toroidal_gaussian(arr: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian blur computed on the torus (wrap-around) via FFT.

    Because the convolution wraps, the result is itself a valid tileable
    field: blurring never introduces a new edge mismatch.
    """
    a = _as_float(arr)
    if sigma <= 0:
        return a.copy()
    h, w, _ = a.shape
    fy = np.fft.fftfreq(h)[:, None, None]
    fx = np.fft.rfftfreq(w)[None, :, None]
    g = np.exp(-2.0 * (np.pi**2) * (sigma**2) * (fx**2 + fy**2))
    spec = np.fft.rfft2(a, axes=(0, 1))
    out = np.fft.irfft2(spec * g, s=(h, w), axes=(0, 1))
    return out


def _box_blur3(a: np.ndarray) -> np.ndarray:
    """One 3x3 box-blur pass with wrap-around (toroidal) neighbourhood."""
    s = np.zeros_like(a)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            s += np.roll(a, (dy, dx), axis=(0, 1))
    return s / 9.0


# ---------------------------------------------------------------------------
# Seam score
# ---------------------------------------------------------------------------


def seam_score(arr: np.ndarray) -> dict:
    """Measure wrap-around edge discontinuity.

    Definition (also in README): the image is lightly blurred (one 3x3
    toroidal box pass, to suppress single-pixel noise), then for each row
    the mean of the leftmost S columns is compared with the mean of the
    rightmost S columns, where S = clamp(min(H, W) // 32, 1, 4).  The
    horizontal score is the mean absolute difference over all rows and
    channels, in 0-255 intensity units; the vertical score is the same
    for rows.  ``score`` is the mean of the two.
    """
    a = _box_blur3(_as_float(arr))
    h, w, _ = a.shape
    s = max(1, min(4, min(h, w) // 32))
    if w < 2 * s or h < 2 * s:
        s = 1
    left = a[:, :s, :].mean(axis=1)
    right = a[:, w - s :, :].mean(axis=1)
    horiz = float(np.abs(left - right).mean())
    top = a[:s, :, :].mean(axis=0)
    bottom = a[h - s :, :, :].mean(axis=0)
    vert = float(np.abs(top - bottom).mean())
    return {"horizontal": horiz, "vertical": vert, "score": (horiz + vert) / 2.0}


def tiled_score(arr: np.ndarray) -> float:
    """Re-score by actually tiling 3x3 and measuring the internal seams.

    The strips straddling the two internal tile boundaries of the middle
    tile are compared exactly as in :func:`seam_score`.  For a correct
    score implementation this agrees with ``seam_score`` up to the blur
    neighbourhood; it exists as an end-to-end consistency check.
    """
    a = _as_float(arr)
    h, w, _ = a.shape
    big = np.tile(a, (3, 3, 1))
    big = _box_blur3(big)
    s = max(1, min(4, min(h, w) // 32))
    if w < 2 * s or h < 2 * s:
        s = 1
    rows = slice(h, 2 * h)
    cols = slice(w, 2 * w)
    diffs = []
    for boundary in (w, 2 * w):
        lft = big[rows, boundary - s : boundary, :].mean(axis=1)
        rgt = big[rows, boundary : boundary + s, :].mean(axis=1)
        diffs.append(float(np.abs(lft - rgt).mean()))
    for boundary in (h, 2 * h):
        top = big[boundary - s : boundary, cols, :].mean(axis=0)
        bot = big[boundary : boundary + s, cols, :].mean(axis=0)
        diffs.append(float(np.abs(top - bot).mean()))
    return float(np.mean(diffs))


def band_delta(arr: np.ndarray, geom: dict) -> float:
    """How much the blend alone has to repaint the seam band (0-255 units).

    Mean absolute change between the original and its blend-only version,
    measured inside the outer band of width ``geom['band']``.  A low seam
    score achieved with a very high band delta means the seam was hidden
    by inventing content - expect ghosting - so the CLI reports both
    numbers and the verdict is downgraded (see :func:`verdict`).
    """
    a = _as_float(arr)
    blended = seam_blend(a, geom)
    h, w, _ = a.shape
    b = geom["band"]
    mask = np.zeros((h, w), dtype=bool)
    mask[:b, :] = mask[h - b :, :] = True
    mask[:, :b] = mask[:, w - b :] = True
    return float(np.abs(blended - a)[mask].mean())


def verdict(score: float, repaint: float | None = None) -> str:
    """Plain-language reading of a seam score (0-255 units).

    If the blend had to repaint the seam band heavily (band delta > 25)
    to reach a low score, the verdict is downgraded: the edge numbers
    match, but the band content was partly invented.
    """
    if repaint is not None and repaint > 25.0 and score <= 8.0:
        return (
            f"poor - low score only because the seam band was heavily repainted "
            f"(band delta {repaint:.0f}); expect ghosting / doubled features"
        )
    if score <= 2.0:
        return "good - seam not visible in practice"
    if score <= 8.0:
        return "fair - a faint seam may show on close inspection"
    return "poor - strong content crosses the edge; blending cannot hide it without repainting"


# ---------------------------------------------------------------------------
# Shared geometry + blend
# ---------------------------------------------------------------------------


def blend_geometry(h: int, w: int, band: int | None = None) -> dict:
    """The single geometric fix shared by every map of a set.

    Returns the roll offset, the blend band, and the per-column /
    per-row cosine blend weights used after rolling.
    """
    if band is None:
        band = max(2, int(round(min(h, w) / 8.0)))
    band = max(1, min(band, min(h, w) // 2))

    def weights(n: int) -> np.ndarray:
        centre = (n - 1) / 2.0
        d = np.abs(np.arange(n) - centre) / float(band)
        a = 0.5 * (0.5 + 0.5 * np.cos(np.pi * np.clip(d, 0.0, 1.0)))
        return np.where(d < 1.0, a, 0.0)

    return {
        "offset_y": h // 2,
        "offset_x": w // 2,
        "band": band,
        "alpha_x": weights(w),  # blend weight per column, after rolling
        "alpha_y": weights(h),  # blend weight per row, after rolling
    }


def seam_blend(arr: np.ndarray, geom: dict) -> np.ndarray:
    """Apply the shared geometric fix to one map.

    Roll by half size (the wrap edges now meet at the centre cross),
    cross-fade each side of the cross with its mirror image using the
    shared cosine weights, then roll back.  Pixels whose blend weight is
    zero are returned bit-identical.
    """
    a = _as_float(arr)
    oy, ox = geom["offset_y"], geom["offset_x"]
    r = np.roll(a, (oy, ox), axis=(0, 1))
    ax = geom["alpha_x"][None, :, None]
    r = r * (1.0 - ax) + r[:, ::-1, :] * ax
    ay = geom["alpha_y"][:, None, None]
    r = r * (1.0 - ay) + r[::-1, :, :] * ay
    return np.roll(r, (-oy, -ox), axis=(0, 1))


# ---------------------------------------------------------------------------
# Detrend (colour maps only)
# ---------------------------------------------------------------------------


def detrend(arr: np.ndarray, sigma: float | None = None) -> np.ndarray:
    """Remove the toroidal low-frequency component (vignette / gradient).

    The low-frequency field is estimated with a wrap-around Gaussian, so
    subtracting it (and adding back its per-channel mean) flattens the
    global illumination without inventing new edge content.
    """
    a = _as_float(arr)
    h, w, _ = a.shape
    if sigma is None:
        sigma = max(2.0, min(h, w) / 5.0)
    lf = toroidal_gaussian(a, sigma)
    return a - lf + lf.mean(axis=(0, 1), keepdims=True)


# ---------------------------------------------------------------------------
# Normal maps
# ---------------------------------------------------------------------------


def renormalize_normals(arr: np.ndarray) -> np.ndarray:
    """Re-normalise a tangent-space normal map (RGB, OpenGL Y+) to unit length.

    Channels are decoded from [0, 255] to [-1, 1]; z is kept positive
    (tangent-space validity); vectors are scaled back to unit length.
    """
    a = _as_float(arr)
    if a.shape[2] < 3:
        return a
    v = a[:, :, :3] / 127.5 - 1.0
    v[:, :, 2] = np.abs(v[:, :, 2])
    n = np.linalg.norm(v, axis=2, keepdims=True)
    n = np.where(n == 0.0, 1.0, n)
    v = v / n
    out = a.copy()
    out[:, :, :3] = (v * 0.5 + 0.5) * 255.0
    return out


def normal_from_height(height: np.ndarray, strength: float = 2.0) -> np.ndarray:
    """Derive a tangent-space normal map (RGB float, 0-255) from a height map.

    Utility used by the examples and the registration test.  Gradients
    use wrap-around differences, matching the tileable setting.
    """
    hgt = _as_float(height)[:, :, 0]
    gy, gx = np.gradient(hgt)
    nx = -gx * strength / 255.0
    ny = gy * strength / 255.0  # OpenGL Y+: up in image = +v
    nz = np.ones_like(hgt)
    n = np.sqrt(nx**2 + ny**2 + nz**2)
    rgb = np.stack([(nx / n * 0.5 + 0.5), (ny / n * 0.5 + 0.5), (nz / n * 0.5 + 0.5)], axis=2)
    return rgb * 255.0


# ---------------------------------------------------------------------------
# Full per-map fix
# ---------------------------------------------------------------------------

#: Map types that carry illumination (vignette) and therefore get detrended.
DETREND_TYPES = {"albedo", "single"}


def fix_array(
    arr: np.ndarray,
    map_type: str,
    geom: dict,
    use_detrend: bool = True,
) -> np.ndarray:
    """Fix one map with the shared geometry.

    * colour maps (albedo / standalone images): detrend, then blend;
    * data maps (normal / roughness / height / other): blend only, so a
      set's derived maps are never pulled out of register by a
      per-map illumination change;
    * normal maps are re-normalised to unit length after blending.
    """
    a = _as_float(arr)
    if use_detrend and map_type in DETREND_TYPES:
        a = detrend(a)
    a = seam_blend(a, geom)
    if map_type == "normal":
        a = renormalize_normals(a)
    return a
