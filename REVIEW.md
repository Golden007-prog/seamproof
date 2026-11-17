# seamproof — Independent Adversarial Review

**Reviewer:** an agent that did not build seamproof (SkillScan-standard gauntlet).
**Date:** 2026-11-17. **Version reviewed:** 0.1.0, local files as found on disk.
**Method:** read README + all source + all tests first; ran the suite myself;
fresh-venv install; then wrote my own probe scripts from scratch (seam-score
re-implementation from the README spec, my own heightfield and my own
normal-from-height derivation — the tool's test code was not reused for the
registration or score checks). Probe scripts were kept in /tmp, tool code was
not modified (no bug requiring a fix was found — see "Bugs").

## Verdict

**PASS.** Every headline claim in the README was verified independently,
including the printed demo output, which reproduces exactly. No
correctness-breaking bug was found. Six minor observations are recorded
below; none changes a verdict band or a published number's meaning.

## 1. Test suite (run by reviewer)

```
~/workspace/astro-tools/.venv/bin/python run_tests.py
Ran 15 tests in 0.431s — OK (15/15)
```

## 2. Fresh-install proof

- New venv in /tmp (`python3 -m venv`), `pip install ~/workspace/graphics-tools/seamproof`
  → exit 0 (numpy + Pillow pulled from network). `seamproof --help` works,
  `import seamproof` reports 0.1.0.
- README demo run verbatim from the fresh venv on the shipped example files
  (256×256 ground + rock set, copied to a clean folder). **Output matched the
  README exactly, every line, to the printed decimal:**

  | file | README claim | fresh-venv run |
  |---|---|---|
  | ground_albedo.png | 23.7 → 0.4 (tiled 0.4) | 23.7 → 0.4 (tiled 0.4) |
  | rock_albedo.png | 2.9 → 0.1 | 2.9 → 0.1 |
  | rock_height.png | 4.7 → 0.1 | 4.7 → 0.1 |
  | rock_normal.png | 0.5 → 0.0 | 0.5 → 0.0 |
  | rock_roughness.png | 3.1 → 0.1 | 3.1 → 0.1 |

