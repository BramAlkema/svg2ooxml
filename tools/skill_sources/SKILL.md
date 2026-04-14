---
name: pptx-animation
description: Emit PowerPoint animation XML that actually plays in slideshow, not just XML that parses as valid OOXML. Uses an empirically verified oracle of PowerPoint animation shapes with a negative catalog of silently-dropped dead paths. Invoke when authoring PowerPoint timing XML, converting SMIL/SVG animations, or debugging why a PPT animation fails to play despite valid markup.
---

# pptx-animation

**Problem:** PowerPoint's parser accepts many XML shapes that its playback
engine silently drops at slideshow time. `<p:anim attrName="fill.opacity">`
parses fine, round-trips cleanly, and animates nothing. Generating PPT
animations from ECMA-376 alone (or by plausibly guessing at element shapes)
produces broken output that looks correct but does not play.

**Solution:** Route every effect through this skill's oracle-backed
scripts. They wrap an empirically verified template library and a
catalog of falsified shapes to avoid. You describe the effect in
semantic terms (shape id, filter, duration, behaviors); the scripts
emit `<p:par>` XML ready to splice into a timing tree.

## Core rules — follow these or you will produce broken XML

1. **Never hand-write `<p:anim>`, `<p:animClr>`, `<p:animEffect>`,
   `<p:animScale>`, `<p:animRot>`, `<p:animMotion>`, or `<p:set>` trees.**
   Use the scripts in `scripts/` instead. Even if you think you know
   the right shape, the verification metadata, `bldP` build modes, and
   token plumbing have non-obvious constraints.

2. **These `attrName` values silently drop at playback — do not use them:**
   - `fill.opacity` → use `emit_compound.py` with a `transparency` behavior
   - `stroke.opacity` → no native path, EMF rasterization fallback
   - `stroke.weight` → no native path, EMF rasterization fallback
   - `line.weight` → no native path, EMF rasterization fallback
   - `style.fontSize` in isolation → requires full preset 28 compound
   - `<p:anim>` on `style.opacity` with tavLst → use `transparency` behavior
   See `references/dead_paths.md` for the full catalog with replacements.

3. **The valid `<p:attrName>` vocabulary has exactly 17 entries.**
   This has been confirmed exhaustive by scanning all authored
   PowerPoint reference files. See `references/attrname_vocabulary.md`.
   If the attribute you want to animate isn't in the list, it is not
   natively animatable — fall back to EMF rasterization.

4. **Prefer compound emission for stacked effects.** PowerPoint fires
   all behavior children of one `<p:cTn>` simultaneously on a single
   click. The compound API (`emit_compound.py`) emits this shape
   directly with arbitrary lists of behavior fragments. Nested `<p:par>`
   siblings work too but are structurally redundant.

## When to invoke this skill

- Authoring PowerPoint animation timing XML programmatically
- Converting SVG/SMIL animations to PPTX
- Debugging why a PowerPoint animation does not play
- Composing multi-effect stacks (fade + rotate + color change + ...)
- Validating hand-written or third-party timing XML

## Authoring flow — pick the right script

| Goal                                                   | Script                                  |
|--------------------------------------------------------|-----------------------------------------|
| Fade, wipe, wheel, circle, or other entrance effect    | `scripts/emit_entrance.py`              |
| Exit effect with the same filter vocabulary            | `scripts/emit_exit.py`                  |
| Emphasis effects (color, size, bold, transparency, …)  | `scripts/emit_compound.py`              |
| Motion path (shape moves along a path)                 | `scripts/emit_motion.py`                |
| Check XML you did not generate through these scripts   | `scripts/validate.py`                   |
| Look up a filter / attrName / dead-path entry          | `scripts/query_vocabulary.py`           |

Every script prints its output (usually a `<p:par>` XML fragment) to
stdout. Redirect into a file or pipe into your timing-tree assembler.

## Quick examples

### Entrance — wipe down

```bash
python scripts/emit_entrance.py \
  --shape 2 --filter "wipe(down)" --duration 1500
```

### Compound emphasis — 4 effects on one click

```bash
python scripts/emit_compound.py \
  --shape 2 --duration 3000 --par-id 5 \
  --behaviors '[
    {"name": "transparency", "tokens": {"SET_BEHAVIOR_ID": 10, "EFFECT_BEHAVIOR_ID": 11, "TARGET_OPACITY": "0.5"}},
    {"name": "fill_color", "tokens": {"STYLE_CLR_BEHAVIOR_ID": 20, "FILL_CLR_BEHAVIOR_ID": 21, "FILL_TYPE_BEHAVIOR_ID": 22, "FILL_ON_BEHAVIOR_ID": 23, "TO_COLOR": "C81010"}},
    {"name": "rotate", "tokens": {"BEHAVIOR_ID": 30, "ROTATION_BY": "21600000"}},
    {"name": "motion", "tokens": {"BEHAVIOR_ID": 40, "PATH_DATA": "M 0 0 L 0.2 0.1 E"}}
  ]'
```

### Validate untrusted XML

```bash
cat some_timing.xml | python scripts/validate.py
```

Non-empty output = dead paths found. Each issue names the offending
element, the verdict (`silently-dropped` / `requires-compound` / …),
and the replacement slot. Empty output = oracle-clean.

### Look up a filter or attrName

```bash
python scripts/query_vocabulary.py filter wipe
python scripts/query_vocabulary.py attrname style.visibility
python scripts/query_vocabulary.py dead fill.opacity
```

## Progressive disclosure

Start with `SKILL.md` (this file). If you need more detail:

- `references/oracle_overview.md` — the two-layer oracle architecture
- `references/filter_vocabulary.md` — 29 filter values, auto-generated
- `references/attrname_vocabulary.md` — the 17 valid attrNames
- `references/dead_paths.md` — every empirically falsified shape
- `references/compound_api.md` — the 10 behavior fragments in detail
- `references/examples.md` — complete recipes for common patterns
- `oracle/` — the raw SSOT XML files consumed by the scripts

## When the scripts don't cover your case

1. Check `references/attrname_vocabulary.md` to see if your target
   attribute is natively animatable.
2. Check `references/dead_paths.md` to see if your approach is a
   known failure with a documented replacement.
3. If the effect is expressible as a compound (multiple disjoint
   behavior channels on one shape), use `emit_compound.py` — it
   accepts any combination of the 10 behavior fragments.
4. If no oracle path exists, the effect probably can't be natively
   animated in current PowerPoint. Fall back to EMF rasterization or
   a discrete `<p:set>` step approximation.

## Self-test

After installing or updating this skill, run:

```bash
python scripts/emit_entrance.py --shape 2 --filter fade --duration 1000
```

You should see a well-formed `<p:par>` on stdout. If you see an
import error, the svg2ooxml package is not on the Python path — the
scripts import `svg2ooxml.drawingml.animation.oracle` directly, so
you need either the svg2ooxml repository or `pip install svg2ooxml`.
