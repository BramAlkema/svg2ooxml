# Stripe Payment Integration Specification

## Overview
Implement a freemium pricing model for the svg2ooxml Figma plugin where:
- **Free users**: Limited exports per month
- **Paid users**: Unlimited exports + priority processing

**Important Discovery**: Figma does NOT expose user billing tier (Professional/Organization) through the Plugin API. We cannot detect if a Figma user has a paid Figma plan. Instead, we'll implement our own payment system using either:
1. Figma's built-in Payments API (if approved as Figma seller)
2. Third-party Stripe integration (recommended for flexibility)

## Recommended Approach: Third-Party Stripe Integration

Since Figma's seller program is currently full, we'll implement direct Stripe integration.

### Pricing Model

**Free Tier**:
- 5 exports per month
- Standard processing
- All features available
- No credit card required

**Pro Tier** - $9/month:
- Unlimited exports
- Priority processing
- Early access to new features
- Email support

**Enterprise Tier** - $49/month:
- Everything in Pro
- API access
- Custom branding
- Priority support

## Architecture

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│                 │         │                  │         │                 │
│  Figma Plugin   │────────▶│  Backend API     │────────▶│  Stripe API     │
│  (ui.js)        │         │  (FastAPI)       │         │                 │
│                 │         │                  │         │                 │
└─────────────────┘         └──────────────────┘         └─────────────────┘
        │                            │
        │                            │
        ▼                            ▼
┌─────────────────┐         ┌──────────────────┐
│                 │         │                  │
│  Figma Storage  │         │  PostgreSQL DB   │
│  (clientStorage)│         │  - Subscriptions │
│  - User ID      │         │  - Usage Metrics │
│  - Session      │         │  - Invoices      │
│                 │         │                  │
└─────────────────┘         └──────────────────┘
```

## Implementation Plan

### Phase 1: Backend Infrastructure

#### 1.1 Database Schema
```sql
-- Users table (extends Firebase auth)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    firebase_uid TEXT UNIQUE NOT NULL,
    email TEXT NOT NULL,
    stripe_customer_id TEXT UNIQUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Subscriptions table
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    stripe_subscription_id TEXT UNIQUE,
    stripe_price_id TEXT NOT NULL,
    status TEXT NOT NULL, -- active, canceled, past_due, etc.
    tier TEXT NOT NULL, -- free, pro, enterprise
    current_period_start TIMESTAMP,
    current_period_end TIMESTAMP,
    cancel_at_period_end BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Usage tracking table
CREATE TABLE export_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    export_count INT DEFAULT 0,
    month_year TEXT NOT NULL, -- e.g., "2024-11"
    last_export_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, month_year)
);

-- Indexes
CREATE INDEX idx_users_firebase_uid ON users(firebase_uid);
CREATE INDEX idx_users_stripe_customer_id ON users(stripe_customer_id);
CREATE INDEX idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX idx_subscriptions_status ON subscriptions(status);
CREATE INDEX idx_export_usage_user_month ON export_usage(user_id, month_year);
```

#### 1.2 Stripe Setup
```bash
# Environment variables
STRIPE_SECRET_KEY=sk_test_xxx
STRIPE_PUBLISHABLE_KEY=pk_test_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
STRIPE_PRICE_ID_PRO=price_xxx
STRIPE_PRICE_ID_ENTERPRISE=price_xxx
```

#### 1.3 API Endpoints

**GET /api/v1/subscription/status**
- Returns current user's subscription status
- Response:
```json
{
  "tier": "free|pro|enterprise",
  "status": "active|canceled|past_due",
  "usage": {
    "exports_this_month": 3,
    "limit": 5,
    "unlimited": false
  },
  "subscription": {
    "current_period_end": "2024-12-01T00:00:00Z",
    "cancel_at_period_end": false
  }
}
```

**POST /api/v1/subscription/checkout**
- Creates Stripe checkout session
- Request:
```json
{
  "price_id": "price_xxx",
  "success_url": "https://figma.com",
  "cancel_url": "https://figma.com"
}
```
- Response:
```json
{
  "checkout_url": "https://checkout.stripe.com/c/pay/xxx"
}
```

**POST /api/v1/subscription/portal**
- Creates Stripe customer portal session
- Returns URL for managing subscription
- Response:
```json
{
  "portal_url": "https://billing.stripe.com/p/session/xxx"
}
```

**POST /api/v1/export** (Modified)
- Add usage tracking
- Check subscription tier and limits
- Return quota exceeded error if limit reached

**POST /api/webhook/stripe**
- Handle Stripe webhook events:
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
  - `invoice.payment_succeeded`
  - `invoice.payment_failed`

### Phase 2: Plugin Integration

#### 2.1 Manifest Updates
```json
{
  "permissions": [
    "currentuser",
    "storage"
  ]
}
```

#### 2.2 Plugin UI Updates

**Add subscription section to ui.html**:
```html
<!-- Subscription Section -->
<div id="subscription-section" class="section">
  <div id="free-tier-info" style="display: none;">
    <div class="plan-badge">Free Plan</div>
    <div class="usage-info">
      <span id="usage-count">0</span> / <span id="usage-limit">5</span> exports this month
    </div>
    <button id="upgrade-btn" class="primary">Upgrade to Pro</button>
  </div>

  <div id="pro-tier-info" style="display: none;">
    <div class="plan-badge pro">Pro Plan</div>
    <div class="usage-info">Unlimited exports</div>
    <button id="manage-subscription-btn" class="secondary">Manage Subscription</button>
  </div>
