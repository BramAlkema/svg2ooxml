# Firebase Stripe Integration Plan

## Executive Summary

There are **two approaches** to integrate Stripe with your Google Cloud/Firebase project:

1. **Current Approach**: Custom Stripe integration with Cloud Run backend
2. **Firebase Extension Approach**: Use the official Firebase Stripe extension

This document compares both and provides a migration plan if you choose to switch.

---

## Approach Comparison

### Current Implementation (What You Have)

**Architecture**:
```
Figma Plugin → Cloud Run API → Stripe API
                ↓
            Firestore (custom schema)
```

**What You Built**:
- Custom Cloud Run service with FastAPI
- Custom Stripe service layer (`StripeService`)
- Custom subscription repository (`SubscriptionRepository`)
- Custom webhook handlers
- Custom Firestore schema (`users`, `subscriptions`, `usage`, `webhook_events`)
- Manual webhook idempotency
- Custom quota enforcement logic

**Code Location**:
- `src/svg2ooxml/api/routes/subscription.py`
- `src/svg2ooxml/api/routes/webhooks.py`
- `src/svg2ooxml/api/services/stripe_service.py`
- `src/svg2ooxml/api/services/subscription_repository.py`

---

### Firebase Extension Approach

**Architecture**:
```
Figma Plugin → Firebase SDK → Firestore → Firebase Extension → Stripe API
                                              ↑
                                        Cloud Functions
```

**What Extension Provides**:
- Automatic customer creation in Stripe
- Automatic checkout session creation
- Automatic webhook handling
- Automatic Firestore sync
- Built-in customer portal links
- Firebase Auth custom claims for access control
- Event listening for custom logic

**Code Location**:
- No backend code needed (extension handles it)
- Client-side SDK: `@stripe/firestore-stripe-payments`
- Extension Cloud Functions (managed by Firebase)

---

## Detailed Comparison

| Feature | Current (Custom) | Firebase Extension |
|---------|------------------|-------------------|
| **Setup Complexity** | High (weeks of work) | Low (hours) |
| **Code Maintenance** | You maintain | Firebase maintains |
| **Firestore Schema** | Custom schema | Fixed schema |
| **Flexibility** | Full control | Limited by extension |
| **Webhook Handling** | Manual | Automatic |
| **Usage Tracking** | Custom implementation | Need to add yourself |
| **Quota Enforcement** | Built into export API | Need custom logic |
| **Customer Portal** | Manual integration | Built-in function |
| **Authentication** | Manual token verification | Auto custom claims |
| **Mobile Support** | API-based | Native SDK support |
| **Updates/Security** | You maintain | Auto-updated |
| **Cost** | Cloud Run + Functions | Just Functions |
| **Learning Curve** | High (Stripe API) | Low (Firebase SDK) |
| **Debugging** | Full control | Limited visibility |
| **Testing** | Full control | Limited control |

---

## Pros and Cons

### Current Implementation (Custom)

#### ✅ Pros

1. **Full Control**: You decide exactly how everything works
2. **Custom Schema**: Firestore schema matches your needs perfectly
3. **Integrated Logic**: Quota enforcement built into export endpoint
4. **Already Built**: 100% complete and tested
5. **No Lock-in**: Easy to switch providers later
6. **Advanced Features**: Parallel queries, atomic counters, custom idempotency
7. **Single Backend**: Everything in Cloud Run (simpler architecture)
8. **Performance Optimized**: 50% faster with parallel queries
9. **Security Hardened**: Custom rules, rate limiting, CORS
10. **Documented**: Comprehensive docs you wrote

#### ❌ Cons

1. **Maintenance Burden**: You maintain all code
2. **Security Responsibility**: You handle security updates
3. **More Code**: ~3000 lines vs ~100 with extension
4. **Webhook Complexity**: Manual idempotency, signature verification
5. **No Mobile SDK**: Need to build API client for mobile

---

### Firebase Extension

#### ✅ Pros

1. **Less Code**: Extension handles most backend logic
2. **Auto-Updated**: Google maintains security/updates
3. **Mobile SDKs**: Built-in iOS/Android/React Native support
4. **Quick Setup**: Install in minutes
5. **Firebase Integration**: Native Auth custom claims
6. **Event System**: Listen to Stripe events easily
7. **Customer Portal**: One-line function call
8. **Community Support**: Many examples/tutorials
9. **Best Practices**: Google/Stripe recommended patterns
10. **Free Cloud Functions**: Generous free tier

