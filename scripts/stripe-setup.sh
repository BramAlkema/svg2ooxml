#!/bin/bash
# Stripe Setup Script for svg2ooxml
# This script helps you set up Stripe products and test webhooks

set -e

echo "🔧 svg2ooxml Stripe Setup"
echo "========================="
echo ""

# Check if stripe CLI is installed
if ! command -v stripe &> /dev/null; then
    echo "❌ Stripe CLI not found. Install it with:"
    echo "   brew install stripe/stripe-cli/stripe"
    exit 1
fi

echo "✅ Stripe CLI installed (version $(stripe --version))"
echo ""

# Check if logged in
if ! stripe config --list &> /dev/null; then
    echo "🔐 Please login to Stripe first:"
    echo "   stripe login"
    echo ""
    read -p "Do you want to login now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        stripe login
    else
        exit 1
    fi
fi

echo "✅ Logged in to Stripe"
echo ""

# Menu
echo "What would you like to do?"
echo ""
echo "1. Create products (Pro & Enterprise)"
echo "2. List existing products"
echo "3. Test webhooks locally"
echo "4. Test webhooks to Cloud Run"
echo "5. Trigger test events"
echo "6. View recent logs"
echo "7. Setup everything (products + test)"
echo ""
read -p "Enter choice [1-7]: " choice

case $choice in
    1)
        echo ""
        echo "📦 Creating products..."
        echo ""

        # Create Pro product
        echo "Creating Pro product ($9/month)..."
        PRO_PRODUCT=$(stripe products create \
            --name "svg2ooxml Pro" \
            --description "Unlimited exports to Google Slides" \
            -o json 2>/dev/null)

        PRO_PRODUCT_ID=$(echo "$PRO_PRODUCT" | grep -o '"id": *"[^"]*"' | head -1 | grep -o 'prod_[^"]*')

        PRO_PRICE=$(stripe prices create \
            --product "$PRO_PRODUCT_ID" \
            --unit-amount 900 \
            --currency usd \
            --recurring interval=month \
            -o json 2>/dev/null)

        PRO_PRICE_ID=$(echo "$PRO_PRICE" | grep -o '"id": *"[^"]*"' | head -1 | grep -o 'price_[^"]*')

        echo "✅ Pro Product ID: $PRO_PRODUCT_ID"
        echo "✅ Pro Price ID: $PRO_PRICE_ID"
        echo ""

        # Create Enterprise product
        echo "Creating Enterprise product ($49/month)..."
        ENT_PRODUCT=$(stripe products create \
            --name "svg2ooxml Enterprise" \
            --description "Unlimited exports + API access + priority support" \
            -o json 2>/dev/null)

        ENT_PRODUCT_ID=$(echo "$ENT_PRODUCT" | grep -o '"id": *"[^"]*"' | head -1 | grep -o 'prod_[^"]*')

        ENT_PRICE=$(stripe prices create \
            --product "$ENT_PRODUCT_ID" \
            --unit-amount 4900 \
            --currency usd \
            --recurring interval=month \
            -o json 2>/dev/null)

        ENT_PRICE_ID=$(echo "$ENT_PRICE" | grep -o '"id": *"[^"]*"' | head -1 | grep -o 'price_[^"]*')

        echo "✅ Enterprise Product ID: $ENT_PRODUCT_ID"
        echo "✅ Enterprise Price ID: $ENT_PRICE_ID"
        echo ""

        # Save to .env
        echo "💾 Saving to .env file..."
        if [ -f .env ]; then
            # Update existing .env
            if grep -q "STRIPE_PRICE_ID_PRO" .env; then
                sed -i.bak "s/STRIPE_PRICE_ID_PRO=.*/STRIPE_PRICE_ID_PRO=$PRO_PRICE_ID/" .env
            else
                echo "STRIPE_PRICE_ID_PRO=$PRO_PRICE_ID" >> .env
            fi

            if grep -q "STRIPE_PRICE_ID_ENTERPRISE" .env; then
                sed -i.bak "s/STRIPE_PRICE_ID_ENTERPRISE=.*/STRIPE_PRICE_ID_ENTERPRISE=$ENT_PRICE_ID/" .env
            else
                echo "STRIPE_PRICE_ID_ENTERPRISE=$ENT_PRICE_ID" >> .env
            fi
            rm -f .env.bak
        else
            cat > .env <<EOF
