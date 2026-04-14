# Recipes

Complete copy-pasteable examples for common PowerPoint animation patterns.
Every recipe below has been verified end-to-end — the commands produce
XML that actually plays in Microsoft PowerPoint, not just XML that
parses.

## Simple entrance effects

### Fade in

```bash
python scripts/emit_entrance.py --shape 2 --filter fade --duration 1500
```

### Wipe right

```bash
python scripts/emit_entrance.py --shape 2 --filter "wipe(right)" --duration 800
```

### Circle in (elliptical reveal)

```bash
python scripts/emit_entrance.py --shape 2 --filter "circle(in)" --duration 1500
```

### Checkerboard reveal

```bash
python scripts/emit_entrance.py --shape 2 --filter "checkerboard(across)" --duration 2000
```

List all verified entrance filters:

```bash
python scripts/emit_entrance.py --list-filters
```

## Exit effects

### Fade out

```bash
python scripts/emit_exit.py --shape 2 --filter fade --duration 500
```

### Wipe up (disappear going up)

```bash
python scripts/emit_exit.py --shape 2 --filter "wipe(up)" --duration 500
```

## Motion path

### Diagonal move

```bash
python scripts/emit_motion.py \
  --shape 2 --path "M 0 0 L 0.25 0.25 E" --duration 2000
```

### Curved path

```bash
python scripts/emit_motion.py \
  --shape 2 --path "M 0 0 C 0.3 0 0.3 0.3 0 0.3 E" --duration 3000
```

Path coordinates are slide-relative (0..1 range). `E` terminates
the path. Use `M` for move, `L` for line, `C` for cubic Bézier.

## Single-effect emphasis (via compound)

### Text color change

```bash
python scripts/emit_compound.py --shape 2 --duration 2000 \
  --behaviors '[{"name": "text_color", "tokens": {"BEHAVIOR_ID": 10, "TO_COLOR": "E81E1E"}}]'
```

### Rotate 360°

```bash
python scripts/emit_compound.py --shape 2 --duration 2000 \
  --behaviors '[{"name": "rotate", "tokens": {"BEHAVIOR_ID": 10, "ROTATION_BY": "21600000"}}]'
```

### Grow 150%

```bash
python scripts/emit_compound.py --shape 2 --duration 1500 \
  --behaviors '[{"name": "scale", "tokens": {"BEHAVIOR_ID": 10, "BY_X": "150000", "BY_Y": "150000"}}]'
```

### Transparency (fade to 50% and hold)

```bash
python scripts/emit_compound.py --shape 2 --duration 2000 \
  --behaviors '[{"name": "transparency", "tokens": {"SET_BEHAVIOR_ID": 10, "EFFECT_BEHAVIOR_ID": 11, "TARGET_OPACITY": "0.5"}}]'
```

## Stacked effects

### Color + rotate + fade (simultaneous)

```bash
python scripts/emit_compound.py --shape 2 --duration 3000 \
  --behaviors '[
    {"name": "text_color", "tokens": {"BEHAVIOR_ID": 10, "TO_COLOR": "FFD700"}},
    {"name": "rotate",     "tokens": {"BEHAVIOR_ID": 20, "ROTATION_BY": "21600000"}},
    {"name": "transparency", "tokens": {"SET_BEHAVIOR_ID": 30, "EFFECT_BEHAVIOR_ID": 31, "TARGET_OPACITY": "0.3"}}
  ]'
```

### Shape fill + text color (change shape and its text together)

```bash
python scripts/emit_compound.py --shape 2 --duration 2000 \
  --behaviors '[
    {"name": "fill_color", "tokens": {"STYLE_CLR_BEHAVIOR_ID": 10, "FILL_CLR_BEHAVIOR_ID": 11, "FILL_TYPE_BEHAVIOR_ID": 12, "FILL_ON_BEHAVIOR_ID": 13, "TO_COLOR": "C81010"}},
    {"name": "text_color", "tokens": {"BEHAVIOR_ID": 20, "TO_COLOR": "FFFFFF"}}
  ]'
```

### Motion + rotate (shape rotates while moving)

```bash
python scripts/emit_compound.py --shape 2 --duration 3000 \
  --behaviors '[
    {"name": "motion", "tokens": {"BEHAVIOR_ID": 10, "PATH_DATA": "M 0 0 L 0.3 0.2 E"}},
    {"name": "rotate", "tokens": {"BEHAVIOR_ID": 20, "ROTATION_BY": "10800000"}}
  ]'
```

### Bold underline (text formatting cascade)

```bash
python scripts/emit_compound.py --shape 2 --duration 2000 \
  --behaviors '[
    {"name": "bold",      "tokens": {"BEHAVIOR_ID": 10}},
    {"name": "underline", "tokens": {"BEHAVIOR_ID": 20}}
  ]'
```

## Debugging

### Validate XML from elsewhere

If someone hands you a `timing.xml` fragment and you want to check it:

```bash
cat timing.xml | python scripts/validate.py
```

Non-empty output means there are dead paths; empty means clean.

### Look up a filter

```bash
python scripts/query_vocabulary.py filter wipe
```

### Check if an attrName is valid

```bash
python scripts/query_vocabulary.py attrname fill.opacity
# (nothing — it's not in the valid vocabulary)

python scripts/query_vocabulary.py dead fill.opacity
# lists the dead path entry with its replacement
```

### List all 17 valid attrNames

```bash
python scripts/query_vocabulary.py attrname
```

## Patterns that DON'T work

These are compiled into `oracle/dead_paths.xml`. Run
`python scripts/query_vocabulary.py dead` to see them all. The most
common failures:

- **`<p:anim>` on `fill.opacity`** — use `transparency` fragment
- **`<p:anim>` on `stroke.weight`** — no native path; use EMF fallback
- **`<p:anim>` on `style.fontSize` alone** — requires full preset 28
  compound (animClr + animClr + set + anim siblings)

When in doubt, validate:

```bash
echo '<p:anim xmlns:p="..."><p:cBhvr><p:attrNameLst><p:attrName>fill.opacity</p:attrName></p:attrNameLst></p:cBhvr></p:anim>' \
  | python scripts/validate.py
```

Output:

```
line 1: p:anim {attrName='fill.opacity'} — DEAD PATH (silently-dropped)
  id:          anim-fill-opacity
  replacement: emph/transparency
  note:        Use preset 9 Transparency — p:set style.opacity + ...
```
