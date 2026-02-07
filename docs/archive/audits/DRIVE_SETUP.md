# Setting Up Google Drive Access for Service Account

## Why This Is Needed

The service account needs permission to create files in Google Drive to upload
Slides presentations. By default, service accounts can't access user Drive files.

## Solution: Shared Folder Approach

This allows the service account to upload to a specific folder in YOUR Drive.

## Steps

### 1. Create a Drive Folder

1. Go to https://drive.google.com
2. Click "New" → "Folder"
3. Name it: `svg2ooxml-exports`
4. Click "Create"

### 2. Get the Folder ID

1. Open the folder you just created
2. Look at the URL in your browser
3. Copy the ID from the URL (the part after `/folders/`)

   Example URL:
   ```
   https://drive.google.com/drive/folders/1a2b3c4d5e6f7g8h9i0j
                                          ^^^^^^^^^^^^^^^^^^^^
                                          This is the folder ID
   ```

### 3. Share the Folder with the Service Account

1. Right-click the folder → "Share"
2. In the "Add people" field, paste:
   ```
   svg2ooxml-runner@powerful-layout-467812-p1.iam.gserviceaccount.com
   ```
3. Click the dropdown and select "Editor"
4. Uncheck "Notify people" (service accounts don't read email)
5. Click "Share"

### 4. Configure Cloud Run

Run this command to set the folder ID in Cloud Run:

```bash
gcloud run services update svg2ooxml-export \
  --region=europe-west1 \
  --set-env-vars SLIDES_FOLDER_ID=YOUR_FOLDER_ID_HERE
```

Replace `YOUR_FOLDER_ID_HERE` with the ID you copied in step 2.

### 5. Test It

Create a new export with `output_format: "slides"`:

```bash
TOKEN=$(gcloud auth print-identity-token)

curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @/tmp/slides_payload.json \
  https://svg2ooxml-export-sghya3t5ya-ew.a.run.app/api/v1/export
```

The Slides file should appear in your `svg2ooxml-exports` folder!

## Verification

After setup, check that:
- ✅ Folder exists in your Drive
- ✅ Service account email shows as "Editor" in sharing settings
- ✅ SLIDES_FOLDER_ID env var is set in Cloud Run
- ✅ Export creates Slides in the folder

## Troubleshooting

**"Insufficient permissions" error:**
- Make sure the service account has "Editor" role (not "Viewer")
- Try removing and re-adding the permission

**"Folder not found" error:**
- Double-check the folder ID
- Make sure it's from the URL, not the folder name

**Files not appearing:**
- Check the folder in Drive
- Service account-created files will show "svg2ooxml Cloud Run Service" as owner

## Alternative: Domain-Wide Delegation

For Google Workspace customers, you can use domain-wide delegation instead:

1. Go to Google Admin Console → Security → API Controls
2. Manage Domain Wide Delegation
3. Add the service account with these scopes:
   - https://www.googleapis.com/auth/drive.file
   - https://www.googleapis.com/auth/presentations
4. Update the code to use delegated credentials

This allows the service account to act on behalf of any user in your domain.

## Alternative: User OAuth (Production)

The Figma plugin uses Firebase Auth + OAuth, which is the recommended production approach:
- Users authenticate with their own Google account
- Files are created in their Drive
- No service account setup needed
- Works for all users
