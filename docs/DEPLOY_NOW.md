# Deploy Now - Quick Start Guide

## 🚀 Ready to Deploy!

Your svg2ooxml payment integration is complete and ready for production. This guide will get you deployed in **~1 hour**.

---

## Deployment Strategy

**Automated via GitHub Actions** ✅
- Push to `main` branch → Automatic deployment
- No manual Firebase/gcloud commands needed
- CI/CD pipeline handles everything

---

## Step-by-Step Deployment

### 1. Setup GitHub Actions (30 minutes)

Run the automated setup script:

```bash
./scripts/setup-github-deployment.sh
```

This script will:
- ✅ Guide you through getting Firebase token
- ✅ Create Workload Identity Federation
- ✅ Create service account with permissions
- ✅ Output GitHub Secrets you need to add

**Manual steps required**:
1. Run `firebase login:ci` to get token
2. Add 3 secrets to GitHub repository settings
3. Done!

**Alternatively**, follow the detailed guide: `docs/GITHUB_DEPLOYMENT_SETUP.md`

### 2. Setup Stripe Products (15 minutes)

```bash
# Run interactive setup
./scripts/stripe-setup.sh

# Choose option 1 or 7 to create products
# This creates Pro ($9/month) and Enterprise ($49/month)
# Saves price IDs to .env file
```

**Or manually**:
1. Go to https://dashboard.stripe.com/test/products
2. Create Pro product ($9/month recurring)
3. Create Enterprise product ($49/month recurring)
4. Copy price IDs

### 3. Configure Stripe Webhook (5 minutes)

```bash
# Get your Cloud Run URL
gcloud run services describe svg2ooxml-export \
  --region=europe-west1 \
  --format='value(status.url)'

# Output example: https://svg2ooxml-export-sghya3t5ya-ew.a.run.app
```

Then:
1. Go to https://dashboard.stripe.com/test/webhooks
2. Click "Add endpoint"
3. URL: `https://svg2ooxml-export-sghya3t5ya-ew.a.run.app/api/webhook/stripe`
4. Select events:
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
5. Copy webhook signing secret

### 4. Set Environment Variables (5 minutes)

**Option A: GitHub Secrets** (Recommended)

Add these to GitHub Secrets:
```
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID_PRO=price_...
STRIPE_PRICE_ID_ENTERPRISE=price_...
```

Then update `.github/workflows/deploy-cloud-run.yml` to set them on Cloud Run.

**Option B: Direct Cloud Run**

```bash
gcloud run services update svg2ooxml-export \
  --region=europe-west1 \
  --project=powerful-layout-467812-p1 \
  --set-env-vars="
ENVIRONMENT=production,
STRIPE_SECRET_KEY=sk_test_YOUR_KEY,
STRIPE_WEBHOOK_SECRET=whsec_YOUR_SECRET,
STRIPE_PRICE_ID_PRO=price_YOUR_PRO_ID,
STRIPE_PRICE_ID_ENTERPRISE=price_YOUR_ENT_ID
"
```

### 5. Deploy! (5 minutes)

```bash
# Stage all changes
git add .

# Commit
git commit -m "feat: add Stripe payment integration and GitHub Actions deployment

- Add subscription management endpoints
- Add Stripe webhook handlers
- Add usage tracking and quota enforcement
- Add plugin subscription UI
- Add GitHub Actions workflows for automated deployment
- Add Firebase Hosting payment pages
- Add comprehensive documentation

Closes #payment-integration"

# Push to main (triggers deployment)
git push origin main
```

**What happens**:
1. GitHub Actions detects push to `main`
2. Runs tests (existing test suite)
3. Deploys Firebase (Hosting + Firestore rules)
4. Deploys Cloud Run (backend API)
5. Runs health check
6. Posts summary to GitHub Actions

**Monitor deployment**:
- GitHub: https://github.com/YOUR_USERNAME/svg2ooxml/actions
- Logs: `gcloud run services logs tail svg2ooxml-export --region=europe-west1`

### 6. Test End-to-End (10 minutes)

```bash
# Test Firebase Hosting
curl https://powerful-layout-467812-p1.web.app/auth.html
curl https://powerful-layout-467812-p1.web.app/payment-success.html

# Test Cloud Run health
SERVICE_URL=$(gcloud run services describe svg2ooxml-export \
  --region=europe-west1 \
  --format='value(status.url)')

curl $SERVICE_URL/health
# Should return: {"status":"healthy"}
```

