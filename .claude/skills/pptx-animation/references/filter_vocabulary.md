# Filter Vocabulary

The complete set of `<p:animEffect filter="...">` string values PowerPoint recognises.
Auto-generated from `oracle/filter_vocabulary.xml` — do not hand-edit.

Loaded programmatically via:

```python
from svg2ooxml.drawingml.animation.oracle import default_oracle
oracle = default_oracle()
vocab = oracle.filter_vocabulary()      # tuple[FilterEntry, ...]
entry = oracle.filter_entry('wipe(down)')
```

## Entries

| Filter | Entrance preset | Exit preset | Verification | Description |
|---|---|---|---|---|
| `fade` | 9/0 | 9/0 | visually-verified | opacity fade in/out |
| `dissolve` | 10/0 | 10/0 | visually-verified | pixel-noise dissolve reveal |
| `wipe(down)` | 22/4 | 22/4 | visually-verified | top-to-bottom directional reveal |
| `wipe(up)` | 22/1 | 22/1 | visually-verified | bottom-to-top directional reveal |
| `wipe(left)` | 22/8 | 22/8 | visually-verified | right-to-left directional reveal |
| `wipe(right)` | 22/2 | 22/2 | visually-verified | left-to-right directional reveal |
| `wedge` | 37/0 | 37/0 | visually-verified | wedge-slice reveal (pie-chart-like sweep) |
| `wheel(1)` | 21/1 | 21/1 | visually-verified | 1-spoke clock-wipe |
| `wheel(2)` | 21/2 | 21/2 | visually-verified | 2-spoke clock-wipe |
| `wheel(3)` | 21/3 | 21/3 | derived-from-handler | 3-spoke clock-wipe |
| `wheel(4)` | 21/4 | 21/4 | derived-from-handler | 4-spoke clock-wipe |
| `wheel(8)` | 21/8 | 21/8 | derived-from-handler | 8-spoke clock-wipe |
| `circle(in)` | 18/12 | 18/12 | visually-verified | elliptical reveal from center outward |
| `circle(out)` | 19/12 | 19/12 | visually-verified | elliptical reveal from edges inward |
| `strips(downLeft)` | 25/0 | 25/0 | visually-verified | diagonal strip reveal from upper-right to lower-left |
| `strips(downRight)` | 25/1 | 25/1 | derived-from-handler | diagonal strip reveal from upper-left to lower-right |
| `strips(upLeft)` | 25/2 | 25/2 | derived-from-handler | diagonal strip reveal from lower-right to upper-left |
| `strips(upRight)` | 25/3 | 25/3 | derived-from-handler | diagonal strip reveal from lower-left to upper-right |
| `blinds(horizontal)` | 42/10 | 42/10 | visually-verified | horizontal blinds reveal |
| `blinds(vertical)` | 42/5 | 42/5 | derived-from-handler | vertical blinds reveal |
| `checkerboard(across)` | 43/0 | 43/0 | visually-verified | checkerboard pattern reveal left-to-right |
| `checkerboard(down)` | 43/1 | 43/1 | derived-from-handler | checkerboard pattern reveal top-to-bottom |
| `barn(inVertical)` | 45/0 | 45/0 | visually-verified | vertical barn-door reveal collapsing inward |
| `barn(inHorizontal)` | 45/1 | 45/1 | derived-from-handler | horizontal barn-door reveal collapsing inward |
| `barn(outVertical)` | 45/2 | 45/2 | derived-from-handler | vertical barn-door reveal opening outward |
| `barn(outHorizontal)` | 45/3 | 45/3 | derived-from-handler | horizontal barn-door reveal opening outward |
| `randombar(horizontal)` | 52/0 | 52/0 | visually-verified | horizontal random-bar reveal |
| `randombar(vertical)` | 52/1 | 52/1 | derived-from-handler | vertical random-bar reveal |
| `image` | — | — | visually-verified | opacity holder used by emphasis effects (preset 9 transparency, preset 27 color pulse); takes an opacity value in the enclosing animEffect prLst="opacity: X"; NOT an entrance/exit filter on its own |

## Verification legend

- `visually-verified` — empirically confirmed playing in PowerPoint via the tune loop.
- `derived-from-handler` — structurally equivalent to a verified entry (e.g. additional direction/spoke subparameters).
