# Final Deployment Checklist - svg2ooxml Payment Integration

## 🎯 Overview

This checklist covers all remaining tasks to deploy the complete payment-enabled Figma plugin to production.

## ✅ Completed Work

### Backend (Cloud Run) - 100% Complete
- [x] Firebase Authentication integration
- [x] OAuth flow with refresh tokens (indefinite sessions)
- [x] Stripe payment service layer
- [x] Subscription repository (Firestore)
- [x] Usage tracking with atomic counters
- [x] Webhook handlers with idempotency
- [x] Quota enforcement (5/month free tier)
- [x] Security hardening (Firestore rules, CORS, rate limiting)
- [x] Performance optimization (parallel queries, composite indexes)
- [x] API endpoints: `/subscription/status`, `/subscription/checkout`, `/subscription/portal`

### Plugin UI - 100% Complete
- [x] Subscription status display
- [x] Usage bar with color coding
- [x] Upgrade to Pro button
- [x] Manage Subscription button
- [x] Quota exceeded error handling
- [x] Payment success/cancel pages
- [x] Token auto-refresh integration

### Documentation - 100% Complete
- [x] Firestore schema documentation
- [x] API endpoint documentation
- [x] Deployment guide
- [x] Speed & security improvements summary
- [x] Plugin UI implementation guide
- [x] Session persistence documentation

## 📋 Remaining Tasks

### 1. Firebase Hosting Deployment

Deploy the new payment pages and plugin UI:

```bash
# Deploy to Firebase Hosting
firebase deploy --only hosting --project powerful-layout-467812-p1

# Verify deployment
echo "Check hosting: https://powerful-layout-467812-p1.web.app"
```

**Verification**:
- [ ] Visit `https://powerful-layout-467812-p1.web.app/auth.html`
- [ ] Visit `https://powerful-layout-467812-p1.web.app/payment-success.html`
- [ ] Visit `https://powerful-layout-467812-p1.web.app/payment-cancel.html`
- [ ] All pages load correctly

### 2. Firestore Rules & Indexes Deployment

Deploy security rules and composite indexes:

```bash
# Deploy Firestore rules
firebase deploy --only firestore:rules --project powerful-layout-467812-p1

# Deploy Firestore indexes (takes 5-10 minutes to build)
firebase deploy --only firestore:indexes --project powerful-layout-467812-p1

# Verify in Firebase Console
echo "Check Firestore: https://console.firebase.google.com/project/powerful-layout-467812-p1/firestore"
```

**Verification**:
- [ ] Rules deployed successfully
- [ ] Indexes show "Building" or "Enabled"
- [ ] Wait for indexes to complete (check status every few minutes)
- [ ] All indexes show green "Enabled" status

### 3. Stripe Dashboard Setup (Test Mode)

#### 3.1 Create Products

**Create Pro Product**:
1. Go to https://dashboard.stripe.com/test/products
2. Click "Add product"
3. Fill in:
   - **Name**: `svg2ooxml Pro`
   - **Description**: `Unlimited exports to Google Slides`
   - **Pricing model**: `Recurring`
   - **Price**: `$9.00 USD`
   - **Billing period**: `Monthly`
4. Click "Save product"
5. **Copy the Price ID** (starts with `price_`) → Save for later

**Create Enterprise Product** (optional):
1. Click "Add product"
2. Fill in:
   - **Name**: `svg2ooxml Enterprise`
   - **Description**: `Unlimited exports + API access + priority support`
   - **Pricing model**: `Recurring`
   - **Price**: `$49.00 USD`
   - **Billing period**: `Monthly`
3. Click "Save product"
4. **Copy the Price ID** → Save for later

#### 3.2 Configure Webhook

1. Go to https://dashboard.stripe.com/test/webhooks
2. Click "Add endpoint"
3. Fill in:
   - **Endpoint URL**: `https://svg2ooxml-export-sghya3t5ya-ew.a.run.app/api/webhook/stripe`
   - **Description**: `svg2ooxml subscription webhooks`
