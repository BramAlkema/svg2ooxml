# Figma Plugin UI Redesign V2 - Implementation Tasks

**Spec**: Historical app plan; no standalone plugin UI spec has been restored yet.

## Overview

Redesign the Figma plugin UI with a professional, tab-based interface for exporting presentation decks to Google Slides with maximum fidelity.

**Timeline**: 4 weeks
**Priority**: High
**Dependencies**: Current plugin UI (apps/figma2gslides/figma-plugin/ui.html, ui.js)

---

## Phase 1: Foundation & Core Components (Week 1)

### 1.1 Project Setup & Architecture

- [ ] Create new UI architecture plan
  - [ ] Define state management approach (vanilla JS or lightweight framework)
  - [ ] Plan component structure and reusability
  - [ ] Set up CSS organization (BEM, utility classes, or CSS modules)

- [ ] Create component library foundation
  - [ ] Set up CSS variables from Figma design tokens
  - [ ] Create base styles (reset, typography, spacing)
  - [ ] Build reusable button component variants
  - [ ] Build card/panel component
  - [ ] Build form input components

- [ ] Build tab navigation system
  - [ ] Create tab bar component with icons
  - [ ] Implement tab switching logic
  - [ ] Add active tab indicator
  - [ ] Handle keyboard navigation (Arrow keys, Tab)
  - [ ] Save active tab to clientStorage

### 1.2 State Management

- [ ] Design global state structure
  - [ ] User authentication state
  - [ ] Selected frames data
  - [ ] Export options/preferences
  - [ ] Active tab
  - [ ] Export progress state

- [ ] Implement state persistence
  - [ ] Save/restore from Figma clientStorage
  - [ ] Handle state hydration on plugin load
  - [ ] Implement state change listeners

### 1.3 Figma Integration

- [ ] Set up Figma selection listener
  - [ ] Listen to selectionchange events
  - [ ] Debounce selection changes (300ms)
  - [ ] Extract frame data (name, dimensions, svg content)
  - [ ] Update UI when selection changes

- [ ] Implement thumbnail generation
  - [ ] Export frame thumbnails from Figma
  - [ ] Cache thumbnails for performance
  - [ ] Handle thumbnail loading states

---

## Phase 2: Deck View Tab (Week 1-2)

### 2.1 Presentation Header

- [ ] Build presentation title editor
  - [ ] Editable input field
  - [ ] Auto-fill from Figma file name
  - [ ] Save title to clientStorage
  - [ ] Validate title (max length, special chars)

### 2.2 Frame Preview Grid

- [ ] Build frame card component
  - [ ] Thumbnail image display
  - [ ] Frame name label
  - [ ] Dimensions badge
  - [ ] Slide number indicator
  - [ ] Include/exclude checkbox

- [ ] Implement preview grid layout
  - [ ] Responsive grid (2-3 columns based on width)
  - [ ] Loading skeleton states
  - [ ] Empty state (no frames selected)
  - [ ] Hover effects and interactions

- [ ] Add frame management features
  - [ ] "Refresh Selection" button
  - [ ] Frame count badge
  - [ ] "Select All" / "Deselect All" buttons
  - [ ] Clear selection button

### 2.3 Instructions & Help

- [ ] Create smart instruction component
  - [ ] Context-aware help text
  - [ ] Change based on state (no selection, ready, etc.)
  - [ ] Collapsible tips section

### 2.4 Export Button

- [ ] Build primary export button
  - [ ] Disabled state when no frames selected
  - [ ] Loading state during export
  - [ ] Tooltip with frame count
  - [ ] Keyboard shortcut (Cmd+Enter)

---

## Phase 3: Options Tab (Week 2)

### 3.1 Text Handling Options

- [ ] Build radio button group for text options
  - [ ] Editable Text (default)
  - [ ] Rasterized Text
  - [ ] Explanatory descriptions
  - [ ] Visual example tooltip/modal

### 3.2 Vector Graphics Options

- [ ] Build vector preservation controls
  - [ ] "Preserve vectors" checkbox
  - [ ] "Convert all to images" checkbox
  - [ ] Explanation of trade-offs

### 3.3 Slide Dimensions

- [ ] Build dimension selector
  - [ ] Preset ratio buttons (16:9, 16:10, 4:3)
  - [ ] Custom dimensions input
  - [ ] Width/height inputs with validation
  - [ ] Preview aspect ratio indicator

