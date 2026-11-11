# Interactive Plot Planner — implementation result

## Status

The React/TypeScript browser interface is implemented as a planning and visualization client. Python remains the scientific/API application. The included TypeScript mock server serves synthetic fixtures only; it is not the Farm Digital Twin scientific engine or optimizer.

## Commands run

From `frontend/`:

```powershell
pnpm install
pnpm exec playwright install chromium webkit
pnpm build
pnpm test
pnpm test:e2e
```

`pnpm build` passed with strict TypeScript checks. `pnpm test` passed **27 tests** (17 geometry, 10 explanation). Playwright passed **18 browser runs** across desktop 1280×800 and touch-emulated mobile 390×844 (9 scenarios per viewport). Axe reported zero serious or critical violations on both viewports.

## Screenshots

Saved under `frontend/artifacts/screens/`:

- `planner-desktop.png`, `planner-mobile.png`
- `result-picture-desktop.png`, `result-picture-mobile.png`
- `result-explanation-desktop.png`, `result-explanation-mobile.png`

The browser checks cover initial render, fixture plan from the mock API, visible crop labels, plain-language explanation, plot switching, zone locking, plan export, geometry-only number disclosures, reset, a deep-linkable demo result, and axe accessibility.

## Implemented

- Responsive React 19 and TypeScript UI with plot overview, editor, evidence indicators, explanation, number, comparison, and next-step panels.
- SVG plot rendering for rectangle, concave L-shaped, and irregular polygon examples with one shared plot-local coordinate system per edit view.
- Polygon clipping, area partitioning, paint/erase, crop-zone painting, zone-level locking, undo/redo, drip row layout, and area-based labels.
- API adapter call for `POST /api/v1/optimize`; a Python-free synthetic mock is included for front-end development. The app displays a disclosure on all fixture results and never presents fixture economics as real.
- Deterministic English explanation functions and number/units formatting; basic Hindi crop-name rendering can be supplied through crop metadata.
- Plan JSON export.

## Known gaps and deviations from the supplied front-end prompt

- This is a usable first interface iteration, not completion of every §7 and §11 acceptance item. The supplied prompt calls for 14 end-to-end scenarios; the implemented suite has 9 scenarios per viewport (18 runs). Plot onboarding/drawing, GeoJSON/KML import, polygon paint, line split, resize sliders, grid snapping, tape/emitter controls, irrigation editing after zone creation, keyboard command mode, PNG export, and durable API persistence remain open.
- The comparison page is explanatory and does not compare model scenarios. There is no configured scientific optimizer endpoint in this client; the included API returns a labelled UI fixture only.
- Farm plots and crop catalog are synthetic examples. Plot C is shaped to exactly 1,300 sq ft. Soil, water availability, crop performance, yields, solar output, and prices are absent; outcome metrics therefore say “Not estimated.”
- The optimizer fixture cannot be represented as farm-specific output or evidence of model validity. The wheat fixture status only indicates a provided golden crop fixture, not local validation.
- The strict label layout, crop pattern, unassigned hatch, scale bar, drip-row overlay, and demo-zone labels are present. Edge length labels and advanced chip leader rules are only partially implemented.
- Browser mobile coverage uses Chromium with mobile dimensions and touch enabled; it does not constitute native iOS Safari testing. WebKit was downloaded but the host lacked its runtime libraries, so it is not used by the test project.
- The version specified as Vitest 5 was available and pinned to 5.1.0. Playwright browser binaries were installed for test execution.

## Reproduction

Run two terminals from `frontend/`:

```powershell
pnpm mock
```

```powershell
pnpm dev
```

Open `http://localhost:5173` (or `http://localhost:5173/?demo=sample` to load the labeled demo result). To use a real backend, set `VITE_API_BASE` to the versioned API root and return the UI contract DTOs; adapter/auth wiring for the production API remains to be connected.

