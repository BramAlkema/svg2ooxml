# Stripe Payment Integration - Implementation Status

## ✅ Completed (Backend)

### 1. Database Schema ✅
- **File**: `docs/firestore-schema.md`
- Firestore collections designed:
  - `/users` - User profiles with Stripe customer IDs
  - `/subscriptions` - Active and historical subscriptions
  - `/usage` - Monthly export usage tracking
- No SQL database needed - using existing Firestore

### 2. Dependencies ✅
- **File**: `requirements.txt`
- Added: `stripe>=8.0.0`

### 3. Stripe Service Layer ✅
- **File**: `src/svg2ooxml/api/services/stripe_service.py`
- Implements:
  - `create_customer()` - Create Stripe customers
  - `create_checkout_session()` - Start subscription purchase
  - `create_portal_session()` - Manage subscription
  - `get_subscription()` - Retrieve subscription details
  - `verify_webhook_signature()` - Verify Stripe webhooks
  - `cancel_subscription()` - Cancel subscriptions

### 4. Firestore Repository ✅
- **File**: `src/svg2ooxml/api/services/subscription_repository.py`
- Implements:
  - User CRUD operations
  - Subscription management
  - Usage tracking with atomic increments
  - Query by Stripe customer ID

### 5. API Models ✅
- **File**: `src/svg2ooxml/api/models/subscription.py`
- Pydantic models for:
  - `CheckoutRequest/Response`
  - `PortalResponse`
  - `SubscriptionStatusResponse`
  - `UsageInfo`
  - `SubscriptionInfo`

### 6. Subscription API Endpoints ✅
- **File**: `src/svg2ooxml/api/routes/subscription.py`
- Endpoints:
  - `GET /api/v1/subscription/status` - Check tier and usage
  - `POST /api/v1/subscription/checkout` - Start payment
  - `POST /api/v1/subscription/portal` - Manage subscription

### 7. Webhook Handler ✅
- **File**: `src/svg2ooxml/api/routes/webhooks.py`
- Handles Stripe events:
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
  - `invoice.payment_succeeded`
  - `invoice.payment_failed`

### 8. Usage Tracking & Quotas ✅
- **File**: `src/svg2ooxml/api/routes/export.py` (modified)
- Features:
  - Check subscription status before export
  - Enforce free tier limit (5 exports/month)
  - Increment usage counter atomically
  - Return 402 Payment Required when quota exceeded

### 9. Router Integration ✅
- **File**: `main.py` (modified)
- Added subscription and webhook routers to FastAPI app

---

## ⏳ In Progress (Frontend)

### 10. Plugin UI Updates 🔄
Need to add subscription management UI to Figma plugin:
- Subscription status display
- Usage counter ("3/5 exports this month")
- Upgrade button
- Manage subscription button

---

## 📋 Pending

### 11. Environment Variables Documentation ⏳
Need to document required environment variables:
```bash
# Stripe Configuration
STRIPE_SECRET_KEY=sk_test_xxx
STRIPE_PUBLISHABLE_KEY=pk_test_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
STRIPE_PRICE_ID_PRO=price_xxx
STRIPE_PRICE_ID_ENTERPRISE=price_xxx
```

### 12. Stripe Dashboard Setup ⏳
- Create products (Pro, Enterprise)
- Create prices (monthly/yearly)
- Configure webhook endpoint
- Enable customer portal
- Set up email templates

### 13. End-to-End Testing ⏳
- Test free tier (5 exports limit)
- Test quota exceeded error
- Test upgrade flow
- Test subscription management
- Test webhook processing

---

## API Endpoints Summary

### Subscription Management
```
GET  /api/v1/subscription/status  - Check subscription and usage
POST /api/v1/subscription/checkout - Create Stripe checkout session
POST /api/v1/subscription/portal   - Create customer portal session
```

### Webhooks
```
POST /api/webhook/stripe - Handle Stripe webhook events
```

### Export (Modified)
```
POST /api/v1/export - Create export job (now with usage tracking)
```

---

## Pricing Tiers

| Tier | Price | Exports | Features |
|------|-------|---------|----------|
| **Free** | $0 | 5/month | All features |
| **Pro** | $9/month | Unlimited | Priority processing |
| **Enterprise** | $49/month | Unlimited | API + Support |

