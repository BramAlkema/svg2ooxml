# Figma Plugin UI Redesign V2 - Specification

## Executive Summary

Based on research of successful Figma plugins (Pitchdeck, Sync to Slides) and Figma plugin design best practices (2024-2025), this spec outlines a complete UI redesign focused on:

1. **Professional deck export workflow** - Multi-frame selection with preview
2. **Fidelity controls** - Fine-tuned export options for maximum quality
3. **Better feedback** - Real-time preview, progress tracking, console logging
4. **Improved organization** - Collapsible sections, tabs, clear visual hierarchy

## Research Findings

### Key Insights from Successful Plugins

**Pitchdeck Presentation Studio** (most popular Figma→Slides plugin):
- Treats top-level frames as slides
- Offers "Use Editable Text" option for text fidelity
- Clear export workflow: select frames → preview → export
- Supports PowerPoint, Keynote, and Google Slides

**Best Practices** (from research):
- **Integration**: Plugin should feel like an extension of Figma, not a separate app
- **Output Quality**: Reduce workload, not increase it - generate usable assets
- **Context-Aware**: Actions should be instant and context-aware
- **Scalability**: Support shared libraries, permissions, consistent outputs

### Current UI Problems

1. **No frame preview** - Can't see what will be exported
2. **Limited export options** - One-size-fits-all approach
3. **Poor feedback** - Generic "processing" messages
4. **Debug clutter** - Development logging in production UI
5. **Hidden features** - Developer settings buried at bottom
6. **No deck concept** - Treats individual frames, not presentations

## Proposed UI Architecture

### Tab-Based Layout

```
┌─────────────────────────────────────────┐
│  svg2ooxml                              │
│  ┌─────┬─────┬─────────┬────────┐      │
│  │ 🖼  │ ⚙️  │ 📊      │ 🔧     │      │
│  │Deck │Opts │Progress │Console│      │
│  └─────┴─────┴─────────┴────────┘      │
│                                         │
│  [TAB CONTENT AREA]                    │
│                                         │
│                                         │
│  ─────────────────────────────────      │
│  👤 user@example.com        [Sign Out] │
│  📦 Pro Plan - ∞ exports               │
└─────────────────────────────────────────┘
```

## Tab 1: Deck View (Primary)

**Purpose**: Visual deck builder with frame preview and ordering

### Layout

```
┌─────────────────────────────────────────┐
│ 📊 Presentation Preview                 │
│ ─────────────────────────────────────   │
│                                         │
│ ┌─────────────────────────────────────┐│
│ │ 📄 Untitled Presentation           │ │
│ │ [Edit Title]                       │ │
│ └─────────────────────────────────────┘│
│                                         │
│ Selected Frames (3)                     │
│ ┌───────┬───────┬───────┐              │
│ │ ╔═══╗ │ ╔═══╗ │ ╔═══╗ │              │
│ │ ║ 1 ║ │ ║ 2 ║ │ ║ 3 ║ │              │
│ │ ╚═══╝ │ ╚═══╝ │ ╚═══╝ │              │
│ │ Cover │ Agenda│ ...  │              │
│ │  [x]  │  [x]  │  [x]  │              │
│ └───────┴───────┴───────┘              │
│                                         │
│ ┌─────────────────────────────────────┐│
│ │ 📋 Instructions                    │ │
│ │ Select frames in Figma, then click │ │
│ │ "Refresh Selection" to preview.    │ │
│ └─────────────────────────────────────┘│
│                                         │
│ [🔄 Refresh Selection]                 │
│                                         │
│ [🚀 Export to Google Slides]           │
│                                         │
└─────────────────────────────────────────┘
```

### Features

1. **Presentation Title**
   - Editable input field at top
   - Auto-fills from Figma file name
   - Persists across sessions

2. **Frame Preview Grid**
   - Thumbnail previews of selected frames
   - Show frame names
   - Checkbox to include/exclude frames
   - Drag to reorder (if time permits)
   - Visual indicators: slide numbers, dimensions

3. **Selection Management**
   - "Refresh Selection" button to sync with Figma
   - Auto-refresh on selection change (optional setting)
   - Frame count badge

