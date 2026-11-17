"""seamproof - make textures tile seamlessly, a whole PBR set at a time.

One shared geometric fix across every map in a set (so maps stay
registered), a toroidal detrend for vignetted colour maps, and a
published seam score that certifies the result before/after.
"""

from .core import (
    band_delta,
    blend_geometry,
    detrend,
    fix_array,
    normal_from_height,
    renormalize_normals,
    seam_blend,
    seam_score,
    tiled_score,
    verdict,
)

__version__ = "0.1.0"

__all__ = [
    "band_delta",
    "blend_geometry",
    "detrend",
    "fix_array",
    "normal_from_height",
    "renormalize_normals",
    "seam_blend",
    "seam_score",
    "tiled_score",
    "verdict",
    "__version__",
]
