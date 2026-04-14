# Animation Oracle SSOT

Canonical `<p:par>` fragments describing every PowerPoint animation shape
svg2ooxml emits. Follows the same `{TOKEN}` substitution convention as
`src/svg2ooxml/assets/pptx_scaffold/`.

## Layout

```
animation_oracle/
├── README.md              (this file)
├── index.json             (slot metadata + SMIL mapping)
├── entr/                  (entrance presets)
├── exit/                  (exit presets)
├── emph/                  (emphasis presets)
└── path/                  (motion-path presets)
```

Each template file is a single `<p:par>` element — the *effect par*, not the
surrounding `mainSeq`/`clickGroup` boilerplate which `AnimationXMLBuilder`
produces unchanged. Loading a template = reading the file, substituting
tokens, parsing into an `lxml` element, and passing it to the existing
`build_timing_tree` alongside the other effect pars for the slide.

## Tokens

| Token                 | Meaning                                                  |
| --------------------- | -------------------------------------------------------- |
| `{SHAPE_ID}`          | target shape `spid`                                      |
| `{PAR_ID}`            | effect par `cTn/@id` (also reused as `grpId`)            |
| `{BEHAVIOR_ID}`       | sole inner behavior `cTn/@id`                            |
| `{SET_BEHAVIOR_ID}`   | first inner `cTn/@id` for templates with a `<p:set>`     |
| `{EFFECT_BEHAVIOR_ID}`| second inner `cTn/@id` for templates with animEffect    |
| `{DURATION_MS}`       | animation duration in milliseconds                       |
| `{DELAY_MS}`          | start delay in milliseconds                              |
| Content placeholders  | Per-template — see the `content_tokens` field in `index.json` (e.g. `{FROM_COLOR}`, `{ROTATION_BY}`, `{PATH_DATA}`) |

## Verification states

Every template in `index.json` carries a `verification` field:

- `derived-from-handler` — extracted from an existing golden master; reflects
  what the current svg2ooxml handlers emit. Starting point.
- `oracle-matched` — structurally equivalent (same `family_signature`) to a
  fragment in `docs/research/powerpoint_oracle/`. Trusted.
- `visually-verified` — confirmed to play correctly in Microsoft PowerPoint
  via `tools/visual/animation_tune.py`. Highest confidence.

Promote templates up this ladder by running the tune loop and the oracle
fragment diff.

## Usage

```python
from svg2ooxml.drawingml.animation.oracle import AnimationOracle

oracle = AnimationOracle()
par = oracle.instantiate(
    "entr/fade",
    shape_id="2",
    par_id=6,
    set_behavior_id=7,
    effect_behavior_id=71,
    duration_ms=1500,
    delay_ms=0,
)
```
