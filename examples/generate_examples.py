#!/usr/bin/env python3
"""Generate seamproof's sample textures procedurally (no external assets).

Creates, next to this script:
  ground_albedo.png  - a ground-like colour texture with a deliberate
                       vignette + left-to-right ramp, so it tiles badly
  rock_albedo.png / rock_normal.png / rock_roughness.png / rock_height.png
                     - one small PBR set derived from a single height field
  demo_compare.png   - ground tiled 3x3 before vs after seamproof

Run:  python3 examples/generate_examples.py
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from seamproof import core  # noqa: E402

HERE = Path(__file__).resolve().parent
rng = np.random.default_rng(42)


def fbm(h: int, w: int, octaves=(48.0, 20.0, 8.0, 3.0), weights=(0.45, 0.3, 0.17, 0.08)) -> np.ndarray:
    """Tileable fractal noise: toroidal-Gaussian octaves of white noise."""
    out = np.zeros((h, w))
    for sigma, wt in zip(octaves, weights):
        layer = core.toroidal_gaussian(rng.normal(0, 1, (h, w, 1)), sigma)[:, :, 0]
        layer /= np.abs(layer).max()
        out += wt * layer
    out -= out.min()
    out /= out.max()
    return out


def palette(t: np.ndarray, stops: list[tuple[float, tuple[int, int, int]]]) -> np.ndarray:
    """Map a 0..1 field through colour stops."""
    img = np.zeros((*t.shape, 3))
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        m = np.clip((t - t0) / (t1 - t0), 0, 1)[..., None]
        seg = np.array(c0) * (1 - m) + np.array(c1) * m
        img = np.where(((t >= t0) & (t <= t1))[..., None], seg, img)
    return img


def save(arr: np.ndarray, name: str) -> None:
    a = np.clip(np.rint(arr), 0, 255).astype(np.uint8)
    if a.ndim == 2:
        Image.fromarray(a, "L").save(HERE / name)
    else:
        Image.fromarray(a, "RGB").save(HERE / name)


def main() -> None:
    size = 256
    yy, xx = np.mgrid[0:size, 0:size]

    # --- ground albedo: nice detail, bad edges (vignette + ramp) -----------
    t = fbm(size, size)
    ground = palette(
        t,
        [
            (0.0, (58, 44, 30)),
            (0.45, (110, 86, 54)),
            (0.75, (140, 126, 82)),
            (1.0, (168, 156, 104)),
        ],
    )
    ground += rng.normal(0, 7, ground.shape)  # speckle
    ramp = (xx[..., None] / size) * 55.0  # left dark -> right bright
    bowl = (((xx - size / 2) ** 2 + (yy - size / 2) ** 2) / (size**2) * 70.0)[..., None]
    ground = np.clip(ground + ramp - bowl, 0, 255)
    save(ground, "ground_albedo.png")

    # --- rock PBR set from one height field --------------------------------
    height = fbm(size, size, octaves=(36.0, 14.0, 5.0), weights=(0.55, 0.3, 0.15)) * 255.0
    save(height, "rock_height.png")
    albedo = palette(
        height / 255.0,
        [(0.0, (52, 50, 48)), (0.5, (112, 106, 98)), (1.0, (178, 170, 158))],
    )
    albedo += rng.normal(0, 6, albedo.shape)
    save(np.clip(albedo, 0, 255), "rock_albedo.png")
    rough = np.clip(215.0 - height * 0.45 + rng.normal(0, 9, height.shape), 0, 255)
    save(rough, "rock_roughness.png")
    save(core.normal_from_height(height[:, :, None], strength=2.5), "rock_normal.png")

    # --- demo: tile 3x3 before vs after ------------------------------------
    geom = core.blend_geometry(size, size)
    fixed = core.fix_array(ground, "albedo", geom)
    before_score = core.seam_score(ground)["score"]
    after_score = core.seam_score(fixed)["score"]

    def tile3(arr: np.ndarray) -> Image.Image:
        a = np.clip(np.rint(arr), 0, 255).astype(np.uint8)
        return Image.fromarray(np.tile(a, (3, 3, 1)), "RGB")

    bar = 30
    left, right = tile3(ground), tile3(fixed)
    canvas = Image.new("RGB", (left.width + right.width, left.height + bar), (24, 24, 24))
    canvas.paste(left, (0, bar))
    canvas.paste(right, (left.width, bar))
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 9), f"BEFORE - tiled 3x3 - seam score {before_score:.1f}", fill=(255, 120, 120))
    draw.text((left.width + 10, 9), f"AFTER seamproof - tiled 3x3 - seam score {after_score:.1f}", fill=(140, 255, 140))
    canvas.save(HERE / "demo_compare.png")
    print(f"ground_albedo seam score: {before_score:.1f} -> {after_score:.1f}")
    print("wrote ground_albedo.png, rock_*.png, demo_compare.png")


if __name__ == "__main__":
    main()