4. **Smart Instructions**
   - Context-aware help text
   - Changes based on state (no selection, ready to export, etc.)

## Tab 2: Options (Export Settings)

**Purpose**: Fine-tuned control over export fidelity and behavior

### Layout

```
┌─────────────────────────────────────────┐
│ ⚙️ Export Options                       │
│ ─────────────────────────────────────   │
│                                         │
│ Text Handling                           │
│ ○ Editable Text (Recommended)          │
│   Keep text editable in Slides         │
│ ○ Rasterized Text                      │
│   Convert text to images (higher       │
│   fidelity, but not editable)          │
│                                         │
│ ─────────────────────────────────────   │
│                                         │
│ Vector Graphics                         │
│ ☑ Preserve vectors where possible      │
│ ☐ Convert all shapes to images         │
│                                         │
│ ─────────────────────────────────────   │
│                                         │
│ Slide Dimensions                        │
│ ○ Standard (16:9)                      │
│ ○ Widescreen (16:10)                   │
│ ○ Custom                               │
│   Width: [1920] Height: [1080]         │
│                                         │
│ ─────────────────────────────────────   │
│                                         │
│ Google Drive                            │
│ ☑ Create in My Drive                   │
│ ☐ Create in folder:                    │
│   [Select Folder...]                   │
│                                         │
│ ─────────────────────────────────────   │
│                                         │
│ [💾 Save Preferences]                   │
│ [🔄 Reset to Defaults]                  │
│                                         │
└─────────────────────────────────────────┘
```

### Features

1. **Text Handling Options**
   - Editable vs. Rasterized toggle
   - Clear explanation of trade-offs
   - Visual examples (tooltip/modal)

2. **Vector Preservation**
   - Option to convert complex shapes to images for better fidelity
   - Checkbox for each export optimization

3. **Slide Dimensions**
   - Preset aspect ratios (16:9, 16:10, 4:3)
   - Custom dimensions with validation
   - Auto-scale content toggle

4. **Google Drive Integration**
   - Folder picker (if API supports it)
   - Default destination
   - Permission handling

5. **Preference Persistence**
   - Save settings to Figma client storage
   - Export/import settings JSON
   - Per-file vs. global settings toggle

## Tab 3: Progress (Live Export Tracking)

**Purpose**: Detailed real-time progress with transparency and debugging

### Layout

```
┌─────────────────────────────────────────┐
│ 📊 Export Progress                      │
│ ─────────────────────────────────────   │
│                                         │
│ Current Job: 3a7b2e4c                   │
│ Started: 2025-11-08 19:12:03           │
│                                         │
│ ■■■■■■■■■■■■■■■░░░░░ 65%              │
│                                         │
│ Current Step:                           │
│ Publishing to Google Slides...          │
│                                         │
│ ─────────────────────────────────────   │
│                                         │
│ Timeline                                │
│ ✅ 19:12:03 - Export job created       │
│ ✅ 19:12:04 - Converted SVG to PPTX    │
│ ✅ 19:12:05 - Uploaded to storage      │
│ ⏳ 19:12:06 - Publishing to Slides...  │
│                                         │
│ ─────────────────────────────────────   │
│                                         │
│ Details                                 │
│ • Frames: 3                             │
│ • Format: Google Slides                 │
│ • Size: 1.2 MB                          │
│ • Elapsed: 0:12                         │
│                                         │
│ [❌ Cancel Export]                      │
│                                         │
└─────────────────────────────────────────┘
```

### Features

1. **Visual Progress Bar**
   - Animated progress indicator
   - Percentage display
   - Estimated time remaining

2. **Step-by-Step Timeline**
   - Checkmark for completed steps
   - Current step highlighted
   - Timestamp for each step
   - Error markers for failed steps

3. **Job Metadata**
   - Unique job ID (for support/debugging)
   - Start time, elapsed time
   - Frame count, file size
   - Output format

4. **Cancel Control**
   - Graceful cancellation
   - Cleanup confirmation
   - Partial results handling

5. **Success State**
   - Large success message
   - Direct link to open Slides
   - Share/copy link buttons
   - Thumbnail preview of first slide

## Tab 4: Console (Developer/Power User)

