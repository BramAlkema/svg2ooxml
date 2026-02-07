# Staging Deployment Guide

This guide explains how to use the staging environment for testing before deploying to production.

## Overview

**Production Environment:**
- Branch: `main`
- Cloud Run: `svg2ooxml-export`
- URL: https://svg2ooxml-export-237932518206.europe-west1.run.app
- Firebase: https://powerful-layout-467812-p1.web.app
- Stripe: **Live mode** with real payments
- Plugin: Public release

**Staging Environment:**
- Branch: `develop` or `staging`
- Cloud Run: `svg2ooxml-export-staging` (deployed on-demand)
- URL: https://svg2ooxml-export-staging-[hash].europe-west1.run.app
- Firebase: Preview channels (temporary URLs)
- Stripe: **Test mode** with test cards
- Plugin: Private beta release

---

## Monthly Release Workflow

### Week 1-3: Development & Testing

1. **Create feature branch:**
   ```bash
   git checkout -b feature/new-feature develop
   ```

2. **Develop and test locally:**
   ```bash
   # Test locally
   source .venv/bin/activate
   python -m pytest
   uvicorn main:app --reload
   ```

3. **Merge to develop:**
   ```bash
   git checkout develop
   git merge feature/new-feature
   git push origin develop
   ```

4. **Auto-deploy to staging:**
   - GitHub Actions automatically deploys to staging
   - Or manually trigger: https://github.com/BramAlkema/svg2ooxml/actions/workflows/deploy-staging.yml

5. **Test in staging:**
   - Get staging URL from GitHub Actions output
   - Update Figma plugin to use staging API URL
   - Test with Stripe test cards
   - Share with beta testers

### Week 4: Production Release

6. **Merge to main:**
   ```bash
   git checkout main
   git merge develop
   git push origin main
   ```

7. **Auto-deploy to production:**
   - GitHub Actions automatically deploys to production
   - Or manually trigger: https://github.com/BramAlkema/svg2ooxml/actions/workflows/deploy-cloud-run.yml

8. **Update plugin:**
   - Update Figma plugin to use production API URL
   - Publish plugin to Figma Community

9. **Clean up staging (optional):**
   ```bash
   gcloud run services delete svg2ooxml-export-staging \
     --region=europe-west1 \
     --project=powerful-layout-467812-p1
   ```

---

## Manual Staging Deployment

### Deploy Staging Cloud Run

```bash
# Deploy staging
gcloud builds submit \
  --config cloudbuild-staging.yaml \
  --project=powerful-layout-467812-p1 \
  --region=europe-west1

# Get staging URL
gcloud run services describe svg2ooxml-export-staging \
  --region=europe-west1 \
  --project=powerful-layout-467812-p1 \
  --format='value(status.url)'
```

### Deploy Staging Firebase (Preview Channel)

```bash
# Create 30-day preview
firebase hosting:channel:deploy staging --expires 30d

# Get preview URL (shown in output)
# Example: https://powerful-layout-467812-p1--staging-abc123.web.app
```

### Delete Staging When Done

```bash
# Delete Cloud Run staging
gcloud run services delete svg2ooxml-export-staging \
  --region=europe-west1 \
  --project=powerful-layout-467812-p1

# Firebase preview channels auto-expire
```

---

## Stripe Test Mode

Staging uses Stripe Test Mode. Use these test cards:

**Successful Payment:**
- Card: `4242 4242 4242 4242`
- Expiry: Any future date
- CVC: Any 3 digits

**Payment Requires Authentication:**
- Card: `4000 0025 0000 3155`

**Payment Declined:**
- Card: `4000 0000 0000 9995`

More test cards: https://stripe.com/docs/testing

---

## Firestore Namespacing

Staging and production share the same Firestore database but use different collection prefixes:

**Production:**
- `subscriptions`
- `users`
- `usage`
- `webhook_events`

**Staging:**
- `staging_subscriptions`
- `staging_users`
- `staging_usage`
- `staging_webhook_events`

This is configured via `ENVIRONMENT=staging` in the staging Cloud Run service.

---

## Testing Checklist

Before merging to production, test the following in staging:

### Backend API
- [ ] Health check: `GET /health`
- [ ] Export job creation: `POST /api/v1/export`
- [ ] Job status polling: `GET /api/v1/export/{job_id}`
- [ ] Subscription status: `GET /api/v1/subscription/status`

### Payment Flow
- [ ] Create checkout session: `POST /api/v1/subscription/checkout`
- [ ] Complete test payment with Stripe test card
- [ ] Verify subscription created in Firestore
- [ ] Test customer portal: `POST /api/v1/subscription/portal`
- [ ] Test subscription cancellation

### Webhooks
- [ ] Stripe webhook receives events
- [ ] Subscription updates reflected in database
- [ ] Idempotency prevents duplicate processing

### Figma Plugin
- [ ] Plugin connects to staging API
- [ ] Export functionality works
- [ ] Payment flow completes successfully
- [ ] Error handling works correctly

---

## Cost Management

**Staging costs when deployed:**
- Cloud Run: ~$0-5/month (mostly idle)
- Firebase Hosting Preview: $0 (free tier)
- Firestore: $0 (shared with production)
- Cloud Build: $0 (free tier)

**Total: ~$0-5/month**

**Cost optimization:**
- Deploy staging only when testing
- Delete staging after testing complete
- Preview channels auto-expire (30 days)

---

## Troubleshooting

### Staging deployment fails
```bash
# Check Cloud Build logs
gcloud builds list --region=europe-west1 --limit=5

# View specific build
gcloud builds log BUILD_ID --region=europe-west1
```

### Staging service not responding
```bash
# Check Cloud Run logs
gcloud run services logs read svg2ooxml-export-staging \
  --region=europe-west1 \
  --limit=50
```

### Firestore permission errors
Staging uses the same service account as production with all necessary permissions already configured.

---

## Branch Strategy

```
main (production)
  └── develop (staging)
       ├── feature/payment-improvements
       ├── feature/new-export-format
       └── bugfix/firestore-query
```

**Branch rules:**
- `main`: Protected, requires PR approval
- `develop`: Integration branch, auto-deploys to staging
- `feature/*`: Feature branches, merge to develop
- `bugfix/*`: Bug fixes, merge to develop or main (hotfix)

---

## Environment Variables

### Production (`main` branch)
```
ENVIRONMENT=production
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PRICE_ID_PRO=price_1SP750...
STRIPE_PRICE_ID_ENTERPRISE=price_1SP75J...
```

### Staging (`develop` branch)
```
ENVIRONMENT=staging
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PRICE_ID_PRO=price_test_pro
STRIPE_PRICE_ID_ENTERPRISE=price_test_enterprise
```

---

## Questions?

- GitHub Workflows: `.github/workflows/`
- Cloud Build configs: `cloudbuild.yaml`, `cloudbuild-staging.yaml`
- Documentation: `docs/`
