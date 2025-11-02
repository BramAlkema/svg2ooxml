# Quick Start - Figma Plugin

Get your plugin running in **5 minutes**!

## Step 1: Load the Plugin (2 min)

1. Open **Figma Desktop app** (not browser version)
2. Go to **Plugins** → **Development** → **Import plugin from manifest...**
3. Navigate to `/Users/ynse/projects/svg2ooxml/figma-plugin/`
4. Select `manifest.json`
5. Click **Open**

✅ Plugin is now loaded!

## Step 2: Test Authentication (1 min)

1. Create a new Figma file or open existing one
2. Go to **Plugins** → **SVG to Google Slides**
3. Plugin window opens
4. Click **"Sign in with Google"**
5. Sign in with a Google account (must be added as test user)
6. You should see: "✓ Signed in as youremail@gmail.com"

✅ Authentication working!

## Step 3: Test Export (2 min)

1. Create a simple frame in Figma:
   - Press **F** to create frame
   - Add some text or shapes
   - Name it "Test Slide"

2. **Select the frame** (click on it)

3. In the plugin window, click **"Export Selected Frames"**

4. Watch the progress bar:
   - "Creating export job..."
   - "Processing: 50%"
   - "✅ Export complete! Open in Google Slides"

5. Click the link to view your presentation

✅ Export working!

---

## Common Issues

### "Figma Desktop app required"
- The plugin uses network features only available in Desktop app
- Download: https://www.figma.com/downloads/

### "Popup blocked" during sign-in
- Allow popups for Figma in your browser settings
- Try again

### "User not authorized"
- Your Google account must be added as a test user
- Contact admin to add you: https://console.firebase.google.com/project/powerful-layout-467812-p1/authentication/settings

### "Please select at least one frame"
- Make sure you've selected a **frame** (not just layers)
- Press **F** to create a frame if you don't have one

---

## Next Steps

- **Multiple Frames**: Select multiple frames and export them all at once
- **Complex Designs**: Try exporting frames with gradients, effects, and filters
- **Customize**: Edit `ui.html` or `ui.js` to customize the plugin UI

---

## Hot Reload for Development

When making changes to the plugin:

1. Edit files in `figma-plugin/`
2. In Figma: **Plugins** → **Development** → **SVG to Google Slides** → **⋮** → **Reload plugin**
3. Changes take effect immediately

No need to re-import!

---

## File Structure

```
figma-plugin/
├── manifest.json     ← Plugin config
├── code.js          ← Backend (SVG export)
├── ui.html          ← UI layout
├── ui.js            ← UI logic
├── README.md        ← Full documentation
└── QUICKSTART.md    ← This file
```

---

## Testing Checklist

- [ ] Plugin loads without errors
- [ ] "Sign in with Google" button works
- [ ] Can sign in with Google account
- [ ] UI shows "✓ Signed in as youremail@gmail.com"
- [ ] Can create and select frames
- [ ] "Export Selected Frames" button is enabled
- [ ] Export shows progress bar
- [ ] Export completes with success message
- [ ] Link opens Google Slides presentation
- [ ] Presentation contains the exported frames

---

## Need Help?

- **Full Docs**: See `README.md` in this directory
- **Firebase Auth Guide**: `docs/guides/figma-plugin-firebase-auth.md`
- **Report Issues**: https://github.com/BramAlkema/svg2ooxml/issues

---

**Happy Exporting!** 🎨→📊