- `seamproof fix …/ground_albedo.png --score-only` (README's second form)
  also works and writes nothing.
- Regenerating the examples in a copy (`examples/generate_examples.py`)
  reproduces all five shipped example PNGs **byte-identical** — the examples
  are deterministic and genuinely produced by the stated script.

## 3. Seam score — independent re-implementation

The score was re-implemented from the README text alone (3×3 toroidal box
blur; S = clamp(min(H,W)//32, 1, 4) edge strips; mean of horizontal/vertical
strip differences) and compared to `core.seam_score` on random images of
three shapes (128×128×3, 64×96×3, 256×256×1): **agreement to <1e-9 in all
cases.** The published definition is the implemented definition.

Independent re-scoring of the *saved* demo outputs gave: ground 23.7→0.4,
rock_albedo 2.9→0.1, rock_roughness 3.1→0.1 (exact), rock_height →0.3
(reported 0.1), rock_normal →0.2 (reported 0.0). See observation 1.

## 4. Honesty mechanism (band repaint downgrade)

My own fixture (fresh RNG, not the tool's test fixture): flat field, white
disk (r=40) on the left edge, black disk on the right edge, white top bar /
black bottom bar:

- score **161.5 → 10.3**, band repaint **54.5**, CLI prints the repaint and a
  **poor** verdict. PASS.
- The specific *downgrade* branch (after-score ≤ 8 bought with repaint > 25)
  was also triggered deliberately (disk r=35, bars 4px): score → **7.6**,
  repaint **33.1**, verdict = "poor - low score only because the seam band
  was heavily repainted…". PASS.
- README prints the test-suite case as 158.4 → 10.2, repaint 51.7. Those
  exact decimals are specific to that test module's shared-RNG fixture
  state and were not reproduced digit-for-digit; my independent fixture of
  the same construction lands within ~2% on all three numbers, and the
  tool's own test asserts the same thresholds (before > 100, repaint > 25,
  verdict poor). The claim is honest in substance.

## 5. Registration (independent)

Heightfield built from integer-frequency sinusoids (exactly tileable, not
the tool's blob generator); normals derived with my own `np.gradient` code;
set fixed through `core.fix_array` with one shared geometry; normal then
recomputed from the *fixed* height with my derivation and compared:

- **mean angular error 0.547°, p95 2.399°, max 6.292°** — inside the tool's
  published test bars (mean < 3°, p95 < 10°). PASS.
- Same check on the shipped rock set (strength 2.5 per its generator):
  mean **0.342°**, p95 **0.914°**. PASS.
- Changed-pixel masks for height vs roughness are pixel-identical (7168 px
  each): data maps receive the identical geometry and no per-map detrend,
  as claimed. PASS.

## 6. Interior preservation (--no-detrend)

Random-noise 128×128 texture, band 16: **0 differing pixels** in the
interior region (rows/cols 17…110); all 7168 changed pixels lie in the
outer band. The README's "pixels outside the band are returned
bit-identical (with --no-detrend)" holds exactly. PASS.

## 7. Normal maps

- After fix, decoded vectors are unit length to 1.0000 (float) for both a
  valid input and a deliberately non-unit flat input (200, 30, 90), which
  is correctly renormalised; z stays positive everywhere. PASS.
- Saved rock_normal.png: norm mean 1.0003, max deviation from 1.0 = 0.0018
  (uint8 quantisation only), z > 0 everywhere. PASS.

## 8. DirectX (Y−) and alpha — code/README consistency

- `_normaldx` and `_normalgl` both parse to type `normal`; processing a
  green-inverted (DirectX-style) map produces exactly the green-inverted
  OpenGL result (deviation from the no-flip expectation ~1e-13). **No green
  flip is performed** — precisely what the README's limits section states.
  Consistent. PASS.
- Alpha passthrough: RGBA input with a patterned alpha (including 0 and
  255 regions) and an LA input both came out with the **alpha channel
  byte-identical** and RGB/L fixed. Matches the README claim. PASS.

## 9. Malformed / edge inputs (all via the real CLI entry point)

| input | result |
|---|---|
| empty file named .png | rc 2, "error: not a readable image", no traceback |
| text file named .png | rc 2, same clean error |
| truncated PNG (40 bytes) | rc 2, same clean error |
| 1×1 image | rc 0, "too small to blend" warning, copied unchanged |
| fully transparent 64×64 RGBA | rc 0, written, score 0.0 (see obs. 5) |
| mismatched PBR set (64×64 + 32×32) | rc 2, error names both files and sizes |
| folder with no images (empty) | rc 2, "no image files found" |
| folder with only a .txt file | rc 2, "no image files found" (see obs. 6) |
| nonexistent path | rc 2, "no such file or folder" |
| missing --out (no --score-only) | rc 2, clean error |
| --band 0 / −5 / 100000 | no crash; clamped (see obs. 3) |
| palette PNG, non-square 80×48, JPEG, uppercase .PNG | all rc 0, correct size out |
| 16-bit PNG | rc 0, silently down-converted to 8-bit L (see obs. 4) |
| constant image | output bit-identical, score 0.0 |
| already-tileable toroidal texture | score 1.27 → 0.11 (not damaged) |

## Bugs

**Found:** none that break a claim or a verdict.
**Fixed:** none — no tool code was changed in this review.

## Minor observations (recorded, not fixed)

1. **Certified score is measured pre-save.** The CLI scores the float array
   before uint8 rounding; re-scoring the saved files gave rock_height 0.3
   (reported 0.1) and rock_normal 0.2 (reported 0.0). Same verdict band
   ("good") in both cases, but the printed number is the float's, not the
   file's, to within ~0.2.
2. **Partial outputs on folder failure.** If one image in a folder is
   corrupt, the run aborts with a clean rc 2 — but sets processed before it
   have already been written to the output folder. The error is honest; the
   half-written output folder could surprise a script.
3. **--band is silently clamped.** 0 or negative becomes a 1px band (score
   barely moves, e.g. 18.3 → 17.2 on noise) with no warning; a huge band
   clamps to half the image — in that case the repaint downgrade correctly
   fired (33.4 → poor).
4. **16-bit PNGs are silently down-converted** to 8-bit. The README limits
   do say "8-bit images", but no warning is printed when it happens.
5. **Fully transparent images score 0.0 "good"** — vacuously true (nothing
   is visible), and the invisible RGB under transparent pixels is still
   blended/detrended. Alpha itself is untouched, as documented.
6. **Cosmetic:** in a folder containing only non-image files, the collected
   "skipping non-image file" warnings are never printed, because the
   "no image files" error raises first.

## Honest remaining limits

The README's own limits section is accurate and was not contradicted by
any probe: seamless ≠ repetition-free (the score is an edge metric, not a
repetition metric); strong unique content crossing an edge is reported,
not hidden; detrend flattens deliberate broad shading in colour maps;
alpha seams are not fixed; DirectX maps are not flipped; one size per set;
<8px images are copied unchanged. Add observation 1 above: treat printed
scores as accurate to ~0.2 for the saved file.

**Bottom line: 15/15 tests, fresh install exact, demo numbers exact,
registration 0.55° mean on an independent derivation, honesty downgrade
fires on independent fixtures. Cleared on correctness grounds.**

---

## Addendum — benchmark round (2026-11-17, after the review above)

A separate benchmark round compared seamproof against a textbook
offset-blend baseline (our own reimplementation of the classic method)
on a shared 8-texture suite plus a PBR set, scored with an independent
scorer written from first principles (not seamproof's scorer). Full
method, tables, and the internal context are in
`BENCHMARK_INTERNAL.md` (internal file; not part of the public repo
claims).

Summary of findings:

- seamproof beat the baseline on every quality metric (raw wrap-edge
  difference and a low-frequency tiling-grid measure) on every case,
  on both the dev suite and a held-out suite with different seeds
  (e.g. wrap-edge ≤ 0.05 vs baseline up to 8.88; low-frequency grid
  ≤ 2.11 vs up to 6.96). PBR registration was a tie (≈ 0.3° mean for
  both, own derivation).
- The baseline's only wins — zero interior change and slightly lower
  band repaint — are the no-detrend tradeoff: seamproof with
  `--no-detrend` also has exactly zero interior change on every case
  while still beating the baseline's edge score everywhere.
- Three candidate improvements were built and measured, and all were
  **rejected on held-out evidence** (details in BENCHMARK_INTERNAL.md):
  a polynomial-trend detrend (worse interior change and worse
  low-frequency scores), an adaptive detrend trigger (no statistic
  separated vignette textures from content textures without
  overfitting), and a repetition warning measure (false-flagged a
  regular brick pattern, missed a blob on noise — not shipped, so the
  README's plain-language "seamless ≠ repetition-free" limit remains
  the honest form of that warning).
- **No seamproof code was changed in this round.** After the round:
  full suite re-run — **15/15 OK**; the review's key probes are
  covered by that suite (honesty disk case still downgrades to poor,
  interior bit-identical with `--no-detrend`, normal maps unit
  length) and the CLI demo still prints ground 23.7 → 0.4.
