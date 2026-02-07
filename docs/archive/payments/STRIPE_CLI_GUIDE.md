# Stripe CLI Quick Reference Guide

## Installation

✅ **Already installed!** (v1.32.0)

```bash
# Check version
stripe --version
```

## Initial Setup

### 1. Login to Stripe

```bash
# Login (opens browser for authentication)
stripe login

# Login for specific project
stripe login --project-name svg2ooxml
```

### 2. Verify Login

```bash
# Show current configuration
stripe config --list
```

## Quick Start Script

We've created a helper script for common tasks:

```bash
# Run the interactive setup script
./scripts/stripe-setup.sh
```

**Menu Options**:
1. Create products (Pro & Enterprise)
2. List existing products
3. Test webhooks locally
4. Test webhooks to Cloud Run
5. Trigger test events
6. View recent logs
7. Setup everything (automated)

## Common Commands

### Products & Prices

#### Create Product

```bash
# Create Pro product
stripe products create \
  --name "svg2ooxml Pro" \
  --description "Unlimited exports to Google Slides"

# Returns: prod_xxxxx
```

#### Create Price

```bash
# Create $9/month price
stripe prices create \
  --product prod_xxxxx \
  --unit-amount 900 \
  --currency usd \
  --recurring interval=month

# Returns: price_xxxxx
```

#### List Products

```bash
# List all products
stripe products list

# List with limit
stripe products list --limit 5

# Get specific product
stripe products retrieve prod_xxxxx
```

#### List Prices

```bash
# List all prices
stripe prices list

# List prices for specific product
stripe prices list --product prod_xxxxx
```

### Webhooks

#### Listen for Webhooks (Local Development)

```bash
# Forward webhooks to localhost
stripe listen --forward-to http://localhost:8080/api/webhook/stripe

# This will output a webhook signing secret like:
# > Ready! Your webhook signing secret is whsec_xxxxx
# Save this secret for your .env file!
```

#### Listen for Webhooks (Cloud Run)

```bash
# Forward webhooks to your deployed Cloud Run service
stripe listen --forward-to https://svg2ooxml-export-sghya3t5ya-ew.a.run.app/api/webhook/stripe
```

#### Trigger Test Events

```bash
# Subscription created
stripe trigger customer.subscription.created

# Subscription updated
stripe trigger customer.subscription.updated

# Subscription deleted (cancellation)
stripe trigger customer.subscription.deleted

# Payment succeeded
stripe trigger invoice.payment_succeeded

# Payment failed
stripe trigger invoice.payment_failed

# Checkout completed
stripe trigger checkout.session.completed
```

### Customers

#### List Customers

```bash
# List all customers
stripe customers list

# List with email filter
stripe customers list --email test@example.com
```

#### Create Test Customer

```bash
# Create customer
stripe customers create \
  --email test@example.com \
  --name "Test User"
```

#### Get Customer Details

```bash
# Retrieve customer
stripe customers retrieve cus_xxxxx
```

### Subscriptions

#### List Subscriptions

```bash
# List all subscriptions
stripe subscriptions list

# List for specific customer
stripe subscriptions list --customer cus_xxxxx

# List active subscriptions only
stripe subscriptions list --status active
```

#### Get Subscription Details

```bash
# Retrieve subscription
stripe subscriptions retrieve sub_xxxxx
```

#### Cancel Subscription

```bash
# Cancel immediately
stripe subscriptions cancel sub_xxxxx

# Cancel at period end
stripe subscriptions update sub_xxxxx \
  --cancel-at-period-end true
```

### Events & Logs

#### View Recent Events

```bash
# List recent events
stripe events list --limit 10

# Get specific event
stripe events retrieve evt_xxxxx
```

#### Resend Webhook

```bash
# Resend failed webhook
stripe events resend evt_xxxxx
```

#### Tail Logs

```bash
# Stream real-time API logs
stripe logs tail

# Filter by event type
stripe logs tail --filter-event-type customer.subscription.created

# Filter by status
stripe logs tail --filter-status 200
```

### Webhook Endpoints

#### List Webhook Endpoints

```bash
# List configured webhooks
stripe webhook-endpoints list
```

#### Create Webhook Endpoint

```bash
# Create webhook via CLI
stripe webhook-endpoints create \
  --url https://svg2ooxml-export-sghya3t5ya-ew.a.run.app/api/webhook/stripe \
  --enabled-event customer.subscription.created \
  --enabled-event customer.subscription.updated \
  --enabled-event customer.subscription.deleted \
  --enabled-event invoice.payment_succeeded \
  --enabled-event invoice.payment_failed
```

## Testing Workflow

### Scenario 1: Test Locally

```bash
# Terminal 1: Start your local server
cd /Users/ynse/projects/svg2ooxml
python main.py

# Terminal 2: Forward webhooks
stripe listen --forward-to http://localhost:8080/api/webhook/stripe
# Copy the webhook signing secret (whsec_xxxxx)

# Terminal 3: Set environment variable and trigger event
export STRIPE_WEBHOOK_SECRET="whsec_xxxxx"
stripe trigger customer.subscription.created
```

