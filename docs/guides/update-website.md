# Updating the Firebase Hosting Website

This guide shows you how to update the svg2ooxml website hosted on Firebase Hosting.

## Website Files

The website files are located in the `public/` directory:
- `public/index.html` - Homepage
- `public/privacy.html` - Privacy Policy
- `public/terms.html` - Terms of Service

## Method 1: Edit Files and Deploy (Recommended)

### Step 1: Edit the Website Files

Edit any files in the `public/` directory:

```bash
# Edit homepage
vim public/index.html

# Edit privacy policy
vim public/privacy.html

# Edit terms of service
vim public/terms.html
```

### Step 2: Deploy to Firebase Hosting

Deploy using Cloud Build:

```bash
gcloud builds submit \
  --config=cloudbuild-hosting.yaml \
  --region=europe-west1 \
  --project=powerful-layout-467812-p1 \
  .
```

The deployment takes about 30-60 seconds.

### Step 3: Verify Changes

Visit the website to see your changes:
- Homepage: https://powerful-layout-467812-p1.web.app
- Privacy: https://powerful-layout-467812-p1.web.app/privacy.html
- Terms: https://powerful-layout-467812-p1.web.app/terms.html

---

## Method 2: Commit and Deploy from Git

### Step 1: Edit and Commit

```bash
# Edit files
vim public/index.html

# Commit changes
git add public/
git commit -m "docs: Update website content"
git push origin main
```

### Step 2: Deploy

```bash
gcloud builds submit \
  --config=cloudbuild-hosting.yaml \
  --region=europe-west1 \
  --project=powerful-layout-467812-p1 \
  .
```

---

## Quick Deploy Script

For convenience, you can use this one-liner:

```bash
# Deploy current state
gcloud builds submit --config=cloudbuild-hosting.yaml --region=europe-west1 --project=powerful-layout-467812-p1 .
```

Or create an alias:

```bash
# Add to ~/.bashrc or ~/.zshrc
alias deploy-website='gcloud builds submit --config=cloudbuild-hosting.yaml --region=europe-west1 --project=powerful-layout-467812-p1 .'

# Usage
deploy-website
```

---

## Firebase Hosting Configuration

The hosting configuration is in `firebase.json`:

```json
{
  "hosting": {
    "public": "public",
    "ignore": [
      "firebase.json",
      "**/.*",
      "**/node_modules/**"
    ],
    "rewrites": [
      {
        "source": "**",
        "destination": "/index.html"
      }
    ]
  }
}
```

### Adding New Pages

1. Create a new HTML file in `public/` (e.g., `public/about.html`)
2. Deploy using the command above
3. Access at: https://powerful-layout-467812-p1.web.app/about.html

---

## Common Updates

### Update Privacy Policy

```bash
# Edit privacy policy
vim public/privacy.html

# Deploy
gcloud builds submit --config=cloudbuild-hosting.yaml --region=europe-west1 --project=powerful-layout-467812-p1 .
```

### Update Homepage Content

```bash
# Edit homepage
vim public/index.html

# Deploy
gcloud builds submit --config=cloudbuild-hosting.yaml --region=europe-west1 --project=powerful-layout-467812-p1 .
```

### Change Styling

All pages use inline CSS. To change the look:
1. Edit the `<style>` section in the `<head>` of each HTML file
2. Deploy changes

---

## Deployment Details

### What Happens During Deployment

1. Cloud Build uploads your source code
2. Firebase CLI docker image is pulled
3. Firebase CLI deploys the `public/` directory to Firebase Hosting
4. Changes are live within seconds

### IAM Requirements

The Cloud Build service account has been granted:
- `roles/firebase.admin` - Required for Firebase deployments

### Cost

Firebase Hosting is **free** for:
- 10 GB storage
- 360 MB/day bandwidth
- Custom domain support

Your website is well within these limits.

---

## Troubleshooting

### "Permission denied" error

Ensure Cloud Build service account has Firebase Admin role:

```bash
gcloud projects add-iam-policy-binding powerful-layout-467812-p1 \
  --member="serviceAccount:237932518206@cloudbuild.gserviceaccount.com" \
  --role="roles/firebase.admin"
```

### Changes not appearing

Firebase Hosting has CDN caching. Try:
1. Hard refresh: Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)
2. Clear browser cache
3. Wait 1-2 minutes for CDN propagation
4. Try incognito/private browsing mode

### File not found (404)

Check:
1. File exists in `public/` directory
2. File was included in deployment (not in `.gitignore`)
3. URL matches exact filename (case-sensitive)

---

## Alternative: Firebase CLI (Local)

If you want to deploy from your local machine with Firebase CLI:

```bash
# Install Firebase CLI (if not already installed)
brew install firebase-cli

# Login (one-time, requires browser)
firebase login

# Deploy
firebase deploy --only hosting --project=powerful-layout-467812-p1
```

**Note**: The Cloud Build method is recommended for CI/CD workflows and doesn't require interactive login.

---

## Website URLs

Your website is available at two URLs:
- **Primary**: https://powerful-layout-467812-p1.web.app
- **Alternative**: https://powerful-layout-467812-p1.firebaseapp.com

Both point to the same content.

---

## Next Steps

- See `public/index.html` for the homepage structure
- See `public/privacy.html` for the privacy policy
- See `public/terms.html` for the terms of service
- Customize styling by editing the `<style>` sections
- Add new pages by creating new HTML files in `public/`