### 3.4 Google Drive Integration

- [ ] Build Drive destination selector
  - [ ] "My Drive" default option
  - [ ] "Select Folder" button (if API supports)
  - [ ] Show selected folder path

### 3.5 Preference Management

- [ ] Implement preference persistence
  - [ ] Save preferences to clientStorage
  - [ ] "Save Preferences" button
  - [ ] "Reset to Defaults" button
  - [ ] Per-file vs. global settings toggle
  - [ ] Export/import settings JSON

---

## Phase 4: Progress Tab (Week 2-3)

### 4.1 Progress Bar Component

- [ ] Build animated progress bar
  - [ ] Percentage display
  - [ ] Smooth transitions
  - [ ] Color coding (info, warning, success, error)
  - [ ] Estimated time remaining

### 4.2 Timeline Component

- [ ] Build step timeline
  - [ ] Checkmark for completed steps
  - [ ] Current step highlight
  - [ ] Timestamp for each step
  - [ ] Error indicators for failed steps
  - [ ] Auto-scroll to current step

### 4.3 Job Metadata Display

- [ ] Show job information
  - [ ] Unique job ID (copyable)
  - [ ] Start time
  - [ ] Elapsed time (live update)
  - [ ] Frame count
  - [ ] File size
  - [ ] Output format

### 4.4 Export Control

- [ ] Build cancel button
  - [ ] Confirmation modal
  - [ ] Graceful cancellation API call
  - [ ] Cleanup UI state
  - [ ] Handle partial results

### 4.5 Success State

- [ ] Build success view
  - [ ] Large success message
  - [ ] Direct "Open in Slides" link
  - [ ] Copy link button
  - [ ] Share button
  - [ ] Thumbnail preview of first slide (if available)
  - [ ] "Export Another" button

---

## Phase 5: Console Tab (Week 3)

### 5.1 Log Viewer

- [ ] Build scrollable log container
  - [ ] Color-coded log levels (info, warn, error, debug)
  - [ ] Timestamp for each entry
  - [ ] Auto-scroll to bottom
  - [ ] Search/filter functionality
  - [ ] "Clear Logs" button

- [ ] Add log export features
  - [ ] "Copy Logs" button
  - [ ] "Download Logs" button (as .txt file)
  - [ ] Select and copy specific log lines

### 5.2 Environment Overrides

- [ ] Build API configuration inputs
  - [ ] API URL override input
  - [ ] Auth URL override input
  - [ ] Validation for URLs
  - [ ] "Test Connection" button
  - [ ] Connection status indicator

- [ ] Implement override persistence
  - [ ] Save overrides to clientStorage
  - [ ] "Apply" button
  - [ ] "Reset to Production" button
  - [ ] Warning when overrides are active

### 5.3 Debug Flags

- [ ] Build debug flag checkboxes
  - [ ] "Enable verbose logging"
  - [ ] "Log API requests/responses"
  - [ ] "Disable analytics"
  - [ ] "Show performance metrics"
  - [ ] Persist flags to clientStorage

### 5.4 Session Inspector

- [ ] Display session information
  - [ ] User ID (copyable, masked)
  - [ ] Current token (masked, copyable)
  - [ ] Token expiration time
  - [ ] Refresh token status
  - [ ] Subscription tier
  - [ ] OAuth connection status

### 5.5 Quick Actions

- [ ] Build action buttons
  - [ ] "Force Token Refresh" button
  - [ ] "Clear Cache" button
  - [ ] "Test API" button
  - [ ] "Revoke OAuth" button (with confirmation)

---

## Phase 6: Footer & Persistent UI (Week 3)

### 6.1 User Info Footer

- [ ] Build always-visible footer
  - [ ] User email display
  - [ ] Avatar image (if available)
  - [ ] Sign out button
  - [ ] Subscription badge
  - [ ] Usage bar for limited tiers

### 6.2 Connection Status

- [ ] Add status indicators
  - [ ] Online/offline badge
  - [ ] API health indicator
  - [ ] Last sync time

---

## Phase 7: Polish & Enhancement (Week 3-4)

### 7.1 Animations & Transitions

- [ ] Add smooth transitions
  - [ ] Tab switching fade/slide
  - [ ] Progress bar animations
  - [ ] Loading spinners
  - [ ] Success/error state animations
  - [ ] Hover effects

### 7.2 Loading States

