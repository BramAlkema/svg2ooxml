# Animation W3C Review - 2026-02-21

- `run_date`: 2026-02-21
- `git_sha`: `4a16e34`
- `profiles_executed`:
  - Profile A: `gradients`, `shapes`
  - Profile B: animation sample (`sample_size=20`, `sample_seed=20260221`)
- `decks_total`: 66
- `decks_failed`: 0
- `known_failures`: none
- `new_failures`: none
- `action_items`:
  - Keep current baseline as reference for next animation PR.
  - Continue tracking profile metrics in `docs/telemetry/animation-w3c-profile-trend.csv`.

## Results

| Profile | Report | Decks | Failed | Native | EMF | Raster | Gate |
|---|---|---:|---:|---:|---:|---:|---|
| A (gradients) | `tests/corpus/w3c/report_gradients.json` | 24 | 0 | 87.1% | 12.2% | 0.7% | PASS |
| A (shapes) | `tests/corpus/w3c/report_shapes.json` | 22 | 0 | 100.0% | 0.0% | 0.0% | PASS |
| B (animate sample) | `tests/corpus/w3c/report_animation.json` | 20 | 0 | 100.0% | 0.0% | 0.0% | PASS |

## Failure Bucket Review

- Parse failures: 0
- Mapping failures: 0
- Timing generation failures: 0
- Policy suppression failures: 0

No follow-up fix issues were created because there were no failed decks and no new regressions in required profiles.
