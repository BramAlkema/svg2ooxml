# Deployment Guide - Stripe Payment Integration

## Prerequisites

- ✅ GCP Project: `powerful-layout-467812-p1`
- ✅ Firebase Project configured
- ✅ Cloud Run service deployed
- ⏳ Stripe account (test or live)

## Step 1: Deploy Firestore Rules & Indexes

```bash
# Deploy Firestore security rules
firebase deploy --only firestore:rules --project powerful-layout-467812-p1

# Deploy Firestore indexes (this can take 5-10 minutes)
firebase deploy --only firestore:indexes --project powerful-layout-467812-p1

# Verify deployment
echo "Check Firestore console:"
echo "https://console.firebase.google.com/project/powerful-layout-467812-p1/firestore"
```

**What this does**:
- Deploys security rules from `firestore.rules`
- Creates composite indexes for optimized queries
- Ensures only authenticated users can read their data
- Backend writes via Admin SDK (no client writes)

## Step 2: Set Up Stripe

### 2.1 Create Stripe Account
```bash
# Visit https://dashboard.stripe.com/register
# Or use existing account: https://dashboard.stripe.com
```

### 2.2 Create Products & Prices

**In Stripe Dashboard**:

1. **Create Pro Product**:
   - Go to Products → Add Product
   - Name: "svg2ooxml Pro"
   - Description: "Unlimited exports to Google Slides"
   - Pricing: $9.00/month (recurring)
   - Save and copy **Price ID** (starts with `price_`)

2. **Create Enterprise Product** (optional):
   - Name: "svg2ooxml Enterprise"
   - Description: "Unlimited exports + API access + priority support"
   - Pricing: $49.00/month (recurring)
   - Save and copy **Price ID**

### 2.3 Configure Webhook

1. Go to **Developers** → **Webhooks**
2. Click **Add endpoint**
3. **Endpoint URL**:
   ```
   https://svg2ooxml-export-sghya3t5ya-ew.a.run.app/api/webhook/stripe
   ```
4. **Events to send**:
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
5. Click **Add endpoint**
6. Copy **Signing secret** (starts with `whsec_`)

### 2.4 Enable Customer Portal

1. Go to **Settings** → **Customer portal**
2. Click **Activate test link** (for test mode)
3. Configure:
   - ✅ Allow customers to update payment methods
   - ✅ Allow customers to cancel subscriptions
   - ✅ Allow customers to view invoices
4. Save

### 2.5 Get API Keys

1. Go to **Developers** → **API keys**
2. Copy:
   - **Publishable key**: `pk_test_...` or `pk_live_...`
   - **Secret key**: `sk_test_...` or `sk_live_...`

## Step 3: Configure Environment Variables

### 3.1 Create .env File (for local testing)

```bash
cat > .env <<EOF
# Firebase / GCP
GCP_PROJECT=powerful-layout-467812-p1
GOOGLE_CLOUD_PROJECT=powerful-layout-467812-p1
ENVIRONMENT=development

# Stripe (TEST MODE)
STRIPE_SECRET_KEY=sk_test_YOUR_KEY_HERE
STRIPE_PUBLISHABLE_KEY=pk_test_YOUR_KEY_HERE
STRIPE_WEBHOOK_SECRET=whsec_YOUR_SECRET_HERE
STRIPE_PRICE_ID_PRO=price_YOUR_PRO_PRICE_ID
STRIPE_PRICE_ID_ENTERPRISE=price_YOUR_ENTERPRISE_PRICE_ID

# Rate Limiting
SVG2OOXML_RATE_LIMIT=60
SVG2OOXML_RATE_WINDOW=60
EOF
```

### 3.2 Deploy to Cloud Run

```bash
# Set environment variables
gcloud run services update svg2ooxml-export \
  --region=europe-west1 \
  --project=powerful-layout-467812-p1 \
  --set-env-vars="
ENVIRONMENT=production,
STRIPE_SECRET_KEY=sk_test_YOUR_KEY_HERE,
STRIPE_WEBHOOK_SECRET=whsec_YOUR_SECRET_HERE,
STRIPE_PRICE_ID_PRO=price_YOUR_PRO_PRICE_ID,
STRIPE_PRICE_ID_ENTERPRISE=price_YOUR_ENTERPRISE_PRICE_ID
"

# Verify environment variables
gcloud run services describe svg2ooxml-export \
  --region=europe-west1 \
  --project=powerful-layout-467812-p1 \
  --format="value(spec.template.spec.containers[0].env)"
```