**Test with Figma Plugin**:
1. Open Figma plugin
2. Sign in with Google ✅
3. Check subscription status (should show "Free Plan") ✅
4. Make an export ✅
5. Check usage (should show "1 / 5 exports") ✅

**Test Stripe Integration**:
```bash
# Use Stripe CLI to test webhooks
stripe listen --forward-to $SERVICE_URL/api/webhook/stripe

# In another terminal, trigger test event
stripe trigger customer.subscription.created

# Check Cloud Run logs
gcloud run services logs tail svg2ooxml-export --region=europe-west1
```

**Test Payment Flow**:
1. Click "Upgrade to Pro" in plugin ✅
2. Use test card: 4242 4242 4242 4242 ✅
3. Complete checkout ✅
4. Check webhook delivered (Stripe dashboard) ✅
5. Verify subscription status shows "Pro" ✅
6. Make unlimited exports ✅

---

## Verification Checklist

### Before Deployment
- [ ] GitHub Actions setup complete
- [ ] Firebase token added to GitHub Secrets
- [ ] Workload Identity Federation configured
- [ ] Stripe products created
- [ ] Stripe webhook configured
- [ ] Environment variables set

### After Deployment
- [ ] GitHub Actions workflow completed successfully
- [ ] Firebase Hosting pages accessible
- [ ] Firestore rules deployed
- [ ] Firestore indexes building/enabled
- [ ] Cloud Run service healthy (200 response)
- [ ] Subscription status endpoint working
- [ ] Checkout endpoint working
- [ ] Webhook endpoint receiving events

### End-to-End Testing
- [ ] User can sign in
- [ ] Subscription status shows correctly
- [ ] Free tier quota enforced (5/month)
- [ ] Upgrade flow works
- [ ] Payment completes successfully
- [ ] Webhook processes subscription
- [ ] Pro tier shows unlimited exports
- [ ] Customer portal accessible

---

## Troubleshooting

### GitHub Actions fails

**Check**:
1. GitHub Secrets are set correctly
2. Workload Identity Federation is configured
3. Service account has required permissions

**Fix**:
```bash
# Re-run setup script
./scripts/setup-github-deployment.sh
```

### Cloud Run deployment fails

**Check**:
1. `cloudbuild.yaml` exists
2. `Dockerfile` is valid
3. All dependencies in `requirements.txt`

**Fix**:
```bash
# View build logs
gcloud builds list --region=europe-west1 --limit=1
gcloud builds log BUILD_ID --region=europe-west1
```

### Health check fails

**Check**:
1. Cloud Run logs for startup errors
2. Environment variables are set
3. Port configuration (should be 8080)

**Fix**:
```bash
# Check logs
gcloud run services logs tail svg2ooxml-export --region=europe-west1

# Check environment variables
gcloud run services describe svg2ooxml-export \
  --region=europe-west1 \
  --format='value(spec.template.spec.containers[0].env)'
```

### Webhook not receiving events

**Check**:
1. Webhook URL is correct
2. Webhook secret matches environment variable
3. Events are selected in Stripe dashboard

**Fix**:
```bash
# Test with Stripe CLI
stripe listen --forward-to $SERVICE_URL/api/webhook/stripe
stripe trigger customer.subscription.created

# Check Cloud Run logs
gcloud run services logs tail svg2ooxml-export \
  --region=europe-west1 | grep webhook
```

---

## Rollback Plan

If something goes wrong:

### Rollback Code
```bash
# Revert last commit
git revert HEAD

# Push to trigger redeployment
git push origin main
```

### Rollback Cloud Run
```bash
# List revisions
gcloud run revisions list \
  --service=svg2ooxml-export \
  --region=europe-west1

# Rollback to previous revision
gcloud run services update-traffic svg2ooxml-export \
  --region=europe-west1 \
  --to-revisions=PREVIOUS_REVISION=100
```

### Rollback Firestore Rules
```bash
# Restore previous rules from git history
git show HEAD~1:firestore.rules > firestore.rules

# Deploy
firebase deploy --only firestore:rules --project powerful-layout-467812-p1
```

---

## Post-Deployment

### Monitor (First 24 Hours)