</div>
```

#### 2.3 Plugin Code Updates (ui.js)

**Add subscription checking**:
```javascript
let currentSubscription = null;

// Check subscription status on load
async function checkSubscriptionStatus() {
  try {
    const response = await fetch(`${API_URL}/api/v1/subscription/status`, {
      headers: {
        'Authorization': `Bearer ${currentToken}`
      }
    });

    const data = await response.json();
    currentSubscription = data;
    updateSubscriptionUI(data);
    return data;

  } catch (error) {
    console.error('Failed to check subscription:', error);
    return null;
  }
}

// Update UI based on subscription
function updateSubscriptionUI(subscription) {
  const freeTier = document.getElementById('free-tier-info');
  const proTier = document.getElementById('pro-tier-info');

  if (subscription.tier === 'free') {
    freeTier.style.display = 'block';
    proTier.style.display = 'none';

    document.getElementById('usage-count').textContent = subscription.usage.exports_this_month;
    document.getElementById('usage-limit').textContent = subscription.usage.limit;

    // Show warning if near limit
    if (subscription.usage.exports_this_month >= subscription.usage.limit * 0.8) {
      showStatus(
        `You've used ${subscription.usage.exports_this_month}/${subscription.usage.limit} exports this month. Consider upgrading!`,
        'info'
      );
    }

  } else {
    freeTier.style.display = 'none';
    proTier.style.display = 'block';
  }
}

// Handle upgrade button
document.getElementById('upgrade-btn').addEventListener('click', async () => {
  try {
    const response = await fetch(`${API_URL}/api/v1/subscription/checkout`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${currentToken}`
      },
      body: JSON.stringify({
        price_id: 'price_pro_monthly', // From environment
        success_url: window.location.href,
        cancel_url: window.location.href
      })
    });

    const data = await response.json();

    // Open Stripe checkout in new window
    window.open(data.checkout_url, '_blank');

    showStatus('Complete checkout in the new window to upgrade', 'info');

  } catch (error) {
    console.error('Upgrade error:', error);
    showStatus(`Failed to start upgrade: ${error.message}`, 'error');
  }
});

// Handle manage subscription button
document.getElementById('manage-subscription-btn').addEventListener('click', async () => {
  try {
    const response = await fetch(`${API_URL}/api/v1/subscription/portal`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${currentToken}`
      }
    });

    const data = await response.json();

    // Open Stripe portal in new window
    window.open(data.portal_url, '_blank');

  } catch (error) {
    console.error('Portal error:', error);
    showStatus(`Failed to open subscription portal: ${error.message}`, 'error');
  }
});