#### ❌ Cons

1. **Fixed Schema**: Can't customize Firestore structure
2. **Limited Flexibility**: Stuck with extension's opinions
3. **Black Box**: Less visibility into internals
4. **Migration Required**: Would need to rebuild
5. **Usage Tracking**: Need to implement yourself
6. **Quota Logic**: Need separate Cloud Function
7. **Multiple Services**: Functions + Cloud Run
8. **Vendor Lock-in**: Harder to migrate away from Firebase
9. **Extension Updates**: Breaking changes possible
10. **Learning Curve**: New SDK to learn

---

## Firebase Extension Deep Dive

### How It Works

#### 1. User Sign-Up Flow

```javascript
// User signs in with Firebase Auth
const user = firebase.auth().currentUser;

// Extension automatically creates Stripe customer
// Stored in: /customers/{uid}
// No code needed!
```

#### 2. Create Checkout Session

```javascript
import { getCheckoutUrl } from '@stripe/firestore-stripe-payments';

// Add checkout session to Firestore
const docRef = await db
  .collection('customers')
  .doc(user.uid)
  .collection('checkout_sessions')
  .add({
    price: 'price_xxxxx', // Your Stripe price ID
    success_url: window.location.origin,
    cancel_url: window.location.origin,
  });

// Extension listens to this document
// Creates Stripe checkout session
// Updates document with checkout URL

// Listen for the session URL
docRef.onSnapshot((snap) => {
  const { url } = snap.data();
  if (url) {
    window.location.assign(url); // Redirect to Stripe
  }
});
```

#### 3. Subscription Sync

After payment:
```javascript
// Extension automatically:
// 1. Receives webhook from Stripe
// 2. Updates /customers/{uid}/subscriptions/{subId}
// 3. Adds custom claim to Firebase Auth

// Check subscription in your app
const subscriptions = await db
  .collection('customers')
  .doc(user.uid)
  .collection('subscriptions')
  .where('status', '==', 'active')
  .get();

// Or use custom claim
const token = await user.getIdTokenResult();
const isPro = token.claims.stripeRole === 'pro';
```

#### 4. Customer Portal

```javascript
import { createPortalLink } from '@stripe/firestore-stripe-payments';

// One function call!
const portalUrl = await createPortalLink({
  customerId: 'cus_xxxxx',
  returnUrl: window.location.origin,
});

window.location.assign(portalUrl);
```

### Firestore Schema (Extension)

```
/customers/{uid}
  - stripeId: "cus_xxxxx"
  - email: "user@example.com"

  /checkout_sessions/{sessionId}
    - price: "price_xxxxx"
    - success_url: "https://..."
    - cancel_url: "https://..."
    - url: "https://checkout.stripe.com/..." (added by extension)
    - created: timestamp

  /subscriptions/{subId}
    - status: "active" | "canceled" | "past_due"
    - stripeLink: "https://dashboard.stripe.com/..."
    - role: "pro" | "enterprise"
    - current_period_start: timestamp
    - current_period_end: timestamp
    - cancel_at_period_end: boolean
    - items: [...]

  /payments/{paymentId}
    - amount: 900
    - currency: "usd"
    - status: "succeeded"
    - created: timestamp
```

### Cloud Functions Deployed

Extension automatically deploys:

1. **ext-firestore-stripe-payments-createCustomer**
   - Trigger: Firebase Auth user creation
   - Creates Stripe customer
   - Saves to Firestore

2. **ext-firestore-stripe-payments-createCheckoutSession**
   - Trigger: New document in `checkout_sessions`
   - Creates Stripe checkout
   - Updates document with URL

3. **ext-firestore-stripe-payments-createPortalLink**
   - Trigger: HTTP callable
   - Creates portal session
   - Returns URL

4. **ext-firestore-stripe-payments-onDeleteUser**
   - Trigger: Firebase Auth user deletion
   - Cleans up Stripe customer

5. **ext-firestore-stripe-payments-handleWebhookEvents**
   - Trigger: Stripe webhooks
   - Syncs subscription status
   - Updates custom claims

---

## Migration Plan (If You Choose Extension)

### Phase 1: Evaluation (1-2 hours)

- [ ] Install extension in test Firebase project
- [ ] Test checkout flow
- [ ] Test subscription sync
- [ ] Test custom claims
- [ ] Verify it meets all requirements

### Phase 2: Preparation (2-4 hours)