**Purpose**: Advanced debugging and API inspection

### Layout

```
┌─────────────────────────────────────────┐
│ 🔧 Developer Console                    │
│ ─────────────────────────────────────   │
│                                         │
│ Logs [Clear] [Copy] [Download]         │
│ ┌─────────────────────────────────────┐│
│ │[19:12:03] 🟢 Plugin initialized    │ │
│ │[19:12:05] 🔵 OAuth token refreshed │ │
│ │[19:12:06] 🟢 Export started        │ │
│ │[19:12:07] 🟡 Uploading PPTX...     │ │
│ │[19:12:08] 🔵 API Response 202      │ │
│ │                                     │ │
│ │                                     │ │
│ │                                     │ │
│ └─────────────────────────────────────┘│
│                                         │
│ API Configuration                       │
│ API URL:                                │
│ [https://svg2ooxml-export-...]         │
│                                         │
│ Auth URL:                               │
│ [https://powerful-layout-467812...]    │
│                                         │
│ ☑ Enable verbose logging               │
│ ☑ Log API requests/responses           │
│ ☐ Disable analytics                    │
│                                         │
│ [Apply] [Reset] [Test Connection]      │
│                                         │
│ Session Info                            │
│ • User ID: RxBg7fFhzA...               │
│ • Token: eyJhbGciOiJSU...             │
│ • Token Expires: 2025-11-09 20:12     │
│                                         │
└─────────────────────────────────────────┘
```

### Features

1. **Log Viewer**
   - Color-coded log levels (info, warn, error)
   - Timestamps
   - Auto-scroll to bottom
   - Search/filter
   - Copy/download logs

2. **Environment Overrides**
   - Custom API URL (for local testing)
   - Custom Auth URL
   - Persist overrides in storage

3. **Debug Flags**
   - Verbose logging toggle
   - API request/response logging
   - Performance metrics
   - Disable analytics/telemetry

4. **Session Inspector**
   - Current auth token (masked)
   - Token expiration
   - Refresh token status
   - User ID
   - Subscription tier

5. **Quick Actions**
   - Test API connectivity
   - Force token refresh
   - Clear cache
   - Reset to production settings

## Footer (Always Visible)

**Purpose**: Persistent auth status and quick actions

```
┌─────────────────────────────────────────┐
│  ─────────────────────────────────────  │
│  👤 user@example.com        [Sign Out]  │
│  📦 Pro Plan - ∞ exports    [Manage]   │
└─────────────────────────────────────────┘
```

### Features

1. **User Info Badge**
   - Email
   - Avatar (if available)
   - Sign out button

2. **Subscription Badge**
   - Current tier with icon
   - Usage bar for limited tiers
   - Quick upgrade/manage link

3. **Status Indicator**
   - Connection status (online/offline)
   - API health indicator

## Visual Design System

### Colors

**From Figma Design Tokens (2024-2025)**:
- Use Figma CSS variables:
  - `--figma-color-bg`
  - `--figma-color-bg-secondary`
  - `--figma-color-text`
  - `--figma-color-text-secondary`
  - `--figma-color-border`

**Brand Colors**:
- Primary: `#18A0FB` (Figma blue)
- Success: `#0ACF83` (green)
- Warning: `#FFA726` (orange)
- Danger: `#EF5350` (red)

**Tier Colors**:
- Free: `#E0E0E0` (gray)
- Pro: `linear-gradient(135deg, #667eea 0%, #764ba2 100%)` (purple)
- Enterprise: `linear-gradient(135deg, #f093fb 0%, #f5576c 100%)` (pink)

### Typography

- **Font Family**: Inter (matches Figma UI)
- **Sizes**:
  - Large header: 18px/bold
  - Header: 16px/600
  - Body: 14px/regular
  - Small: 12px/regular
  - Tiny: 11px/regular

### Spacing

- Base unit: 4px
- Common spacing:
  - xs: 4px
  - sm: 8px
  - md: 12px
  - lg: 16px
  - xl: 24px

### Components