// Check subscription before export
async function handleExport(frames, fileKey, fileName) {
  try {
    exportBtn.disabled = true;

    // Check subscription status first
    const subscription = await checkSubscriptionStatus();

    if (!subscription) {
      throw new Error('Failed to verify subscription status');
    }

    // Check if user has exceeded free tier limit
    if (subscription.tier === 'free' &&
        subscription.usage.exports_this_month >= subscription.usage.limit) {

      showStatus(
        `You've reached your monthly limit of ${subscription.usage.limit} exports. <a href="#" id="upgrade-link">Upgrade to Pro</a> for unlimited exports.`,
        'error'
      );
      hideProgress();
      return;
    }

    // Proceed with export
    showStatus(`Preparing to export ${frames.length} frame(s)...`, 'info');

    const jobId = await createExportJob(frames, fileKey, fileName);
    await pollJobStatus(jobId);

    // Refresh subscription status to update usage count
    await checkSubscriptionStatus();

  } catch (error) {
    console.error('Export error:', error);
    showStatus(`Export failed: ${error.message}`, 'error');
    hideProgress();

  } finally {
    exportBtn.disabled = false;
  }
}
```

### Phase 3: Backend Implementation

#### 3.1 Install Dependencies
```bash
pip install stripe python-dotenv
```

#### 3.2 Stripe Service (Python)
```python
# src/svg2ooxml/services/stripe_service.py

import stripe
from typing import Optional, Dict, Any
from datetime import datetime, timezone