```bash
# Stream logs
gcloud run services logs tail svg2ooxml-export --region=europe-west1

# Watch for:
# - Subscription status requests
# - Export requests
# - Quota enforcement
# - Webhook events
# - Any errors
```

### Check Stripe Dashboard

- Webhooks: https://dashboard.stripe.com/test/webhooks
- Subscriptions: https://dashboard.stripe.com/test/subscriptions
- Customers: https://dashboard.stripe.com/test/customers

### Check Firestore

- Console: https://console.firebase.google.com/project/powerful-layout-467812-p1/firestore
- Verify data is being written correctly
- Check index status (should be "Enabled")

---

## Going Live (Production)

Once testing is complete:

### 1. Switch Stripe to Live Mode

1. Go to https://dashboard.stripe.com (live mode)
2. Create products (same as test mode)
3. Configure webhook (same URL, live mode)
4. Get live API keys

### 2. Update Environment Variables

```bash
gcloud run services update svg2ooxml-export \
  --region=europe-west1 \
  --set-env-vars="
ENVIRONMENT=production,
STRIPE_SECRET_KEY=sk_live_YOUR_KEY,
STRIPE_WEBHOOK_SECRET=whsec_YOUR_LIVE_SECRET,
STRIPE_PRICE_ID_PRO=price_YOUR_LIVE_PRO_ID,
STRIPE_PRICE_ID_ENTERPRISE=price_YOUR_LIVE_ENT_ID
"
```

### 3. Test with Real Payment

1. Use real credit card (small amount)
2. Verify full flow works
3. Cancel subscription
4. Verify cancellation works

### 4. Monitor for 48 Hours

Watch for any issues before announcing launch.

---

## Success Metrics

### Technical Metrics (Week 1)
- [ ] Zero webhook failures
- [ ] Zero authentication errors
- [ ] Zero quota enforcement bugs
- [ ] API response time < 200ms P95
- [ ] All Firestore indexes enabled

### Business Metrics (Month 1)
- [ ] Free → Pro conversion rate
- [ ] Average exports per user
- [ ] Quota exceeded events
- [ ] Churn rate
- [ ] Monthly recurring revenue

---

## Quick Reference

### Useful Commands

```bash
# Deploy manually (if needed)
gh workflow run deploy-cloud-run.yml
gh workflow run deploy-firebase.yml

# View deployments
gh run list

# View logs
gcloud run services logs tail svg2ooxml-export --region=europe-west1

# Check service
gcloud run services describe svg2ooxml-export --region=europe-west1

# Test Stripe webhooks
stripe listen --forward-to $SERVICE_URL/api/webhook/stripe
stripe trigger customer.subscription.created
```

### Important URLs

- **GitHub Actions**: https://github.com/YOUR_USERNAME/svg2ooxml/actions
- **Cloud Run Console**: https://console.cloud.google.com/run?project=powerful-layout-467812-p1
- **Firebase Console**: https://console.firebase.google.com/project/powerful-layout-467812-p1
- **Stripe Dashboard**: https://dashboard.stripe.com
- **Service URL**: https://svg2ooxml-export-sghya3t5ya-ew.a.run.app

---

## Timeline Summary

| Task | Time | Status |
|------|------|--------|
| Setup GitHub Actions | 30 min | ⏳ |
| Create Stripe products | 15 min | ⏳ |
| Configure webhook | 5 min | ⏳ |
| Set environment variables | 5 min | ⏳ |
| Commit and push | 5 min | ⏳ |
| Wait for deployment | 10 min | ⏳ |
| Test end-to-end | 10 min | ⏳ |
| **Total** | **~1 hour** | |

---

## Ready? Let's Go! 🚀

1. **Run**: `./scripts/setup-github-deployment.sh`
2. **Run**: `./scripts/stripe-setup.sh`
3. **Commit and push** to `main`
4. **Watch** GitHub Actions deploy
5. **Test** end-to-end flow
6. **Launch!** 🎉

---

**Need Help?**
- Setup Guide: `docs/GITHUB_DEPLOYMENT_SETUP.md`
- Deployment Checklist: `docs/FINAL_DEPLOYMENT_CHECKLIST.md`
- Stripe Setup: `docs/STRIPE_CLI_GUIDE.md`
- Requirements Review: `docs/REQUIREMENTS_AND_TESTS_REVIEW.md`

**Everything is ready. Time to deploy!** ✨
