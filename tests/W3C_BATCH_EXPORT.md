# W3C Batch Export to Google Slides

Batch export all 525 W3C SVG test files to Google Slides via the Cloud Run API.

## Prerequisites

### 1. Share Google Drive Folder

Share your target Google Drive folder with the service account:

```
svg2ooxml-runner@powerful-layout-467812-p1.iam.gserviceaccount.com
```

**Permissions:** Editor (so it can create Slides presentations)

### 2. Get Drive Folder ID

From your Drive folder URL:
```
https://drive.google.com/drive/folders/1LsnrNyo8nnBCG0gWC8F8T2T2JQzJpP5a
                                          ↑
                                          This is the folder ID
```

### 3. Set Environment Variables

```bash
# Authentication token
export FIREBASE_TOKEN="$(gcloud auth print-identity-token)"

# Target Drive folder
export DRIVE_FOLDER_ID="1LsnrNyo8nnBCG0gWC8F8T2T2JQzJpP5a"
```

## Usage

### Quick Start (Test with 5 files)

```bash
source .venv/bin/activate
export FIREBASE_TOKEN="$(gcloud auth print-identity-token)"
export DRIVE_FOLDER_ID="YOUR_FOLDER_ID"

python tests/batch_export_w3c.py --limit 5
```

### Full Export (All 525 files)

```bash
python tests/batch_export_w3c.py \
  --batch-size 10 \
  --delay 15
```

**Estimated time:** ~2-3 hours for all 525 files

### Custom Export

```bash
# Export only gradient tests
python tests/batch_export_w3c.py \
  --pattern "*grad*.svg" \
  --batch-size 5

# Export with faster batching (use cautiously)
python tests/batch_export_w3c.py \
  --limit 50 \
  --batch-size 10 \
  --delay 5
```

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--limit N` | None | Process only first N files (for testing) |
| `--batch-size N` | 5 | Number of files to process in parallel |
| `--delay SECONDS` | 10 | Delay between batches (prevents rate limiting) |
| `--pattern` | `*.svg` | File pattern to match |
| `--output` | `w3c_batch_report.json` | Output report file |

## Output

### Report File

The script generates `w3c_batch_report.json` containing:

```json
{
  "started_at": "2025-01-05T15:30:00",
  "completed_at": "2025-01-05T17:45:00",
  "total_files": 525,
  "submitted": 525,
  "completed": 520,
  "failed": 5,
  "skipped": 0,
  "results": [
    {
      "svg_file": "pservers-grad-01-b.svg",
      "job_id": "abc-123",
      "status": "completed",
      "slides_url": "https://docs.google.com/presentation/d/...",
      "slides_presentation_id": "1X2Y3Z...",
      "duration_seconds": 12.5
    },
    ...
  ]
}
```

### Google Drive

All generated Slides presentations will appear in your specified Drive folder with titles like:
- `W3C Test: pservers-grad-01-b`
- `W3C Test: shapes-rect-01-t`
- etc.

## Performance

**Batch processing:**
- Default: 5 files per batch, 10s delay between batches
- ~30 files per 5 minutes
- Full 525 files: ~2-3 hours

**Recommended settings:**
- **Testing:** `--limit 10 --batch-size 5 --delay 5`
- **Production:** `--batch-size 10 --delay 15`
- **Conservative:** `--batch-size 5 --delay 20` (prevents any rate limiting)

## Troubleshooting

### "Authentication token missing"

```bash
export FIREBASE_TOKEN="$(gcloud auth print-identity-token)"
```

Token expires after 1 hour. Re-run if you see authentication errors.

### "Permission denied" in Drive

Make sure you've shared the folder with:
```
svg2ooxml-runner@powerful-layout-467812-p1.iam.gserviceaccount.com
```

### Rate limiting / 429 errors

Increase `--delay` between batches:
```bash
python tests/batch_export_w3c.py --delay 30
```

### Quota exceeded (402 Payment Required)

Make sure quota is disabled on the Cloud Run service:
```bash
gcloud run services update svg2ooxml-export \
  --region=europe-west1 \
  --update-env-vars=DISABLE_EXPORT_QUOTA=true
```

### Resume after interruption

The script doesn't currently support resume. To continue after interruption:

1. Check the report file to see how many completed
2. Use `--limit` and file sorting to skip completed files
3. Or manually filter out completed files

## Analysis

After export completes, you can analyze the results:

```python
import json

# Load report
with open("w3c_batch_report.json") as f:
    report = json.load(f)

# Success rate
success_rate = report["completed"] / report["submitted"] * 100
print(f"Success rate: {success_rate:.1f}%")

# Failed files
failed = [r for r in report["results"] if r["status"] != "completed"]
print(f"Failed files ({len(failed)}):")
for result in failed:
    print(f"  - {result['svg_file']}: {result.get('error', 'Unknown error')}")

# Average duration
durations = [r["duration_seconds"] for r in report["results"] if r.get("duration_seconds")]
avg_duration = sum(durations) / len(durations) if durations else 0
print(f"Average export time: {avg_duration:.1f}s")
```

## Related Documentation

- [Smoke Tests](smoke/README.md) - Authentication methods
- [Testing Setup](../docs/TESTING_SETUP.md) - Quick reference guide
- [W3C Corpus](corpus/w3c/README.md) - W3C test suite information