4. Click "Select events"
5. Select these events:
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
6. Click "Add events"
7. Click "Add endpoint"
8. **Copy the Signing Secret** (starts with `whsec_`) → Save for later

#### 3.3 Enable Customer Portal

1. Go to https://dashboard.stripe.com/test/settings/billing/portal
2. Click "Activate test link"
3. Configure settings:
   - [x] Allow customers to update payment methods
   - [x] Allow customers to cancel subscriptions
   - [x] Allow customers to view invoices
   - [x] Allow customers to update billing information
4. **Save changes**

**Verification**:
- [ ] Pro product created with price ID
- [ ] Enterprise product created (optional)
- [ ] Webhook endpoint configured with signing secret
- [ ] Customer portal activated
- [ ] Test portal link works

### 4. Cloud Run Environment Variables

Set Stripe configuration on Cloud Run:

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

**Replace placeholders**:
- `sk_test_YOUR_KEY_HERE` → Your Stripe test secret key
- `whsec_YOUR_SECRET_HERE` → Your webhook signing secret
- `price_YOUR_PRO_PRICE_ID` → Pro product price ID
- `price_YOUR_ENTERPRISE_PRICE_ID` → Enterprise product price ID (or same as Pro if skipped)

**Verification**:
- [ ] All environment variables set correctly
- [ ] No syntax errors in variable names
- [ ] Values match Stripe dashboard

### 5. Deploy Updated Cloud Run Service

Rebuild and deploy with all changes:

```bash
# Ensure Stripe SDK is in requirements.txt
grep "stripe" requirements.txt

# Build and deploy via Cloud Build
gcloud builds submit --config cloudbuild.yaml \
  --project=powerful-layout-467812-p1 \
  --region=europe-west1

# Check deployment status
gcloud run services describe svg2ooxml-export \
  --region=europe-west1 \
  --project=powerful-layout-467812-p1 \
  --format="value(status.url)"
```

**Verification**:
- [ ] Build completes successfully
- [ ] New revision deployed
- [ ] Service URL returns 200 OK
- [ ] Health check passes: `curl https://svg2ooxml-export-sghya3t5ya-ew.a.run.app/health`

### 6. End-to-End Testing

#### 6.1 Test Subscription Status (Unauthenticated)

```bash
SERVICE_URL="https://svg2ooxml-export-sghya3t5ya-ew.a.run.app"

# Should return 401 Unauthorized
curl -X GET "$SERVICE_URL/api/v1/subscription/status"
```

**Expected**: `{"detail": "Missing or invalid authentication token"}`

#### 6.2 Test with Firebase Auth Token

1. Open Figma plugin
2. Sign in with Google
3. Open browser console
4. Copy `currentToken` value
5. Run:

```bash
TOKEN="YOUR_FIREBASE_ID_TOKEN"

# Test subscription status
curl -X GET "$SERVICE_URL/api/v1/subscription/status" \
  -H "Authorization: Bearer $TOKEN"
```

**Expected** (for new user):
```json
{
  "tier": "free",
  "status": "none",
  "usage": {
    "exports_this_month": 0,
    "limit": 5,
    "unlimited": false
  },
  "subscription": null
}
```

#### 6.3 Test Quota Enforcement

Make 5 exports from Figma plugin, then attempt 6th:

**Expected**:
- Exports 1-5: Success ✅
- Export 6: `402 Payment Required` with quota exceeded error ❌
- Plugin shows upgrade prompt

#### 6.4 Test Webhook Delivery

Use Stripe CLI to forward test webhooks:

```bash
# Install Stripe CLI if needed
brew install stripe/stripe-cli/stripe

# Forward webhooks to Cloud Run
stripe listen --forward-to "$SERVICE_URL/api/webhook/stripe"

# In another terminal, trigger test webhook
stripe trigger customer.subscription.created
```

**Expected**:
- Webhook received by Cloud Run
- Event processed successfully
- Check logs: `gcloud run services logs tail svg2ooxml-export --region=europe-west1`
- Firestore `webhook_events` collection updated

