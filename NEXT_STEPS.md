# 🎉 Code Pushed! Next Steps for Deployment

## ✅ What Just Happened

Your payment integration code is now on GitHub!
- **Commit**: 74a8f5d
- **Files**: 50 changed (11,507 insertions)
- **Repository**: https://github.com/BramAlkema/svg2ooxml

## ⚠️ GitHub Actions Won't Run Yet

The workflows need authentication to deploy. Here's what to do:

---

## Step 1: Get Firebase Token (5 minutes)

```bash
# Login to Firebase (opens browser)
firebase login

# Generate CI token
firebase login:ci

# Copy the token that's printed
# It will look like: 1//xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Add to GitHub Secrets**:
1. Go to: https://github.com/BramAlkema/svg2ooxml/settings/secrets/actions
2. Click "New repository secret"
3. Name: `FIREBASE_TOKEN`
4. Value: [paste the token from above]
5. Click "Add secret"

---

## Step 2: Set Up Google Cloud Authentication (15 minutes)

**Option A: Run the automated script** (Easiest)

```bash
./scripts/setup-github-deployment.sh
```

This will:
- Create Workload Identity Federation
- Create service account
- Grant permissions
- Tell you what GitHub Secrets to add

**Option B: Manual setup** (If script doesn't work)

Follow the detailed guide: `docs/GITHUB_DEPLOYMENT_SETUP.md`

**GitHub Secrets you'll need to add**:
- `WIF_PROVIDER` - Workload Identity Provider path
- `WIF_SERVICE_ACCOUNT` - Service account email

---

## Step 3: Manual Deployment (Until GitHub Actions is set up)

Since GitHub Actions isn't configured yet, let's deploy manually:

### Deploy Firebase Hosting

```bash
# Login to Firebase
firebase login

# Deploy hosting, rules, and indexes
firebase deploy --only hosting,firestore:rules,firestore:indexes \
  --project powerful-layout-467812-p1
```

### Deploy Cloud Run

```bash
# Build and deploy
gcloud builds submit --config cloudbuild.yaml \
  --project=powerful-layout-467812-p1 \
  --region=europe-west1
```

---

## Step 4: Set Environment Variables (Required!)

```bash
gcloud run services update svg2ooxml-export \
  --region=europe-west1 \
  --project=powerful-layout-467812-p1 \
  --set-env-vars="
ENVIRONMENT=production,
STRIPE_SECRET_KEY=sk_test_REPLACE_WITH_YOUR_KEY,
STRIPE_WEBHOOK_SECRET=whsec_REPLACE_WITH_YOUR_SECRET,
STRIPE_PRICE_ID_PRO=price_REPLACE_WITH_YOUR_PRO_ID,
STRIPE_PRICE_ID_ENTERPRISE=price_REPLACE_WITH_YOUR_ENT_ID
"
```

**Get these values from**:
- Stripe Dashboard: https://dashboard.stripe.com/test/apikeys
- Or run: `./scripts/stripe-setup.sh` to create products

---

## Step 5: Create Stripe Products

```bash
# Interactive setup
./scripts/stripe-setup.sh

# Choose option 1 or 7
```

This creates:
- Pro: $9/month
- Enterprise: $49/month

And saves the price IDs to `.env`

---

## Step 6: Configure Stripe Webhook

1. Go to: https://dashboard.stripe.com/test/webhooks
2. Click "Add endpoint"
3. Endpoint URL: `https://svg2ooxml-export-sghya3t5ya-ew.a.run.app/api/webhook/stripe`
4. Select events:
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
5. Copy the "Signing secret" (starts with `whsec_`)
6. Use it in Step 4 above

---

## Step 7: Test Everything

### Test Firebase Hosting

```bash
curl https://powerful-layout-467812-p1.web.app/auth.html
curl https://powerful-layout-467812-p1.web.app/payment-success.html
```

### Test Cloud Run

```bash
SERVICE_URL="https://svg2ooxml-export-sghya3t5ya-ew.a.run.app"

# Health check
curl $SERVICE_URL/health

# Should return: {"status":"healthy"}
```

### Test with Stripe CLI

```bash
# Forward webhooks
stripe listen --forward-to $SERVICE_URL/api/webhook/stripe

# In another terminal, trigger test
stripe trigger customer.subscription.created

# Check logs
gcloud run services logs tail svg2ooxml-export --region=europe-west1
```

---

## Quick Deploy Commands

If you want to deploy right now without GitHub Actions:

```bash
# 1. Deploy Firebase
firebase deploy --only hosting,firestore --project powerful-layout-467812-p1

# 2. Deploy Cloud Run
gcloud builds submit --config cloudbuild.yaml \
  --project=powerful-layout-467812-p1 \
  --region=europe-west1

# 3. Set environment variables (with your real values!)
gcloud run services update svg2ooxml-export \
  --region=europe-west1 \
  --set-env-vars="ENVIRONMENT=production,STRIPE_SECRET_KEY=sk_test_..."

# 4. Test
curl https://svg2ooxml-export-sghya3t5ya-ew.a.run.app/health
```

---

## Once GitHub Actions is Set Up

After you complete Steps 1-2 above, every push to `main` will automatically:
1. ✅ Run tests
2. ✅ Deploy Firebase
3. ✅ Deploy Cloud Run
4. ✅ Run health checks

---

## Priority Order

1. **NOW**: Deploy manually (Steps 3-7 above) to test everything
2. **Later**: Set up GitHub Actions (Steps 1-2) for automated deployments

---

## Get Help

- **Quick Deploy**: `docs/DEPLOY_NOW.md`
- **GitHub Setup**: `docs/GITHUB_DEPLOYMENT_SETUP.md`
- **Stripe Setup**: `docs/STRIPE_CLI_GUIDE.md`
- **Full Checklist**: `docs/FINAL_DEPLOYMENT_CHECKLIST.md`

---

## 🚀 You're Almost There!

Everything is ready. Just need to:
1. Run Stripe setup
2. Deploy manually once
3. Test the payment flow
4. Launch! 🎉

**Let's deploy!**
