# Quick Start: Staging Environment

## Your Monthly Workflow

### Development (Week 1-3)

```bash
# 1. Start working on new feature
git checkout develop
git pull origin develop
git checkout -b feature/my-new-feature

# 2. Make changes, test locally
source .venv/bin/activate
python -m pytest
uvicorn main:app --reload

# 3. Push to develop when ready
git checkout develop
git merge feature/my-new-feature
git push origin develop
```

**Result:** GitHub Actions automatically deploys to staging 🚀

### Testing (Week 3-4)

1. Go to: https://github.com/BramAlkema/svg2ooxml/actions
2. Find latest "Deploy Staging" workflow run
3. Copy staging URL from workflow output
4. Test with Stripe test card: `4242 4242 4242 4242`
5. Share with beta testers

### Production Release (Week 4)

```bash
# 1. Merge to production
git checkout main
git pull origin main
git merge develop
git push origin main
```

**Result:** GitHub Actions automatically deploys to production 🎉

### Cleanup (Optional)

```bash
# Delete staging to save costs
gcloud run services delete svg2ooxml-export-staging \
  --region=europe-west1 \
  --project=powerful-layout-467812-p1
```

---

## Quick Commands

### Deploy Staging Manually
```bash
gcloud builds submit \
  --config cloudbuild-staging.yaml \
  --project=powerful-layout-467812-p1 \
  --region=europe-west1
```

### Get Staging URL
```bash
gcloud run services describe svg2ooxml-export-staging \
  --region=europe-west1 \
  --format='value(status.url)'
```

### Create Firebase Preview
```bash
firebase hosting:channel:deploy staging --expires 30d
```

### Check Staging Health
```bash
curl https://YOUR-STAGING-URL/health
```

---

## Stripe Test Cards

**Success:** `4242 4242 4242 4242`
**Requires Auth:** `4000 0025 0000 3155`
**Declined:** `4000 0000 0000 9995`

More: https://stripe.com/docs/testing

---

## Cost Estimate

- **When deployed:** ~$0-5/month
- **When deleted:** $0/month

💡 **Tip:** Delete staging after testing to minimize costs!

---

## Need Help?

Full documentation: [STAGING_DEPLOYMENT.md](./STAGING_DEPLOYMENT.md)