#### 6.5 Test Upgrade Flow

1. Open Figma plugin
2. Sign in
3. Click "⚡ Upgrade to Pro - $9/month"
4. Use Stripe test card: `4242 4242 4242 4242`
5. Complete checkout
6. Verify:
   - Redirected to payment-success.html
   - Webhook fires and updates Firestore
   - Reopen plugin → Shows "Pro" badge with unlimited exports

**Stripe Test Cards**:
- **Success**: `4242 4242 4242 4242`
- **Declined**: `4000 0000 0000 0002`
- **Requires Auth**: `4000 0025 0000 3155`

#### 6.6 Test Customer Portal

1. As Pro user, click "Manage Subscription"
2. Verify portal opens in new window
3. Try:
   - View invoices
   - Update payment method (test card)
   - Cancel subscription
4. Verify changes sync via webhooks

**Verification Checklist**:
- [ ] Unauthenticated requests rejected
- [ ] Subscription status fetched correctly
- [ ] Quota enforcement works (5 exports max for free)
- [ ] Webhook delivery confirmed
- [ ] Upgrade flow completes successfully
- [ ] Pro badge shows after upgrade
- [ ] Unlimited exports work
- [ ] Customer portal accessible
- [ ] Cancellation syncs correctly

### 7. Monitor Cloud Run Logs

Stream logs during testing:

```bash
# Stream all logs
gcloud run services logs tail svg2ooxml-export \
  --region=europe-west1 \
  --project=powerful-layout-467812-p1

# Filter for subscription-related logs
gcloud logging read \
  "resource.type=cloud_run_revision \
   AND resource.labels.service_name=svg2ooxml-export \
   AND textPayload=~'subscription'" \
  --limit=50 \
  --project=powerful-layout-467812-p1
```

**Look for**:
- Successful subscription fetches
- Quota enforcement logs
- Webhook processing events
- Any errors or warnings

### 8. Verify Firestore Data

Check Firestore console: https://console.firebase.google.com/project/powerful-layout-467812-p1/firestore/data

**Collections to verify**:

1. **`/users/{uid}`**:
   - Created on first sign-in
   - Contains `email`, `stripeCustomerId`

2. **`/subscriptions/{sub_id}`**:
   - Created after first payment
   - Contains `userId`, `status`, `tier`, `stripeSubscriptionId`

3. **`/usage/{uid_month}`**:
   - Created on first export
   - Contains `exportCount`, `monthYear`, `userId`

4. **`/webhook_events/{event_id}`**:
   - Created for each processed webhook
   - Contains `event_id`, `event_type`, `processed_at`, `expires_at`

**Verification**:
- [ ] All collections created automatically
- [ ] User document has Stripe customer ID
- [ ] Subscription document created after payment
- [ ] Usage increments on export
- [ ] Webhook events stored with 24h expiry

### 9. Performance Validation

Run performance tests:

```bash
# Test subscription status endpoint (should be ~100ms)
time curl -X GET "$SERVICE_URL/api/v1/subscription/status" \
  -H "Authorization: Bearer $TOKEN"

# Test export endpoint (should complete in <3 minutes)
time curl -X POST "$SERVICE_URL/api/v1/export" \
  -H "Authorization: Bearer $TOKEN" \
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
```

**Expected Performance**:
- Subscription status: < 200ms
- Export (PPTX): < 30s
- Export (Slides): < 180s

### 10. Security Audit

Run security checks:

```bash
# Verify Firestore rules are active
firebase firestore:security get --project powerful-layout-467812-p1

# Verify CORS configuration
curl -X OPTIONS "$SERVICE_URL/api/v1/export" \
  -H "Origin: https://www.figma.com" \
  -H "Access-Control-Request-Method: POST" \
  -v

# Test rate limiting (should be limited at 60 requests/minute)
for i in {1..65}; do
  curl -s "$SERVICE_URL/health" &
done
wait
```

**Expected**:
- Firestore rules deployed and active
- CORS allows only Figma origins
- Rate limiting kicks in at 61st request (429 status)