## Step 4: Deploy Updated Code

### 4.1 Build and Deploy

```bash
# Ensure all dependencies are in requirements.txt
grep -q "stripe>=8.0.0" requirements.txt && echo "✅ Stripe SDK present" || echo "❌ Missing Stripe SDK"

# Build and deploy via Cloud Build
gcloud builds submit --config cloudbuild.yaml \
  --project=powerful-layout-467812-p1 \
  --region=europe-west1

# Or trigger via GitHub Actions (if configured)
git push origin main
```

### 4.2 Verify Deployment

```bash
# Check service is running
gcloud run services describe svg2ooxml-export \
  --region=europe-west1 \
  --project=powerful-layout-467812-p1 \
  --format="value(status.url)"

# Test health endpoint
SERVICE_URL=$(gcloud run services describe svg2ooxml-export \
  --region=europe-west1 \
  --project=powerful-layout-467812-p1 \
  --format="value(status.url)")

curl "$SERVICE_URL/health"
# Should return: {"status":"healthy"}
```

## Step 5: Test the Integration

### 5.1 Test Subscription Status (Unauthenticated)

```bash
# This should fail with 401 Unauthorized
curl -X GET "$SERVICE_URL/api/v1/subscription/status"
```

### 5.2 Test with Firebase Auth Token

```bash
# Get a Firebase ID token (from browser or plugin)
# Then test:
curl -X GET "$SERVICE_URL/api/v1/subscription/status" \
  -H "Authorization: Bearer YOUR_FIREBASE_ID_TOKEN"

# Should return:
# {
#   "tier": "free",
#   "status": "none",
#   "usage": {
#     "exports_this_month": 0,
#     "limit": 5,
#     "unlimited": false
#   },
#   "subscription": null
# }
```

### 5.3 Test Webhook Endpoint

```bash
# Use Stripe CLI to forward webhooks (for local testing)
stripe listen --forward-to "$SERVICE_URL/api/webhook/stripe"

# Or test webhook delivery in Stripe Dashboard:
# Developers → Webhooks → Your endpoint → Send test webhook
```

### 5.4 Test Export with Quota

```bash
# Make 5 exports (free tier limit)
for i in {1..5}; do
  echo "Export $i..."
  curl -X POST "$SERVICE_URL/api/v1/export" \
    -H "Authorization: Bearer YOUR_FIREBASE_ID_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "frames": [{
        "name": "Test",
        "svg_content": "<svg></svg>",
        "width": 100,
        "height": 100
      }],
      "output_format": "pptx"
    }'
  sleep 1
done

# 6th export should fail with 402 Payment Required
curl -X POST "$SERVICE_URL/api/v1/export" \
  -H "Authorization: Bearer YOUR_FIREBASE_ID_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "frames": [{
      "name": "Test",
      "svg_content": "<svg></svg>",
      "width": 100,
      "height": 100
    }],
    "output_format": "pptx"
  }'

# Should return:
# {
#   "detail": {
#     "error": "quota_exceeded",
#     "message": "You've reached your monthly limit of 5 exports...",
#     "usage": {"current": 5, "limit": 5}
#   }
# }
```

## Step 6: Monitor & Verify

### 6.1 Check Firestore Data

```bash
# View collections in Firebase console
echo "https://console.firebase.google.com/project/powerful-layout-467812-p1/firestore/data"
```

**Should see**:
- `/users/{uid}` - User records
- `/subscriptions/{sub_id}` - Subscription records (after first payment)
- `/usage/{uid_month}` - Usage tracking
- `/webhook_events/{event_id}` - Processed webhooks

### 6.2 Check Cloud Run Logs

```bash
# Stream logs
gcloud run services logs tail svg2ooxml-export \
  --region=europe-west1 \
  --project=powerful-layout-467812-p1

# Search for specific events
gcloud logging read "resource.type=cloud_run_revision \
  AND resource.labels.service_name=svg2ooxml-export \
  AND textPayload=~'subscription'" \
  --limit=50 \
  --project=powerful-layout-467812-p1
```

