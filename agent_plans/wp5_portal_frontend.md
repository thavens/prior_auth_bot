# WP5: Insurer Portal Frontend

**Depends on:** WP4 (backend API endpoints must exist)

## Theme Reference

Match the existing physician portal dark theme:
- Background: `pi-bg` (#0e0e0e)
- Cards: `.pi-card` (glass-morphism, rgba(255,255,255,0.02) bg)
- Text: `pi-text` (#ffffff), `pi-muted` (rgba(255,255,255,0.50))
- Green: `pi-green` (#55cc58) - for approved/success
- Red: `pi-red` (#c52626) - for rejected/error
- Blue: `pi-blue` (#3e77f1) - for processing/info
- Buttons: `.pi-btn-primary` (white CTA), `.pi-btn-secondary` (transparent bordered)
- Headings: `.pi-heading` (monospace, JetBrains Mono)
- Inputs: `.pi-input` (styled input fields)
- Labels: `.pi-label` (uppercase, letter-spacing)
- Badges: `.pi-badge` (status badges)
- Fonts: Inter (sans), JetBrains Mono (mono)
- Nav: `.pi-nav` (sticky, backdrop blur)

## Modified Files

### 1. `frontend/src/api/client.ts`

Add three new API client functions:
```typescript
export const getInsurerQueue = () =>
  api.get('/insurer/queue').then(r => r.data.results);

export const getInsurerPARequest = (id: string) =>
  api.get(`/insurer/pa-requests/${id}`).then(r => r.data);

export const submitInsurerDecision = (id: string, decision: { decision: string; rejection_reasons?: string[]; feedback?: string }) =>
  api.post(`/insurer/pa-requests/${id}/decide`, decision).then(r => r.data);
```

### 2. `frontend/src/App.tsx`

Add imports and routes:
```tsx
import InsurerDashboard from './pages/InsurerDashboard';
import InsurerReviewPage from './pages/InsurerReviewPage';

// Inside <Routes>:
<Route path="/insurer" element={<InsurerDashboard />} />
<Route path="/insurer/review/:paRequestId" element={<InsurerReviewPage />} />
```

### 3. `frontend/src/pages/PhysicianDashboard.tsx`

Add nav link to Insurer Portal in the header/nav area:
```tsx
<Link to="/insurer" className="pi-btn-secondary text-sm">Insurer Portal</Link>
```

### 4. `frontend/src/pages/PipelineDashboard.tsx`

- Add nav link to Insurer Portal
- Add `pending_insurer_review` as a visible stage in the pipeline visualizer (or map it to an existing stage display)

## New Files

### 5. `frontend/src/pages/InsurerDashboard.tsx`

**Layout:** Same structure as PhysicianDashboard/PipelineDashboard
- Sticky nav with "Insurer Portal" title
- Navigation links: Physician Portal, Pipeline Dashboard
- Main content: Queue of pending PA requests

**Queue display:**
- Fetch from `getInsurerQueue()` on mount
- WebSocket connection for auto-refresh (same pattern as PipelineVisualizer)
- Display as list of `.pi-card` items showing:
  - pa_request_id (monospace)
  - Patient name + Physician name
  - Insurance provider + Treatment text
  - Attempt number (show badge if > 1: "Appeal #N")
  - Created date
  - Status badge
- Click navigates to `/insurer/review/{pa_request_id}`
- Empty state: "No pending requests" message

### 6. `frontend/src/pages/InsurerReviewPage.tsx`

**Layout:** Similar to PAVisualizerPage but with decision form

**Sections:**
1. **Header:** Back button to /insurer, PA request ID, status badge
2. **Patient/Physician info:** 2-column grid (reuse patterns from PAVisualizer)
   - Patient: name, DOB, insurance provider, insurance ID, address, phone
   - Physician: name, NPI, specialty, phone, fax
3. **Request details:** Created date, attempt number, attempt hash
4. **Treatments requiring PA:** List of treatments with categories
5. **Completed documents:** Links to PDF viewer (use existing /pa/:id/pdf/:hash/:doc route)
6. **Rejection history:** (only shown if attempt > 1) - expandable cards showing previous rejection reasons and proposed fixes
7. **Decision form:**
   - Two large buttons side by side:
     - "Approve" - pi-green border, on click calls API with `{decision: "approved"}`
     - "Reject" - pi-red border, on click expands rejection form
   - Rejection form (shown when Reject clicked):
     - Dynamic list of rejection reason inputs (add/remove)
     - "Add reason" button
     - Optional feedback textarea
     - "Submit Rejection" button
   - After submission: show confirmation message, auto-navigate back to /insurer after 2s

**State management:**
- `loading`, `error`, `paRequest` for data fetch
- `decision`: null | 'approve' | 'reject' for form state
- `rejectionReasons: string[]` for dynamic reason list
- `feedback: string` for optional notes
- `submitting: boolean` for submission state
- `submitted: boolean` for confirmation display

## Verify
```bash
cd frontend && npm run build
# Navigate to /insurer - see queue (empty or populated)
# Run a pipeline to pending_insurer_review
# Refresh /insurer - see the request
# Click into review page - see all details
# Approve - verify status change
# Reject with reasons - verify appeal triggers and new request appears
```

## What NOT to touch
- Do not modify backend Python files (those are other WPs)
- Do not modify existing components (PAVisualizer, PipelineVisualizer, etc.) - create new pages
- Reuse the existing `.pi-*` CSS classes and Tailwind theme, do NOT add new theme values