## 🚀 Go Live (Production Mode)

Once all testing passes, switch to live mode:

### Step 1: Switch Stripe to Live Mode

1. In Stripe Dashboard, toggle from **Test** to **Live**
2. Repeat product creation with live prices
3. Configure live webhook endpoint (same URL)
4. Enable live customer portal
5. Copy live API keys and webhook secret

### Step 2: Update Cloud Run with Live Keys

```bash
gcloud run services update svg2ooxml-export \
  --region=europe-west1 \
  --project=powerful-layout-467812-p1 \
  --set-env-vars="
ENVIRONMENT=production,
STRIPE_SECRET_KEY=sk_live_YOUR_LIVE_KEY,
STRIPE_WEBHOOK_SECRET=whsec_YOUR_LIVE_SECRET,
STRIPE_PRICE_ID_PRO=price_YOUR_LIVE_PRO_PRICE_ID,
STRIPE_PRICE_ID_ENTERPRISE=price_YOUR_LIVE_ENTERPRISE_PRICE_ID
"
```

### Step 3: Test with Real Payment

1. Use real credit card (not test card)
2. Complete one full payment cycle
3. Verify webhook delivery
4. Check live Stripe dashboard
5. Verify Firestore updates

### Step 4: Monitor for 24 Hours

- Watch Cloud Run logs for errors
- Monitor Stripe dashboard for payments
- Check webhook delivery success rate
- Respond to any user issues

## 📊 Success Metrics

After 1 week, check:

- [ ] Zero authentication errors
- [ ] Zero webhook failures
- [ ] Zero quota enforcement errors
- [ ] >0 successful payments
- [ ] Firestore usage within free tier
- [ ] Cloud Run latency < 200ms P95

## 🆘 Rollback Plan

If critical issues occur:

```bash
# Rollback Cloud Run to previous revision
gcloud run services update-traffic svg2ooxml-export \
  --region=europe-west1 \
  --to-revisions=PREVIOUS_REVISION=100

# Rollback Firestore rules
firebase deploy --only firestore:rules --project powerful-layout-467812-p1
```

## 📞 Support Setup

### Create Support Email

Set up `support@svg2ooxml.com` (or use existing domain) with auto-responder:

```
Thank you for contacting svg2ooxml support!

We've received your message and will respond within 24 hours.

Common issues:
- Quota exceeded? Upgrade to Pro for unlimited exports: [link]
- Payment issues? Manage your subscription: [link]
- Technical support: Check our docs: [link]

Best regards,
svg2ooxml Team
```

### Create FAQ Page

Add to Firebase Hosting (`public/faq.html`):

Topics:
- How do I upgrade?
- How do I cancel?
- What happens when I cancel?
- How do refunds work?
- What are the usage limits?

## 🎉 Launch Announcement

Once live and stable:

1. Update Figma plugin listing with pricing info
2. Announce on social media
3. Email existing users (if applicable)
4. Monitor for feedback

## ✅ Final Checklist

Before marking as "complete":

- [ ] Firebase Hosting deployed (payment pages)
- [ ] Firestore rules deployed
- [ ] Firestore indexes built and enabled
- [ ] Stripe products created (test mode)
- [ ] Stripe webhook configured
- [ ] Stripe customer portal enabled
- [ ] Cloud Run environment variables set
- [ ] Cloud Run service deployed
- [ ] End-to-end payment flow tested
- [ ] Quota enforcement tested
- [ ] Webhook delivery tested
- [ ] Customer portal tested
- [ ] Performance validated (<200ms)
- [ ] Security audit passed
- [ ] Logs monitored (no errors)
- [ ] Firestore data verified
- [ ] Test mode fully validated
- [ ] Support email configured
- [ ] Ready to switch to live mode

## 🏁 Status

**Current Status**: Ready for testing in test mode

**Next Action**: Execute checklist steps 1-10 to validate in test mode, then switch to live mode.

**Estimated Time to Production**: 2-4 hours (mostly waiting for index builds and testing)