**Button Styles**:
```css
.button-primary {
  background: #18A0FB;
  color: white;
  border-radius: 6px;
  padding: 10px 16px;
  font-weight: 500;
  transition: all 0.15s;
}

.button-secondary {
  background: transparent;
  color: var(--figma-color-text);
  border: 1px solid var(--figma-color-border);
  border-radius: 6px;
  padding: 10px 16px;
}

.button-icon {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
```

**Card Style**:
```css
.card {
  background: var(--figma-color-bg-secondary);
  border-radius: 8px;
  padding: 16px;
  border: 1px solid var(--figma-color-border);
}
```

## Interaction Patterns

### Auto-Refresh Selection

**Behavior**: When user selects/deselects frames in Figma:
1. Debounce for 300ms
2. Show "Selection changed" indicator
3. Auto-refresh preview (if setting enabled)
4. Otherwise, show "Refresh Selection" button with badge

### Export Flow

```
User Action           Plugin State            UI Feedback
─────────────────────────────────────────────────────────
Select frames    →    frames_selected    →   Preview grid updated
Click "Export"   →    validating         →   "Checking selection..."
                 →    creating_job       →   "Creating export job..."
                 →    processing         →   Progress bar + timeline
                 →    completed          →   Success message + link
```

### Error Handling

**OAuth Required**:
- Show friendly "Connect Google Drive" card
- Inline button to start OAuth flow
- "Retry Export" button after connection
- Don't lose frame selection

**Quota Exceeded**:
- Show usage bar at 100%
- Highlight upgrade button
- Explain limits clearly
- Link to pricing page

**API Error**:
- Show error message with job ID
- Offer "Copy Debug Info" button
- Link to support/help
- Suggest retry or contacting support

## Implementation Plan

### Phase 1: Foundation (Week 1)
- [ ] Create tab navigation system
- [ ] Build reusable card/button components
- [ ] Implement state management (current tab, selection, etc.)
- [ ] Add Figma selection listener

### Phase 2: Deck View (Week 1-2)
- [ ] Frame preview grid
- [ ] Thumbnail generation
- [ ] Selection management
- [ ] Presentation title editor
- [ ] Include/exclude checkboxes

### Phase 3: Options Tab (Week 2)
- [ ] Text handling options
- [ ] Vector preservation settings
- [ ] Slide dimension controls
- [ ] Preference persistence

### Phase 4: Progress Tab (Week 2-3)
- [ ] Real-time progress bar
- [ ] Timeline component
- [ ] Job metadata display
- [ ] Cancel functionality
- [ ] Success state with link

### Phase 5: Console Tab (Week 3)
- [ ] Log viewer component
- [ ] Environment overrides
- [ ] Debug flags
- [ ] Session inspector
- [ ] Quick action buttons

### Phase 6: Polish (Week 3-4)
- [ ] Animations and transitions
- [ ] Loading states
- [ ] Empty states
- [ ] Error state designs
- [ ] Responsive layout
- [ ] Dark mode support (uses Figma tokens)

## Success Metrics

1. **User Experience**
   - Time to first export: < 30 seconds
   - Export success rate: > 95%
   - User satisfaction: 4.5+ stars

2. **Technical**
   - No console errors in production
   - < 100ms UI response time
   - Proper error recovery

3. **Business**
   - Conversion to Pro: 10%+ of free users
   - Retention: 80%+ monthly active users
   - Support tickets: < 5% of exports

## Open Questions

1. **Frame Reordering**: Implement drag-and-drop or use Figma layer order?
2. **Folder Picker**: Does Google Drive API support folder selection in OAuth flow?
3. **Thumbnail Generation**: Client-side canvas rendering or request from Figma?
4. **Auto-refresh**: On by default or opt-in?
5. **Persistent Deck**: Save deck configurations per Figma file?

## References

- [Figma Plugin API - clientStorage](https://www.figma.com/plugin-docs/api/figma-clientStorage/)
- [Figma Design Tokens (Variables)](https://www.figma.com/best-practices/design-systems-variables/)
- [Pitchdeck Plugin](https://www.hypermatic.com/tutorials/how-to-export-presentations-from-figma-to-google-slides-using-pitchdeck/)
- [Figma Plugin Best Practices](https://www.figma.com/plugin-docs/best-practices/)
