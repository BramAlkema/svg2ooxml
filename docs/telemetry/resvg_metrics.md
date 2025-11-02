# Resvg Telemetry Metrics

Resvg filter decisions are now summarised alongside PPTX jobs so staging
dashboards can track adoption and hotspots without parsing raw trace events.

## Metric fields

Conversion summaries (written back to Firestore) contain a `conversion.resvg_metrics`
object with the following counters:

| Metric                | Description                                                                 |
| --------------------- | --------------------------------------------------------------------------- |
| `attempts`            | Count of resvg planning executions (`resvg_attempt`).                       |
| `plan_characterised`  | Planner runs that produced a primitive summary (`resvg_plan_characterised`).|
| `promotions`          | Successful promotions to vector/EMF (`resvg_promoted_emf`).                 |
| `policy_blocks`       | Promotions vetoed by policy (`resvg_promotion_policy_blocked`).             |
| `lighting_candidates` | Lighting primitives seen during promotion that remain raster for now.       |
| `lighting_promotions` | Lighting primitives handled via the promotion factories (prototype stage). |
| `successes`           | Resvg executions that returned a bitmap fallback (`resvg_success`).         |
| `failures`            | Planner/execution failures (unsupported primitives, runtime errors, etc.). |

All counters are optional; zero-valued metrics are omitted to keep documents lean.

## Example Firestore document

```json
{
  "conversion": {
    "slide_count": 4,
    "stage_totals": {...},
    "geometry_totals": {...},
    "paint_totals": {...},
    "resvg_metrics": {
      "attempts": 5,
      "plan_characterised": 5,
      "promotions": 3,
      "policy_blocks": 1,
      "lighting_candidates": 2,
      "successes": 2,
      "failures": 0
    },
    "page_titles": ["Title slide", "Overview", "Demo", "CTA"]
  },
  ...
}
```

## Dashboard scaffolding

### BigQuery (Firestore export)

With Firestore-to-BigQuery exports enabled, you can surface conversion trends:

```sql
SELECT
  TIMESTAMP_TRUNC(timestamp, DAY) AS day,
  SUM(conversion.resvg_metrics.promotions) AS promotions,
  SUM(conversion.resvg_metrics.policy_blocks) AS policy_blocks,
  SUM(conversion.resvg_metrics.lighting_candidates) AS lighting_candidates
FROM `project.firestore_exports.svg_jobs_raw`
WHERE conversion.resvg_metrics IS NOT NULL
GROUP BY day
ORDER BY day DESC;
```

### Looker / Data Studio

1. Connect to the BigQuery view containing the metrics.
2. Add scorecards for `promotions`, `policy_blocks`, and `lighting_candidates`.
3. Visualise `promotions / attempts` as an adoption percentage.
4. Use filters (file id, exporter version, policy profile) to drill into regressions.

### Alerting

Monitor elevated `failures` or `policy_blocks` by wiring a Cloud Function /
Dataform job that checks the latest day’s totals and posts to Slack when they
cross your SLO.

## Integrating with existing dashboards

* Update your ingestion schema to capture `conversion.resvg_metrics` if it is
  currently ignored.
* Backfill recent documents (last 30 days) so trend lines are continuous.
* Annotate dashboards with the date resvg metrics landed (see project changelog)
  to contextualise step changes.

Need other counters? Emit additional `filter:*` stage events in
`svg2ooxml/services/filter_service.py` and they’ll roll up automatically.