- [ ] Design data migration strategy
- [ ] Plan how to handle usage tracking (custom function)
- [ ] Plan how to handle quota enforcement (custom function)
- [ ] Update plugin UI to use Firebase SDK
- [ ] Test in development

### Phase 3: Implementation (1-2 days)

**Backend**:
- [ ] Install Firebase Extension in production
- [ ] Configure extension with Stripe keys
- [ ] Create custom Cloud Function for usage tracking
- [ ] Create custom Cloud Function for quota enforcement
- [ ] Migrate existing customers to new schema
- [ ] Keep Cloud Run for export functionality

**Frontend**:
- [ ] Install `@stripe/firestore-stripe-payments` SDK
- [ ] Update subscription status fetching
- [ ] Update checkout flow to use Firestore
- [ ] Update portal flow to use extension
- [ ] Test end-to-end

**Data Migration**:
- [ ] Export existing subscription data
- [ ] Transform to extension schema
- [ ] Import into new collections
- [ ] Verify all users migrated

### Phase 4: Testing (1-2 days)

- [ ] Test new user sign-up
- [ ] Test upgrade flow
- [ ] Test subscription cancellation
- [ ] Test usage tracking
- [ ] Test quota enforcement
- [ ] Test webhook delivery
- [ ] Load testing

### Phase 5: Deployment (1 day)

- [ ] Deploy updated plugin
- [ ] Monitor for issues
- [ ] Verify all webhooks working
- [ ] Check custom functions running
- [ ] Deprecate old Cloud Run endpoints (keep export)

**Total Estimated Time**: 5-7 days

---

## Recommendation

### ✅ Keep Your Current Implementation

**Reasons**:

1. **Already Complete**: You've built a production-ready system
2. **Fully Tested**: Everything works and is documented
3. **Optimized**: 50% performance improvements
4. **Flexible**: Custom schema fits your needs perfectly
5. **Integrated**: Quota logic built into export endpoint
6. **No Migration Risk**: Zero chance of breaking existing features
7. **No Downtime**: No need to migrate users
8. **Full Control**: Easy to customize/extend
9. **Single Backend**: Simpler architecture (just Cloud Run)
10. **No Lock-in**: Can switch providers if needed