- [ ] Design and implement loading states
  - [ ] Skeleton loaders for frames
  - [ ] Shimmer effects
  - [ ] Loading spinners where appropriate
  - [ ] Progress indicators

### 7.3 Empty States

- [ ] Create empty state designs
  - [ ] No frames selected
  - [ ] No export history
  - [ ] No logs
  - [ ] First-time user onboarding

### 7.4 Error States

- [ ] Design error UI
  - [ ] Inline error messages
  - [ ] Toast notifications
  - [ ] Error recovery actions
  - [ ] Helpful error messages

### 7.5 Responsive Layout

- [ ] Ensure responsive design
  - [ ] Test at different plugin sizes
  - [ ] Adjust grid columns for narrow widths
  - [ ] Collapsible sections for mobile
  - [ ] Touch-friendly tap targets

### 7.6 Dark Mode

- [ ] Implement dark mode support
  - [ ] Use Figma CSS variables
  - [ ] Test all components in dark mode
  - [ ] Ensure contrast ratios meet accessibility standards

### 7.7 Accessibility

- [ ] Ensure accessibility
  - [ ] Keyboard navigation for all features
  - [ ] ARIA labels where needed
  - [ ] Focus indicators
  - [ ] Screen reader testing
  - [ ] Color contrast validation

---

## Phase 8: Testing & Documentation (Week 4)

### 8.1 Testing

- [ ] Manual testing
  - [ ] Test all user flows
  - [ ] Test error scenarios
  - [ ] Test with different selections
  - [ ] Test on different Figma platforms (Mac, Windows, Web)
  - [ ] Test with various network conditions

- [ ] Performance testing
  - [ ] Test with large frame selections (50+ frames)
  - [ ] Measure UI responsiveness
  - [ ] Optimize thumbnail loading
  - [ ] Check memory usage

- [ ] Cross-browser testing
  - [ ] Chrome
  - [ ] Safari
  - [ ] Firefox
  - [ ] Edge

### 8.2 Documentation

- [ ] Update README with new UI features
- [ ] Create user guide with screenshots
- [ ] Document keyboard shortcuts
- [ ] Create developer documentation for future updates
- [ ] Add inline code comments
- [ ] Create changelog entry

### 8.3 Migration

- [ ] Create migration plan from old UI
  - [ ] Migrate user preferences
  - [ ] Handle session data
  - [ ] Backward compatibility if needed

- [ ] Beta testing
  - [ ] Deploy to beta channel
  - [ ] Gather user feedback
  - [ ] Iterate based on feedback

---

## Phase 9: Launch (Week 4)

### 9.1 Pre-Launch

- [ ] Final QA pass
- [ ] Performance audit
- [ ] Security review
- [ ] Update plugin manifest version
- [ ] Prepare release notes

### 9.2 Deployment

- [ ] Deploy to Figma plugin store
- [ ] Update plugin listing with new screenshots
- [ ] Update description with new features
- [ ] Monitor for errors/crashes
- [ ] Set up user feedback channel

### 9.3 Post-Launch

- [ ] Monitor user adoption metrics
- [ ] Track conversion rates (free to pro)
- [ ] Gather user feedback
- [ ] Plan iteration roadmap
- [ ] Address critical bugs immediately

---

## Future Enhancements (Post-Launch)

- [ ] Drag-and-drop frame reordering
- [ ] Bulk edit frame properties
- [ ] Presentation templates
- [ ] Export to PowerPoint/Keynote (in addition to Slides)
- [ ] Collaboration features (shared decks)
- [ ] Version history for decks
- [ ] Animation/transition support
- [ ] Speaker notes export
- [ ] Batch export multiple files
- [ ] CLI for automated exports

---

## Success Criteria

- [ ] Time to first export: < 30 seconds
- [ ] Export success rate: > 95%
- [ ] Zero console errors in production
- [ ] UI response time: < 100ms for all interactions
- [ ] Passes all accessibility audits
- [ ] Dark mode fully supported
- [ ] Works on all Figma platforms (Mac, Windows, Web)
- [ ] Positive user feedback (4.5+ stars)
- [ ] Pro conversion rate: 10%+ of free users

---

## Notes

- Prioritize Deck View and Progress tabs - these are the most user-facing
- Keep existing authentication flow intact
- Maintain backward compatibility with current export API
- Use Figma design tokens for seamless integration
- Follow Figma plugin best practices for performance
- Consider phased rollout (beta → gradual rollout → full release)