### 6.3 Monitor Stripe Dashboard

- **Payments**: https://dashboard.stripe.com/test/payments
- **Subscriptions**: https://dashboard.stripe.com/test/subscriptions
- **Webhooks**: https://dashboard.stripe.com/test/webhooks

## Step 7: Go Live (Production)

### 7.1 Switch to Live Mode

1. In Stripe Dashboard, toggle from **Test** to **Live** mode
2. Repeat Step 2 (create products, configure webhook)
3. Get live API keys

### 7.2 Update Environment Variables

```bash
gcloud run services update svg2ooxml-export \
  --region=europe-west1 \
  --project=powerful-layout-467812-p1 \
  --set-env-vars="
STRIPE_SECRET_KEY=sk_live_YOUR_KEY_HERE,
STRIPE_WEBHOOK_SECRET=whsec_YOUR_LIVE_SECRET_HERE,
STRIPE_PRICE_ID_PRO=price_YOUR_LIVE_PRO_PRICE_ID,
STRIPE_PRICE_ID_ENTERPRISE=price_YOUR_LIVE_ENTERPRISE_PRICE_ID
"
```

### 7.3 Verify Live Webhook

```bash
# Send test webhook from Stripe Dashboard (live mode)
# Check logs for successful processing
```

## Rollback Procedure

If something goes wrong:

```bash
# Rollback to previous Cloud Run revision
gcloud run services update-traffic svg2ooxml-export \
  --region=europe-west1 \
  --project=powerful-layout-467812-p1 \
  --to-revisions=PREVIOUS_REVISION=100

# Or rollback Firestore rules
firebase deploy --only firestore:rules --project powerful-layout-467812-p1
```

## Troubleshooting

### Issue: Webhook signature verification fails

**Solution**:
```bash
# Verify webhook secret is correct
gcloud run services describe svg2ooxml-export \
  --region=europe-west1 \
  --format="value(spec.template.spec.containers[0].env)" | grep STRIPE_WEBHOOK

# Test webhook delivery in Stripe Dashboard
```

### Issue: Firestore permission denied

**Solution**:
```bash
# Redeploy Firestore rules
firebase deploy --only firestore:rules --project powerful-layout-467812-p1

# Verify rules are active
firebase firestore:indexes --project powerful-layout-467812-p1
```

### Issue: Rate limit errors

**Solution**:
```bash
# Increase rate limit
gcloud run services update svg2ooxml-export \
  --region=europe-west1 \
  --set-env-vars="SVG2OOXML_RATE_LIMIT=120"
```

### Issue: Composite index not found

**Solution**:
```bash
# Indexes can take 5-10 minutes to build
# Check status:
firebase firestore:indexes --project powerful-layout-467812-p1

# Rebuild if needed:
firebase deploy --only firestore:indexes --project powerful-layout-467812-p1
```

## Performance Benchmarks

After optimization:

- Subscription check: ~100ms → ~50ms (parallel queries ✅)
- Export with quota check: ~300ms → ~150ms
- Webhook processing: ~200ms with idempotency ✅
- Rate limit: 60 requests/minute per IP ✅

## Security Checklist

- [x] Firestore rules deployed (backend-only writes)
- [x] Webhook signature verification
- [x] Idempotency for webhook replays
- [x] Rate limiting on all endpoints (except webhooks)
- [x] CORS restricted to Figma origins
- [x] Firebase Auth on all API endpoints
- [x] Composite indexes for optimized queries
- [x] Environment-specific CORS (dev vs prod)

## Cost Monitoring

```bash
# Check Firestore usage
echo "https://console.firebase.google.com/project/powerful-layout-467812-p1/usage"

# Check Cloud Run usage
gcloud run services describe svg2ooxml-export \
  --region=europe-west1 \
  --format="value(status.traffic)"
```

## Next Steps

1. Update Figma plugin UI for subscription management
2. Add monitoring alerts (Cloud Monitoring)
3. Set up revenue tracking (Stripe Dashboard)
4. Create user documentation
5. Announce launch! 🚀