class StripeService:
    def __init__(self, api_key: str):
        stripe.api_key = api_key

    async def create_customer(
        self,
        email: str,
        firebase_uid: str,
        name: Optional[str] = None
    ) -> str:
        """Create a Stripe customer"""
        customer = stripe.Customer.create(
            email=email,
            metadata={'firebase_uid': firebase_uid},
            name=name
        )
        return customer.id

    async def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str
    ) -> Dict[str, Any]:
        """Create a Stripe checkout session"""
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
            allow_promotion_codes=True
        )
        return {
            'checkout_url': session.url,
            'session_id': session.id
        }

    async def create_portal_session(
        self,
        customer_id: str,
        return_url: str
    ) -> Dict[str, Any]:
        """Create a Stripe customer portal session"""
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url
        )
        return {
            'portal_url': session.url
        }

    async def get_subscription(
        self,
        subscription_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get subscription details"""
        try:
            sub = stripe.Subscription.retrieve(subscription_id)
            return {
                'id': sub.id,
                'status': sub.status,
                'current_period_start': datetime.fromtimestamp(
                    sub.current_period_start, tz=timezone.utc
                ),
                'current_period_end': datetime.fromtimestamp(
                    sub.current_period_end, tz=timezone.utc
                ),
                'cancel_at_period_end': sub.cancel_at_period_end,
                'price_id': sub.items.data[0].price.id
            }
        except stripe.error.StripeError:
            return None

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
        webhook_secret: str
    ) -> stripe.Event:
        """Verify and parse Stripe webhook"""
        return stripe.Webhook.construct_event(
            payload, signature, webhook_secret
        )
```

#### 3.3 Subscription Endpoints
```python
# src/svg2ooxml/api/routes/subscription.py

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from ...services.stripe_service import StripeService
from ...services.auth_service import get_current_user

router = APIRouter(prefix="/api/v1/subscription", tags=["subscription"])

class CheckoutRequest(BaseModel):
    price_id: str
    success_url: str
    cancel_url: str

@router.get("/status")
async def get_subscription_status(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get current user's subscription status and usage"""

    # Get user from database
    user = await db.get_user_by_firebase_uid(current_user['uid'])

    # Get active subscription
    subscription = await db.get_active_subscription(user.id)

    # Get usage for current month
    current_month = datetime.now().strftime("%Y-%m")
    usage = await db.get_usage(user.id, current_month)

    # Determine tier and limits
    if subscription and subscription.status == 'active':
        tier = subscription.tier
        limit = None  # Unlimited for paid tiers
        unlimited = True
    else:
        tier = 'free'
        limit = 5
        unlimited = False

    return {
        "tier": tier,
        "status": subscription.status if subscription else "none",
        "usage": {
            "exports_this_month": usage.export_count if usage else 0,
            "limit": limit,
            "unlimited": unlimited
        },
        "subscription": {
            "current_period_end": subscription.current_period_end,
            "cancel_at_period_end": subscription.cancel_at_period_end
        } if subscription else None
    }

@router.post("/checkout")
async def create_checkout(
    request: CheckoutRequest,
    current_user = Depends(get_current_user),
    db = Depends(get_db),
    stripe_service: StripeService = Depends(get_stripe_service)
):
    """Create Stripe checkout session"""

    user = await db.get_user_by_firebase_uid(current_user['uid'])

    # Create Stripe customer if doesn't exist
    if not user.stripe_customer_id:
        customer_id = await stripe_service.create_customer(
            email=user.email,
            firebase_uid=current_user['uid']
        )
        await db.update_user_stripe_customer(user.id, customer_id)
    else:
        customer_id = user.stripe_customer_id

    # Create checkout session
    session = await stripe_service.create_checkout_session(
        customer_id=customer_id,
        price_id=request.price_id,
        success_url=request.success_url,
        cancel_url=request.cancel_url
    )

    return session

@router.post("/portal")
async def create_portal(
    current_user = Depends(get_current_user),
    db = Depends(get_db),
    stripe_service: StripeService = Depends(get_stripe_service)
):
    """Create Stripe customer portal session"""

    user = await db.get_user_by_firebase_uid(current_user['uid'])

    if not user.stripe_customer_id:
        raise HTTPException(
            status_code=400,
            detail="No subscription found"
        )

    portal = await stripe_service.create_portal_session(
        customer_id=user.stripe_customer_id,
        return_url="https://figma.com"
    )

    return portal
```

#### 3.4 Webhook Handler
```python
# src/svg2ooxml/api/routes/webhooks.py

from fastapi import APIRouter, Request, HTTPException
from ...services.stripe_service import StripeService
import stripe

router = APIRouter(prefix="/api/webhook", tags=["webhooks"])

@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    db = Depends(get_db),
    stripe_service: StripeService = Depends(get_stripe_service)
):
    """Handle Stripe webhook events"""

    payload = await request.body()
    signature = request.headers.get('stripe-signature')

    try:
        event = stripe_service.verify_webhook_signature(
            payload,
            signature,
            os.getenv('STRIPE_WEBHOOK_SECRET')
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle subscription events
    if event.type == 'customer.subscription.created':
        await handle_subscription_created(event.data.object, db)

    elif event.type == 'customer.subscription.updated':
        await handle_subscription_updated(event.data.object, db)

    elif event.type == 'customer.subscription.deleted':
        await handle_subscription_deleted(event.data.object, db)

    elif event.type == 'invoice.payment_succeeded':
        await handle_payment_succeeded(event.data.object, db)

    elif event.type == 'invoice.payment_failed':
        await handle_payment_failed(event.data.object, db)

    return {"status": "ok"}

async def handle_subscription_created(subscription, db):
    """Handle new subscription"""
    # Get user by Stripe customer ID
    user = await db.get_user_by_stripe_customer(subscription.customer)

    # Determine tier from price ID
    tier = get_tier_from_price_id(subscription.items.data[0].price.id)

    # Create subscription record
    await db.create_subscription(
        user_id=user.id,
        stripe_subscription_id=subscription.id,
        stripe_price_id=subscription.items.data[0].price.id,
        status=subscription.status,
        tier=tier,
        current_period_start=datetime.fromtimestamp(
            subscription.current_period_start
        ),
        current_period_end=datetime.fromtimestamp(
            subscription.current_period_end
        )
    )

def get_tier_from_price_id(price_id: str) -> str:
    """Map Stripe price ID to tier"""
    price_tiers = {
        os.getenv('STRIPE_PRICE_ID_PRO'): 'pro',
        os.getenv('STRIPE_PRICE_ID_ENTERPRISE'): 'enterprise'
    }
    return price_tiers.get(price_id, 'free')
```

### Phase 4: Usage Tracking

#### 4.1 Modify Export Service
```python
# src/svg2ooxml/api/services/export_service.py

async def create_export_job(...):
    # ... existing code ...

    # Check subscription and usage limits
    user = await db.get_user_by_firebase_uid(firebase_uid)
    subscription = await db.get_active_subscription(user.id)

    # Get current month usage
    current_month = datetime.now().strftime("%Y-%m")
    usage = await db.get_or_create_usage(user.id, current_month)

    # Check limits for free tier
    if not subscription or subscription.status != 'active':
        if usage.export_count >= 5:  # Free tier limit
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "quota_exceeded",
                    "message": "Monthly export limit reached. Upgrade to Pro for unlimited exports.",
                    "usage": {
                        "current": usage.export_count,
                        "limit": 5
                    }
                }
            )

    # Increment usage counter
    await db.increment_usage(user.id, current_month)

    # ... continue with export ...
