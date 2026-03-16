# Project Roadmap

Last updated: 2026-03-17

## Current Status (v0.4.0)

- **Core pipeline**: SVG → IR → DrawingML → PPTX working. 1958 unit tests pass.
  W3C corpus at 98%+ OpenXML compliance via `openxml-audit`.
- **Deployment**: API live on Coolify at `svg2ooxml.tactcheck.com`. Supabase
  Google OAuth replaces Firebase. Synchronous conversion (no job queue).
- **PyPI**: Published as `pip install svg2ooxml`. Trusted publishing via
  GitHub Actions OIDC.
- **Repo**: Public at `github.com/BramAlkema/svg2ooxml`. CI: unit tests +
  W3C sample with OpenXML validation.
- **Figma plugin**: Rewritten for Supabase auth + Coolify backend. Pending
  end-to-end testing.

## What was removed (v0.3–v0.4)

- Firebase Auth, Firestore, Cloud Storage, Cloud Tasks
- Stripe subscriptions / payment tiers
- Huey/Redis background queue (conversion is synchronous now)
- GCP Cloud Run deployment (replaced by Coolify)
- ~27,600 lines of dead code, orphaned modules, defunct infrastructure

## Next milestone (v0.5.0)

### Blocking

- [ ] End-to-end Figma plugin test (sign in → export → Slides link)
- [ ] Google OAuth consent screen: verify status on `do-this-484623`, publish
      if still in "Testing" mode
- [ ] Fix issues found during plugin testing

### Quality

- [ ] Redeploy API with latest hardening (background cleanup, rate limiter sweep)
- [ ] Switch CI badge from static to live GitHub Actions badge
- [ ] Add CI visual comparisons (resvg vs legacy) and publish diff artifacts

### Pipeline

- [ ] Fill remaining DrawingML writer gaps
- [ ] Add end-to-end pipeline tests
- [ ] Define resvg parity thresholds and flip resvg to default

## Future

- Conversion timeout (prevent hung threads on malformed SVGs)
- Async conversion option for large multi-frame exports
- Font embedding improvements (WOFF2 support without FontForge)
- Visual regression CI with LibreOffice screenshots
