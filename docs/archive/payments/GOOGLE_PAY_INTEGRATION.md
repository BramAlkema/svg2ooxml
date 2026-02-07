# Adding Google Pay to Stripe Checkout

## Overview

**Important**: Google Pay is NOT a replacement for Stripe. It's a payment method that works **with** Stripe.

### What This Means

- ✅ Keep all your existing Stripe code
- ✅ Keep subscription management, webhooks, portal
- ✅ Just add Google Pay as a payment option in checkout
- ✅ Users can choose: Credit card OR Google Pay
- ✅ Both go through Stripe

## Why Add Google Pay?

### Benefits

1. **Better Mobile UX**: One-tap checkout on mobile devices
2. **Higher Conversion**: 20-30% increase in mobile conversions
3. **Faster Checkout**: No typing card numbers on phone
4. **Security**: Tokenized payments, no card details shared
5. **Trust**: Users trust Google Pay brand

### Perfect For

- Mobile users (Figma mobile app)
- Returning customers
- Quick upgrades from plugin
- Reducing checkout abandonment

## Implementation (Simple!)

### Option 1: Enable in Stripe Dashboard (Easiest)

This requires **zero code changes**!

1. **Go to Stripe Dashboard**: https://dashboard.stripe.com/settings/payment_methods
2. **Enable Google Pay**: Check the box next to "Google Pay"
3. **That's it!** 🎉

Stripe Checkout will automatically show Google Pay button on supported devices.

### Option 2: Customize Checkout Session (More Control)

Update your checkout creation to explicitly enable Google Pay:

```python
# In src/svg2ooxml/api/routes/subscription.py

@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    request: CheckoutRequest,
    current_user: dict = Depends(require_auth),
    stripe_service: StripeService = Depends(get_stripe_service),
    repo: SubscriptionRepository = Depends(get_subscription_repo),
):
    # ... existing code ...

    # Create checkout session with Google Pay enabled
    session = await stripe_service.create_checkout_session(
        customer_id=user["stripeCustomerId"],
        price_id=price_id,
        success_url=request.success_url,
        cancel_url=request.cancel_url,
        # Add these lines:
        payment_method_types=["card", "google_pay"],  # Enable Google Pay
    )

    # ... rest of code ...
```

Update `StripeService.create_checkout_session()`:

```python
# In src/svg2ooxml/api/services/stripe_service.py

async def create_checkout_session(
    self,
    customer_id: str,
    price_id: str,
    success_url: str,
    cancel_url: str,
    payment_method_types: list[str] | None = None,  # Add this parameter
) -> Dict[str, Any]:
    """Create Stripe checkout session."""

    if payment_method_types is None:
        payment_method_types = ["card", "google_pay"]  # Default to both

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        payment_method_types=payment_method_types,  # Use parameter
        line_items=[
            {
                "price": price_id,
                "quantity": 1,
            }
        ],
        success_url=success_url,
        cancel_url=cancel_url,
        allow_promotion_codes=True,
    )

    return {
        "checkout_url": session.url,
        "session_id": session.id,
    }
```

## What Users See

### Mobile Device (Chrome/Safari)
```
┌─────────────────────────┐
│  Pay with Google Pay    │  ← One-tap button
├─────────────────────────┤
│         OR              │
├─────────────────────────┤
│  Pay with credit card   │  ← Traditional form
└─────────────────────────┘
```

### Desktop (if Google Pay wallet set up)
```
┌─────────────────────────┐
│  [G] Pay               │  ← If wallet configured
├─────────────────────────┤
│         OR              │
├─────────────────────────┤
│  Card Number: ____     │
│  Expiry: __  CVC: ___  │
└─────────────────────────┘
```

### Desktop (no Google Pay)
```
┌─────────────────────────┐
│  Card Number: ____     │  ← Only card form shown
│  Expiry: __  CVC: ___  │
└─────────────────────────┘
```

Stripe automatically shows/hides Google Pay based on device and wallet setup!

## Testing Google Pay

### Test Mode Setup

1. **Enable in Stripe Dashboard** (test mode)
   - Settings → Payment methods → Enable "Google Pay"

2. **Test on Mobile Device**:
   ```bash
   # Open your checkout URL on phone
   # If you have Google Pay set up, you'll see the button
   ```

3. **Test Cards**: Use Stripe test cards
   - Success: `4242 4242 4242 4242`
   - Declined: `4000 0000 0000 0002`

### Local Testing

```bash
# Google Pay only works on:
# - HTTPS domains (not localhost)
# - Or localhost for testing

# So you can test locally at http://localhost:8080
# But users need HTTPS in production
```

## Other Payment Methods You Can Add