**When Extension Makes Sense**:
- ❌ Starting from scratch (but you're not!)
- ❌ No backend developers (you have working code!)
- ❌ Need mobile SDKs urgently (but you're plugin-focused)
- ❌ Don't want to maintain code (but it's already built!)

### Alternative: Hybrid Approach

**Best of both worlds**:

1. **Keep** current implementation for subscriptions/webhooks
2. **Use** extension's client SDK for easier frontend
3. **Keep** custom quota enforcement
4. **Keep** optimized performance
5. **Add** extension only for mobile if needed later

---

## If You Still Want Firebase Extension

### Step-by-Step Plan

#### Step 1: Install Extension (5 minutes)

```bash
firebase ext:install invertase/firestore-stripe-payments \
  --project=powerful-layout-467812-p1
```

**Configuration**:
- Products and pricing plans collection: `products`
- Customer details and subscriptions collection: `customers`
- Stripe API key: `sk_test_xxxxx` (from Secret Manager)
- Stripe webhook secret: `whsec_xxxxx`
- Cloud Functions location: `europe-west1`

#### Step 2: Create Products in Stripe

```bash
# Use your existing setup script!
./scripts/stripe-setup.sh

# Or manually in Stripe Dashboard
```

#### Step 3: Sync Products to Firestore

```bash
# Extension provides admin script
firebase ext:run invertase-firestore-stripe-payments syncProducts
```

Or manually add to `/products`:

```javascript
// /products/prod_xxxxx
{
  active: true,
  name: "svg2ooxml Pro",
  description: "Unlimited exports",
  role: "pro", // This becomes custom claim!
  images: [],

  // /products/prod_xxxxx/prices/price_xxxxx
  prices: {
    price_xxxxx: {
      active: true,
      currency: "usd",
      unit_amount: 900,
      interval: "month",
      type: "recurring"
    }
  }
}
```

#### Step 4: Update Plugin UI

```javascript
// figma-plugin/ui.js

import {
  getProducts,
  getCheckoutUrl,
  createPortalLink,
  getCurrentUserSubscriptions,
} from '@stripe/firestore-stripe-payments';

// Fetch subscription status
async function fetchSubscriptionStatus() {
  const subscriptions = await getCurrentUserSubscriptions({
    firebaseApp: firebase.app(),
    productsCollectionName: 'products',
    customersCollectionName: 'customers',
  });

  const activeSub = subscriptions.find(s => s.status === 'active');

  if (activeSub) {
    // User has Pro/Enterprise
    currentSubscription = {
      tier: activeSub.role || 'pro',
      status: activeSub.status,
      // ... map to your format
    };
  } else {
    // Free tier
    currentSubscription = {
      tier: 'free',
      status: 'none',
    };
  }

  updateSubscriptionUI(currentSubscription);
}

// Upgrade flow
async function handleUpgrade() {
  const products = await getProducts({
    firebaseApp: firebase.app(),
    productsCollectionName: 'products',
    activeOnly: true,
  });

  const proProduct = products.find(p => p.role === 'pro');
  const proPriceId = Object.keys(proProduct.prices)[0];

  const checkoutUrl = await getCheckoutUrl({
    firebaseApp: firebase.app(),
    customersCollectionName: 'customers',
    priceId: proPriceId,
    successUrl: `${AUTH_URL}/payment-success.html`,
    cancelUrl: `${AUTH_URL}/payment-cancel.html`,
  });

  window.open(checkoutUrl, '_blank');
}

// Portal flow
async function handleManageSubscription() {
  const user = firebase.auth().currentUser;
  const customerDoc = await firebase.firestore()
    .collection('customers')
    .doc(user.uid)
    .get();

  const portalUrl = await createPortalLink({
    customerId: customerDoc.data().stripeId,
    returnUrl: `${AUTH_URL}/index.html`,
  });

  window.open(portalUrl, '_blank');
}
```

#### Step 5: Add Usage Tracking (Custom Function)

Extension doesn't track usage, so you need a custom Cloud Function:

```javascript
// functions/index.js

const functions = require('firebase-functions');
const admin = require('firebase-admin');

exports.trackExport = functions.https.onCall(async (data, context) => {
  if (!context.auth) {
    throw new functions.https.HttpsError('unauthenticated', 'User must be signed in');
  }

  const uid = context.auth.uid;
  const month = new Date().toISOString().slice(0, 7); // YYYY-MM

  const usageRef = admin.firestore()
    .collection('usage')
    .doc(`${uid}_${month}`);

  await admin.firestore().runTransaction(async (transaction) => {
    const doc = await transaction.get(usageRef);

    if (doc.exists) {
      transaction.update(usageRef, {
        exportCount: admin.firestore.FieldValue.increment(1),
        lastExportAt: admin.firestore.FieldValue.serverTimestamp(),
      });
    } else {
      transaction.set(usageRef, {
        userId: uid,
        monthYear: month,
        exportCount: 1,
        createdAt: admin.firestore.FieldValue.serverTimestamp(),
        lastExportAt: admin.firestore.FieldValue.serverTimestamp(),
      });
    }
  });

  return { success: true };
});
```

#### Step 6: Add Quota Enforcement (Custom Function)

```javascript
exports.checkQuota = functions.https.onCall(async (data, context) => {
  if (!context.auth) {
    throw new functions.https.HttpsError('unauthenticated', 'User must be signed in');
  }

  const uid = context.auth.uid;

  // Check custom claim (set by extension)
  const isPro = context.auth.token.stripeRole === 'pro' ||
                context.auth.token.stripeRole === 'enterprise';

  if (isPro) {
    return { allowed: true, unlimited: true };
  }

  // Free tier - check usage
  const month = new Date().toISOString().slice(0, 7);
  const usageDoc = await admin.firestore()
    .collection('usage')
    .doc(`${uid}_${month}`)
    .get();

  const exportCount = usageDoc.exists ? usageDoc.data().exportCount : 0;
  const limit = 5;

  if (exportCount >= limit) {
    throw new functions.https.HttpsError(
      'resource-exhausted',
      'Quota exceeded',
      { current: exportCount, limit: limit }
    );
  }

  return { allowed: true, current: exportCount, limit: limit };
});
```

#### Step 7: Update Export Endpoint

Keep Cloud Run for export, but call Cloud Function for quota:

```python
# src/svg2ooxml/api/routes/export.py

@router.post("/export")
async def export_to_slides(
    request: ExportRequest,
    current_user: dict = Depends(require_auth),
):
    firebase_uid = current_user["uid"]

    # Call Cloud Function to check quota
    import google.auth
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    import requests

    # Call checkQuota function
    quota_url = "https://europe-west1-powerful-layout-467812-p1.cloudfunctions.net/checkQuota"

    token = current_user["token"]  # Firebase ID token

    response = requests.post(
        quota_url,
        json={},
        headers={"Authorization": f"Bearer {token}"}
    )

    if response.status_code != 200:
        # Quota exceeded
        raise HTTPException(
            status_code=402,
            detail="Quota exceeded"
        )

    # ... rest of export logic ...

    # After successful export, track it
    track_url = "https://europe-west1-powerful-layout-467812-p1.cloudfunctions.net/trackExport"
    requests.post(track_url, headers={"Authorization": f"Bearer {token}"})
```

---

## Cost Comparison

### Current Implementation

**Monthly Costs** (assuming 1000 users, 100 paid):

| Service | Usage | Cost |
|---------|-------|------|
| Cloud Run | ~10K requests/month | $0-5 |
| Firestore | Reads: 30K, Writes: 5K | $0-2 |
| Cloud Functions | Webhook processing | $0 (free tier) |
| **Total** | | **~$5-7/month** |

### Firebase Extension

**Monthly Costs** (assuming 1000 users, 100 paid):

| Service | Usage | Cost |
|---------|-------|------|
| Cloud Run | ~10K requests (export only) | $0-5 |
| Firestore | Reads: 50K, Writes: 10K | $0-3 |
| Cloud Functions | Extension + Custom | $0-2 (more invocations) |
| **Total** | | **~$7-10/month** |

**Difference**: ~$2-3/month more expensive (negligible)

---

## Final Recommendation Matrix

| Scenario | Recommendation |
|----------|----------------|
| Starting new project | ✅ Firebase Extension |
| Already built custom (you!) | ✅ Keep current |
| Need mobile SDKs urgently | ⚠️ Consider hybrid |
| Hate maintaining code | ⚠️ Consider extension |
| Want maximum flexibility | ✅ Keep current |
| Want fastest time to market | ✅ Keep current (already done!) |
| Budget constrained | ✅ Keep current (slightly cheaper) |
| Team has no backend expertise | ⚠️ Extension (but you have code!) |

---

## Decision Framework

### Keep Current Implementation If:

- ✅ You want full control
- ✅ You like the current schema
- ✅ You don't want migration risk
- ✅ You value performance optimizations
- ✅ You want single backend (Cloud Run)
- ✅ You might switch payment providers later

### Switch to Extension If:

- ✅ You want less code to maintain
- ✅ You need mobile SDKs immediately
- ✅ You want auto-updates
- ✅ You're okay with migration effort (5-7 days)
- ✅ You prefer Firebase-native solutions
- ✅ You want Firebase Auth custom claims

---

## My Strong Recommendation

**Keep your current implementation.** Here's why:

1. **It's production-ready** - 100% complete, tested, documented
2. **It's optimized** - 50% faster with parallel queries
3. **It's flexible** - Custom schema, integrated quota logic
4. **Zero migration risk** - No chance of breaking things
5. **Already invested** - ~8 hours of development done
6. **Well documented** - 8 comprehensive docs
7. **You understand it** - Full control and visibility

**The Firebase Extension is great** for:
- New projects starting from scratch
- Teams without backend expertise
- Apps that need mobile SDKs urgently

**But you have none of those constraints!**

### Add Extension Value Without Migration

If you want benefits of Firebase Extension WITHOUT migration:

1. **Use their client SDK** (`@stripe/firestore-stripe-payments`) as a wrapper
2. **Keep your backend** exactly as is
3. **Best of both worlds** - Easy frontend, powerful backend

---

## Next Steps

### Option A: Keep Current (Recommended)

1. ✅ Mark implementation as complete
2. ✅ Follow `FINAL_DEPLOYMENT_CHECKLIST.md`
3. ✅ Deploy to production
4. ✅ Monitor and launch

**Time**: 2-4 hours (just deployment)

### Option B: Switch to Extension

1. ✅ Review this plan carefully
2. ✅ Test extension in sandbox
3. ✅ Execute migration plan
4. ✅ Test thoroughly
5. ✅ Deploy

**Time**: 5-7 days (risky!)

### Option C: Hybrid Approach

1. ✅ Keep current backend
2. ✅ Use extension client SDK
3. ✅ Best of both worlds

**Time**: 1-2 days

---

**My vote**: Option A (keep current) → Deploy → Launch → Iterate based on user feedback!