```

## Testing Strategy

### Unit Tests
- Stripe webhook verification
- Subscription status calculation
- Usage limit enforcement

### Integration Tests
- Checkout flow end-to-end
- Webhook processing
- Usage tracking accuracy

### Manual Testing Checklist
1. [ ] Free user can export up to 5 times
2. [ ] Free user blocked at 6th export
3. [ ] Upgrade flow works (test mode)
4. [ ] Pro user has unlimited exports
5. [ ] Subscription portal works
6. [ ] Webhook updates subscription status
7. [ ] Usage resets each month
8. [ ] Cancellation works correctly

## Deployment Checklist

### Environment Variables
```bash
# Production
STRIPE_SECRET_KEY=sk_live_xxx
STRIPE_PUBLISHABLE_KEY=pk_live_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
STRIPE_PRICE_ID_PRO=price_xxx
STRIPE_PRICE_ID_ENTERPRISE=price_xxx

# URLs
STRIPE_SUCCESS_URL=https://powerful-layout-467812-p1.web.app/success
STRIPE_CANCEL_URL=https://powerful-layout-467812-p1.web.app/cancel
```

### Stripe Dashboard Setup
1. Create products (Pro, Enterprise)
2. Create prices (monthly/yearly)
3. Configure webhooks
4. Enable customer portal
5. Configure email templates
6. Set up tax collection (if applicable)

### Database Migration
```bash
# Run migrations to create subscription tables
alembic upgrade head
```

## Alternative: Figma Payments API

If you get approved for Figma's seller program, you can use the built-in Payments API instead:

```javascript
// Check payment status
const status = figma.payments.status.type; // "PAID" or "UNPAID"

// Initiate checkout
if (status === "UNPAID") {
  await figma.payments.initiateCheckoutAsync({
    interstitial: "PAID_FEATURE"
  });

  // Recheck status after checkout
  if (figma.payments.status.type === "PAID") {
    // User completed payment
  }
}
```

**Pros**:
- Integrated into Figma UI
- No backend needed
- Figma handles payments

**Cons**:
- Must be approved as seller
- Less control over pricing/features
- Limited to Figma's payment flow
- Can't differentiate usage tiers easily

## Pricing Recommendations

Based on competitor analysis:

| Plugin | Pricing | Features |
|--------|---------|----------|
| Autoflow | $49 one-time | 50 flows/file limit (free) |
| Remove BG | $13.25/month | Per-image pricing |
| Populate | $3/month | Content categories |
| html.to.design | $18/month | HTML import |

**Recommended Pricing**:
- Free: 5 exports/month
- Pro: $9/month (unlimited exports)
- Enterprise: $49/month (API + support)

## Success Metrics

- Free-to-paid conversion rate (target: 2-5%)
- Monthly recurring revenue (MRR)
- Churn rate (target: <5%)
- Average revenue per user (ARPU)
- Usage per tier

## Resources

- [Stripe Subscriptions Docs](https://stripe.com/docs/billing/subscriptions/overview)
- [Stripe Webhooks Guide](https://stripe.com/docs/webhooks)
- [Figma Payments API](https://www.figma.com/plugin-docs/api/figma-payments/)
- [Figma Plugin Monetization Forum](https://forum.figma.com/t/a-list-of-all-premium-figma-plugins/25963)