# Stripe Configuration (Test Mode)
STRIPE_PRICE_ID_PRO=$PRO_PRICE_ID
STRIPE_PRICE_ID_ENTERPRISE=$ENT_PRICE_ID
EOF
        fi

        echo "✅ Saved to .env"
        echo ""
        echo "📋 Next steps:"
        echo "1. Get your Stripe secret key from: https://dashboard.stripe.com/test/apikeys"
        echo "2. Add to .env: STRIPE_SECRET_KEY=sk_test_..."
        echo "3. Configure webhook endpoint in Stripe dashboard"
        echo "4. Add webhook secret to .env: STRIPE_WEBHOOK_SECRET=whsec_..."
        ;;

    2)
        echo ""
        echo "📦 Listing products..."
        stripe products list --limit 10
        echo ""
        echo "💰 Listing prices..."
        stripe prices list --limit 10
        ;;

    3)
        echo ""
        echo "🎧 Starting webhook listener (localhost:8080)..."
        echo "Press Ctrl+C to stop"
        echo ""
        stripe listen --forward-to http://localhost:8080/api/webhook/stripe
        ;;

    4)
        echo ""
        echo "🎧 Starting webhook listener (Cloud Run)..."
        echo "Press Ctrl+C to stop"
        echo ""
        stripe listen --forward-to https://svg2ooxml-export-sghya3t5ya-ew.a.run.app/api/webhook/stripe
        ;;

    5)
        echo ""
        echo "🧪 Trigger test events"
        echo ""
        echo "Which event would you like to trigger?"
        echo "1. customer.subscription.created"
        echo "2. customer.subscription.updated"
        echo "3. customer.subscription.deleted"
        echo "4. invoice.payment_succeeded"
        echo "5. invoice.payment_failed"
        echo "6. checkout.session.completed"
        echo ""
        read -p "Enter choice [1-6]: " event_choice

        case $event_choice in
            1) EVENT="customer.subscription.created" ;;
            2) EVENT="customer.subscription.updated" ;;
            3) EVENT="customer.subscription.deleted" ;;
            4) EVENT="invoice.payment_succeeded" ;;
            5) EVENT="invoice.payment_failed" ;;
            6) EVENT="checkout.session.completed" ;;
            *) echo "Invalid choice"; exit 1 ;;
        esac

        echo ""
        echo "Triggering $EVENT..."
        stripe trigger "$EVENT"
        echo ""
        echo "✅ Event triggered!"
        echo "Check your webhook endpoint logs to see if it was received."
        ;;

    6)
        echo ""
        echo "📊 Recent Stripe API logs..."
        stripe logs tail --limit 20
        ;;

    7)
        echo ""
        echo "🚀 Full setup - Creating products and testing webhooks"
        echo ""

        # Create products (same as option 1)
        echo "📦 Step 1: Creating products..."

        PRO_PRODUCT=$(stripe products create \
            --name "svg2ooxml Pro" \
            --description "Unlimited exports to Google Slides" \
            -o json 2>/dev/null)

        PRO_PRODUCT_ID=$(echo "$PRO_PRODUCT" | grep -o '"id": *"[^"]*"' | head -1 | grep -o 'prod_[^"]*')

        PRO_PRICE=$(stripe prices create \
            --product "$PRO_PRODUCT_ID" \
            --unit-amount 900 \
            --currency usd \
            --recurring interval=month \
            -o json 2>/dev/null)

        PRO_PRICE_ID=$(echo "$PRO_PRICE" | grep -o '"id": *"[^"]*"' | head -1 | grep -o 'price_[^"]*')

        echo "✅ Pro: $PRO_PRICE_ID"

        ENT_PRODUCT=$(stripe products create \
            --name "svg2ooxml Enterprise" \
            --description "Unlimited exports + API access + priority support" \
            -o json 2>/dev/null)

        ENT_PRODUCT_ID=$(echo "$ENT_PRODUCT" | grep -o '"id": *"[^"]*"' | head -1 | grep -o 'prod_[^"]*')

        ENT_PRICE=$(stripe prices create \
            --product "$ENT_PRODUCT_ID" \
            --unit-amount 4900 \
            --currency usd \
            --recurring interval=month \
            -o json 2>/dev/null)

        ENT_PRICE_ID=$(echo "$ENT_PRICE" | grep -o '"id": *"[^"]*"' | head -1 | grep -o 'price_[^"]*')

        echo "✅ Enterprise: $ENT_PRICE_ID"
        echo ""

        # Test webhook
        echo "🧪 Step 2: Testing webhook..."
        echo "Triggering customer.subscription.created..."
        stripe trigger customer.subscription.created > /dev/null 2>&1
        echo "✅ Test event sent"
        echo ""

        echo "✅ Setup complete!"
        echo ""
        echo "📋 Your Price IDs:"
        echo "   Pro: $PRO_PRICE_ID"
        echo "   Enterprise: $ENT_PRICE_ID"
        echo ""
        echo "📋 Next steps:"
        echo "1. Add these to your Cloud Run environment variables"
        echo "2. Configure webhook endpoint in Stripe dashboard"
        echo "3. Test the full payment flow"
        ;;

    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "✅ Done!"
