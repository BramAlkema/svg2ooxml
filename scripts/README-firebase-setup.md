# Firebase Authentication Setup

Quick guide to set up Firebase Authentication for svg2ooxml.

## Quick Start

```bash
# 1. Install Firebase CLI (choose one)
brew install firebase-cli              # macOS (Homebrew)
npm install -g firebase-tools          # npm (all platforms)

# 2. Run setup script
./scripts/setup-firebase-auth.sh

# 3. Follow prompts for 2 manual steps:
#    - Enable Google Sign-In provider
#    - Configure OAuth consent screen

# 4. Deploy
git add .
git commit -m "feat: Add Firebase Auth integration"
git push origin main
```

## What the Script Does

✅ **Automated**:
- Enables Firebase on your GCP project
- Enables required APIs (Firebase, Identity Toolkit, Secret Manager)
- Creates Firebase web app and saves config
- Creates Firebase service account key
- Creates Secret Manager secrets (`firebase-service-account`, `token-encryption-key`)
- Grants IAM permissions to Cloud Run service account
- Cleans up sensitive local files

⚠️ **Manual (2 steps)**:
- Enable Google Sign-In provider (Firebase Console)
- Configure OAuth consent screen (GCP Console)

The script will pause and show you exact links for these steps.

## Prerequisites

- **gcloud CLI**: Already installed ✅
- **Firebase CLI**: Install with `brew install firebase-cli`
- **Python 3**: Already installed ✅
- **GCP Project**: `svg2ooxml` ✅

## Installation Options

### macOS (Homebrew - Recommended)
```bash
brew install firebase-cli
```

### npm (All platforms)
```bash
npm install -g firebase-tools
```

### Verify Installation
```bash
firebase --version
# Should show: 13.x.x or higher
```

## What Gets Created

### Secrets in GCP Secret Manager
- `firebase-service-account` - Service account JSON key for Firebase Admin SDK
- `token-encryption-key` - 32-byte Fernet key for encrypting OAuth tokens

### Firebase Resources
- Web app: `svg2ooxml-web`
- Config file: `docs/setup/firebase-web-config.json`

### IAM Permissions
- `svg2ooxml-runner@svg2ooxml.iam.gserviceaccount.com` granted `roles/secretmanager.secretAccessor` on both secrets

## Troubleshooting

### "Firebase CLI not found"
```bash
# Install it first
brew install firebase-cli

# Verify
firebase --version
```

### "gcloud not authenticated"
```bash
gcloud auth login
gcloud config set project svg2ooxml
```

### "Permission denied"
```bash
# Make script executable
chmod +x scripts/setup-firebase-auth.sh
```

### "Firebase project not found"
Wait a few minutes after the script completes - Firebase initialization can take 2-5 minutes. Then try deploying.

## After Setup

1. **Deploy to Cloud Run**:
   ```bash
   git add .
   git commit -m "feat: Add Firebase Auth integration"
   git push origin main
   ```

2. **Test locally** (optional):
   ```bash
   # Get Firebase config
   cat docs/setup/firebase-web-config.json

   # Set environment variables
   export FIREBASE_PROJECT_ID=svg2ooxml
   export TOKEN_ENCRYPTION_KEY=$(gcloud secrets versions access latest --secret=token-encryption-key)

   # Run locally
   uvicorn main:app --port 8080
   ```

3. **Test authentication**:
   - See `docs/guides/figma-plugin-firebase-auth.md` for Figma plugin integration
   - See `docs/implementation-summary-firebase-auth.md` for testing guide

## Security Notes

- 🔒 Service account keys are **never committed** to git
- 🔒 Encryption keys are stored in **Secret Manager** (not environment variables)
- 🔒 OAuth tokens are **encrypted at rest** and **deleted after use**
- 🔒 The script will **prompt before deleting** local sensitive files

## Documentation

- **Full specification**: `docs/specs/firebase-auth-google-slides-export.md`
- **Implementation summary**: `docs/implementation-summary-firebase-auth.md`
- **Task breakdown**: `docs/tasks/firebase-auth-implementation-tasks.md`
- **Figma plugin guide**: `docs/guides/figma-plugin-firebase-auth.md`

## Support

If you encounter issues:
1. Check the script output for specific error messages
2. Review the manual setup steps in `docs/implementation-summary-firebase-auth.md`
3. Verify all prerequisites are installed and authenticated
