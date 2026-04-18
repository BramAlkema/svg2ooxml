# figma2gslides

This folder holds the app-layer Figma and Google Slides surface that was split
out of the core `svg2ooxml` converter.

Contents:

- `run_api.py` — local runner for the extracted FastAPI app
- `figma-plugin/` — Figma plugin UI and sandbox code
- `google-workspace/` — Google Apps Script integration
- `docs/` — app-owned task docs, local runtime notes, and website notes
- `tools/` — local backend helpers for the extracted app runtime
- `website/` — hosted app/legal pages
- `figma-plugin-firebase-auth.md` — plugin auth integration notes

The Python app/runtime lives under `src/figma2gslides/`, with API routes and
services under `src/figma2gslides/api/`. The root `svg2ooxml` package remains
the converter library.

This is an extracted app surface kept in-repo for now. It is not part of the
supported `svg2ooxml` converter API.