---

## Next Steps

1. **Update Plugin UI** (Current task)
   - Add subscription section to `figma-plugin/ui.html`
   - Add subscription checking to `figma-plugin/ui.js`
   - Display usage counter and upgrade CTA

2. **Set Up Stripe**
   - Create Stripe account (test mode)
   - Create products and prices
   - Configure webhook endpoint
   - Get API keys

3. **Configure Environment**
   - Add Stripe keys to Cloud Run
   - Add Stripe keys to `.env` for local testing
   - Deploy updated code

4. **Test End-to-End**
   - Test free tier limit
   - Test upgrade flow
   - Test subscription portal
   - Verify webhook processing

5. **Production Launch**
   - Switch to live Stripe keys
   - Update pricing page
   - Announce feature

---

## Files Created/Modified

### Created
- `src/svg2ooxml/api/services/stripe_service.py`
- `src/svg2ooxml/api/services/subscription_repository.py`
- `src/svg2ooxml/api/models/subscription.py`
- `src/svg2ooxml/api/routes/subscription.py`
- `src/svg2ooxml/api/routes/webhooks.py`
- `docs/firestore-schema.md`
- `docs/specs/stripe-payment-integration.md`
- `docs/STRIPE_IMPLEMENTATION_STATUS.md`

### Modified
- `requirements.txt` - Added Stripe SDK
- `main.py` - Added subscription & webhook routers
- `src/svg2ooxml/api/routes/export.py` - Added usage tracking

### Pending
- `figma-plugin/ui.html` - Need subscription UI
- `figma-plugin/ui.js` - Need subscription logic
- `.env.example` - Need Stripe env vars
- `cloudbuild.yaml` - May need Stripe secrets

---

## Technical Decisions

### Why Firestore over PostgreSQL?
- ✅ Already integrated (Firebase Admin SDK installed)
- ✅ No connection management needed
- ✅ Auto-scaling
- ✅ Generous free tier
- ✅ Atomic counter increments
- ✅ No new infrastructure to provision

### Why $9/month for Pro?
- Competitive with similar plugins ($3-18/month range)
- Higher than simple plugins ($3-5/month)
- Lower than enterprise tools ($20+/month)
- Good value for unlimited exports

### Why 5 exports for free tier?
- Enough for evaluation (1 week of typical use)
- Low enough to encourage upgrades
- Similar to other freemium tools

---

## Cost Analysis

### Firestore Costs (free tier: 50K reads, 20K writes/day)

**100 users, 50 exports/day**:
- Reads: ~150/day (3 per export)
- Writes: ~50/day
- Cost: **$0/month** (within free tier)

**1,000 users, 500 exports/day**:
- Reads: ~1,500/day
- Writes: ~500/day
- Cost: **$0/month** (still within free tier)

**10,000 users, 5,000 exports/day**:
- Reads: ~15K/day
- Writes: ~5K/day
- Cost: **$0/month** (barely within free tier)

Even at scale, Firestore is essentially free for this use case.

### Stripe Costs
- 2.9% + $0.30 per transaction
- No monthly fees
- Customer portal included

**Revenue Example** (100 Pro subscribers):
- Gross: $900/month
- Stripe fees: ~$60/month (6.7%)
- Net: ~$840/month

---

## Security Considerations

✅ Implemented:
- Firebase Auth for user authentication
- Webhook signature verification
- Atomic usage increments (no race conditions)
- Firestore security rules (backend-only writes)

⚠️ TODO:
- Rate limiting on subscription endpoints
- Fraud detection (monitor unusual usage patterns)
- Token encryption for stored customer IDs

---

## Success Metrics to Track

- Free-to-paid conversion rate (target: 2-5%)
- Monthly recurring revenue (MRR)
- Churn rate (target: <5%)
- Average revenue per user (ARPU)
- Usage per tier
- Quota exceeded events (funnel metric)

---

## Documentation

- ✅ Technical spec: `docs/specs/stripe-payment-integration.md`
- ✅ Database schema: `docs/firestore-schema.md`
- ⏳ Environment variables: Need to create
- ⏳ Testing guide: Need to create
- ⏳ Deployment guide: Need to create