### Scenario 2: Test Cloud Run

```bash
# Terminal 1: Watch Cloud Run logs
gcloud run services logs tail svg2ooxml-export --region=europe-west1

# Terminal 2: Forward webhooks to Cloud Run
stripe listen --forward-to https://svg2ooxml-export-sghya3t5ya-ew.a.run.app/api/webhook/stripe

# Terminal 3: Trigger event
stripe trigger invoice.payment_succeeded
```

### Scenario 3: Full Payment Flow Test

```bash
# 1. Create test customer
CUSTOMER=$(stripe customers create \
  --email test@example.com \
  --name "Test User" \
  -o json)

CUSTOMER_ID=$(echo $CUSTOMER | grep -o '"id": *"[^"]*"' | head -1 | grep -o 'cus_[^"]*')

# 2. Create subscription
stripe subscriptions create \
  --customer $CUSTOMER_ID \
  --items[0][price]=price_xxxxx

# 3. Check webhook was received
stripe events list --limit 5
```

## Test Cards

Use these test card numbers in checkout:

- **Success**: `4242 4242 4242 4242`
- **Declined**: `4000 0000 0000 0002`
- **Requires Authentication**: `4000 0025 0000 3155`
- **Insufficient Funds**: `4000 0000 0000 9995`

**Details**:
- Any future expiration date (e.g., 12/34)
- Any 3-digit CVC (e.g., 123)
- Any ZIP code

## Advanced Usage

### JSON Output for Scripting

```bash
# Get JSON output
stripe products list -o json

# Parse with jq
stripe products list -o json | jq '.data[0].id'
```

### API Requests

```bash
# Make raw API request
stripe get /v1/customers/cus_xxxxx

# POST request
stripe post /v1/customers \
  email=test@example.com \
  name="Test User"
```

### Fixtures for Complex Scenarios

```bash
# Load fixture data
stripe fixtures fixtures/subscriptions.json
```

## Useful Aliases

Add these to your `~/.zshrc` or `~/.bashrc`:

```bash
# Stripe aliases
alias stripe-local="stripe listen --forward-to http://localhost:8080/api/webhook/stripe"
alias stripe-cloud="stripe listen --forward-to https://svg2ooxml-export-sghya3t5ya-ew.a.run.app/api/webhook/stripe"
alias stripe-logs="stripe logs tail"
alias stripe-test="stripe trigger customer.subscription.created"
```

## Environment Variables

After running setup, add these to your `.env`:

```bash
# Get from Stripe Dashboard: https://dashboard.stripe.com/test/apikeys
STRIPE_SECRET_KEY=sk_test_xxxxx

# Get from `stripe listen` output
STRIPE_WEBHOOK_SECRET=whsec_xxxxx

# Get from product creation
STRIPE_PRICE_ID_PRO=price_xxxxx
STRIPE_PRICE_ID_ENTERPRISE=price_xxxxx
```

## Troubleshooting

### Issue: "stripe: command not found"

```bash
# Reinstall
brew install stripe/stripe-cli/stripe
```

### Issue: "Forbidden: You are not logged in"

```bash
# Login again
stripe login
```

### Issue: Webhook not receiving events

```bash
# Check webhook endpoint is configured
stripe webhook-endpoints list

# Check recent events
stripe events list --limit 5

# Check logs
stripe logs tail
```

### Issue: "Invalid signature"

The webhook signing secret changed. When using `stripe listen`, you get a temporary secret starting with `whsec_`.

**For local testing**: Use the secret from `stripe listen` output
**For production**: Use the secret from Stripe Dashboard → Webhooks

## Quick Reference

| Task | Command |
|------|---------|
| Login | `stripe login` |
| Create product | `stripe products create --name "Product"` |
| Create price | `stripe prices create --product prod_xxx --unit-amount 900` |
| List products | `stripe products list` |
| Listen locally | `stripe listen --forward-to http://localhost:8080/api/webhook/stripe` |
| Trigger event | `stripe trigger customer.subscription.created` |
| View logs | `stripe logs tail` |
| List customers | `stripe customers list` |
| List subscriptions | `stripe subscriptions list` |
| Cancel subscription | `stripe subscriptions cancel sub_xxx` |

## Resources

- **Stripe CLI Docs**: https://stripe.com/docs/stripe-cli
- **API Reference**: https://stripe.com/docs/api
- **Webhook Events**: https://stripe.com/docs/api/events/types
- **Test Cards**: https://stripe.com/docs/testing

## Next Steps

1. Run `./scripts/stripe-setup.sh` to create products
2. Test webhooks locally with `stripe listen`
3. Trigger test events to verify your webhook handler
4. Check logs with `stripe logs tail`
5. When ready, configure production webhook in Stripe Dashboard

---

**Tip**: Keep the Stripe CLI running in a terminal tab during development. It's incredibly useful for debugging webhook issues!