Stripe supports **tons** of payment methods. You can enable these with zero code changes:

### Popular Options

**Digital Wallets**:
- ✅ Google Pay (recommended for mobile)
- ✅ Apple Pay (recommended for iOS)
- ✅ PayPal (coming soon to Stripe Checkout)

**Buy Now, Pay Later**:
- Klarna
- Affirm
- Afterpay/Clearpay

**Regional Methods**:
- iDEAL (Netherlands)
- SEPA Direct Debit (Europe)
- Alipay (China)
- WeChat Pay (China)

**Bank Transfers**:
- ACH (US bank accounts)
- SEPA (European bank accounts)

### How to Enable

1. Go to: https://dashboard.stripe.com/settings/payment_methods
2. Check boxes for methods you want
3. Stripe Checkout automatically shows them to eligible users

**That's it!** No code changes needed.

## Recommendation for svg2ooxml

### Start Simple

**Just enable in Stripe Dashboard** (Option 1):
1. Go to settings
2. Enable Google Pay
3. Enable Apple Pay (while you're there)
4. Done!

**Why this works**:
- Zero code changes
- Works immediately
- Stripe handles all complexity
- Automatically shown on supported devices
- No downside

### Later Enhancements

If you want more control:
1. Use Option 2 to customize checkout
2. Add payment method selection UI in plugin
3. Track which payment methods are most popular
4. Optimize checkout flow based on data

## Cost Comparison

### Stripe + Google Pay
- Stripe fee: 2.9% + $0.30 per transaction
- Google Pay fee: **$0** (included in Stripe fee)
- Subscription management: **Included**
- Customer portal: **Included**
- Webhooks: **Included**

### Alternatives (NOT Recommended)

**Google Play Billing** (for Android apps):
- Fee: **15-30%** (much higher!)
- Only works in Android app (not web)
- Different API, rewrite needed
- No subscription portal

**PayPal Subscriptions**:
- Fee: 3.49% + $0.49 (higher)
- No customer portal
- Limited subscription features
- Webhook issues common

**Paddle**:
- Fee: 5% + $0.50 (higher)
- Merchant of record (handles taxes)
- Less control over UX

**Verdict**: Stripe + Google Pay is the best option

## Implementation Checklist

### Immediate (Zero Code)

- [ ] Login to Stripe Dashboard
- [ ] Go to Settings → Payment Methods
- [ ] Enable "Google Pay"
- [ ] Enable "Apple Pay" (while you're there)
- [ ] Test on mobile device
- [ ] Deploy (no code changes needed!)

### Optional (Better Control)

- [ ] Update `StripeService.create_checkout_session()` with payment_method_types parameter
- [ ] Update checkout endpoint to pass payment methods
- [ ] Test in local environment
- [ ] Deploy updated code
- [ ] Monitor which methods users prefer

## FAQs

### Q: Does this cost more?
**A**: No! Google Pay is free. You only pay Stripe's normal 2.9% + $0.30.

### Q: Do I need to change my code?
**A**: No! Just enable it in Stripe Dashboard.

### Q: Will it work on desktop?
**A**: Yes, if users have Google Pay wallet set up on Chrome.

### Q: Will it work on iPhone?
**A**: Yes, but they'll more likely use Apple Pay. Enable both!

### Q: What about subscriptions?
**A**: Works perfectly! Google Pay supports recurring payments.

### Q: Does this replace Stripe?
**A**: No! Google Pay is a payment METHOD. Stripe is the payment PROCESSOR. You need both.

### Q: Can users still use credit cards?
**A**: Yes! They can choose Google Pay OR credit card.

### Q: Is it secure?
**A**: Yes! Google Pay uses tokenization. Card details never shared.

### Q: Does it work in test mode?
**A**: Yes! Use Stripe test cards with Google Pay in test mode.

## Comparison Table

| Feature | Stripe Only | Stripe + Google Pay |
|---------|-------------|---------------------|
| Mobile UX | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Desktop UX | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Conversion | Good | Better (+20-30%) |
| Setup Time | Done ✅ | +5 minutes |
| Code Changes | None | None (Dashboard) |
| Extra Cost | $0 | $0 |
| Subscriptions | ✅ | ✅ |
| Webhooks | ✅ | ✅ |
| Portal | ✅ | ✅ |

## Next Steps

1. **Read this**: https://stripe.com/docs/payments/google-pay
2. **Enable in Dashboard**: 5 minute task
3. **Test on mobile**: Verify it works
4. **Launch**: Users get better UX automatically

---

**Bottom Line**: Keep Stripe (you've already built it), just add Google Pay as a payment method. Takes 5 minutes, zero code changes, better mobile UX. Win-win! 🎉
