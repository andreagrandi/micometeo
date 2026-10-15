---
name: SporaMeteo Fieldwork
colors:
  surface: '#fff9ed'
  surface-dim: '#dfd9cf'
  surface-bright: '#fff9ed'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f9f3e8'
  surface-container: '#f3ede2'
  surface-container-high: '#ede7dd'
  surface-container-highest: '#e8e2d7'
  on-surface: '#1d1b15'
  on-surface-variant: '#424844'
  inverse-surface: '#333029'
  inverse-on-surface: '#f6f0e5'
  outline: '#727974'
  outline-variant: '#c1c8c3'
  surface-tint: '#486458'
  primary: '#07241a'
  on-primary: '#ffffff'
  primary-container: '#1e3a2f'
  on-primary-container: '#86a496'
  inverse-primary: '#aecebe'
  secondary: '#6f5a49'
  on-secondary: '#ffffff'
  secondary-container: '#f7dac4'
  on-secondary-container: '#745f4d'
  tertiary: '#341800'
  on-tertiary: '#ffffff'
  tertiary-container: '#532a00'
  on-tertiary-container: '#d78c4a'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#caeada'
  primary-fixed-dim: '#aecebe'
  on-primary-fixed: '#032017'
  on-primary-fixed-variant: '#304c41'
  secondary-fixed: '#faddc7'
  secondary-fixed-dim: '#ddc1ac'
  on-secondary-fixed: '#27180b'
  on-secondary-fixed-variant: '#564333'
  tertiary-fixed: '#ffdcc2'
  tertiary-fixed-dim: '#ffb77b'
  on-tertiary-fixed: '#2e1500'
  on-tertiary-fixed-variant: '#6d3a00'
  background: '#fff9ed'
  on-background: '#1d1b15'
  surface-variant: '#e8e2d7'
typography:
  display-lg:
    fontFamily: Newsreader
    fontSize: 44px
    fontWeight: '500'
    lineHeight: 52px
    letterSpacing: -0.02em
  display-lg-mobile:
    fontFamily: Newsreader
    fontSize: 32px
    fontWeight: '500'
    lineHeight: 38px
    letterSpacing: -0.015em
  headline-lg:
    fontFamily: Newsreader
    fontSize: 30px
    fontWeight: '500'
    lineHeight: 36px
    letterSpacing: -0.015em
  headline-lg-mobile:
    fontFamily: Newsreader
    fontSize: 24px
    fontWeight: '500'
    lineHeight: 30px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Newsreader
    fontSize: 22px
    fontWeight: '400'
    lineHeight: 28px
  title-lg:
    fontFamily: DM Sans
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  title-md:
    fontFamily: DM Sans
    fontSize: 15px
    fontWeight: '600'
    lineHeight: 20px
  body-lg:
    fontFamily: DM Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: DM Sans
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: DM Sans
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-md:
    fontFamily: DM Sans
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.02em
  label-sm:
    fontFamily: DM Sans
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 14px
    letterSpacing: 0.06em
  caption-topo:
    fontFamily: DM Sans
    fontSize: 10px
    fontWeight: '600'
    lineHeight: 12px
    letterSpacing: 0.08em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-tablet: 1.25rem
  gutter-desktop: 1.5rem
  margin: 1rem
  margin-tablet: 1.5rem
  margin-desktop: 2.5rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1.25rem
  space-xl: 2rem
---

## Brand & Style

The design system is engineered for mycological field research, alpine forage planning, and bioclimatic observation across the Apennines and Alps. It balances the tactility of an archival botanical cartography dossier with the surgical precision of an alpine weather telemetry station.

The aesthetic philosophy fuses **Topographic Tactility** and **Modern Field Utilitarianism**:
- Natural parchment paper surfaces act as the grounding baseline, removing screen glare during direct forest sunlight.
- Fine hairline contour lines, precision micro-grids, and monospaced geodetic references establish authority.
- Tactile warmth overrides cold dashboard software: surfaces evoke pressed botanical paper, deep conifer needles, wet humus, and aged copper instruments.
- Visual cadence alternates between high-density meteorological readout matrices and expansive, unobstructed topographic canvas views.

## Colors

The chromatic system operates on botanical pigment hierarchy, alpine terrain depth, and a specialized chromatic likelihood ramp:

### Palette Structure
- **Primary (`#1e3a2f`) — Deep Conifer / Muschio Scuro:** The foundation for high-emphasis typography, critical structural framing, selected control anchors, and active state highlights.
- **Secondary (`#3d2c1d`) — Forest Bark / Corteccia:** Grounding secondary structural tone used for cartographic border bounds, subheaders, and natural material demarcations.
- **Tertiary (`#b87333`) — Alpine Ochre / Rame Bruciato:** Accent color reserved for active thermal anomalies, humidity-dewpoint crossover flags, user location markers, and interactive hover pings.
- **Neutral (`#f2ece1`) — Parchment Surface / Carta Topografica:** Natural unbleached low-glare field canvas background. Canvas default sits at `#f9f6f0` (Parchment White), with surface layering stepping down into `#f2ece1` and `#e6decb`.

### Specialized 0–100% Porcini Growth Likelihood Ramp
Dedicated chromatic continuum for grid-cell likelihood matrices (*Indice di Crescita*):
- **0–20% (Dormant/Dry):** `#fbf9f5` (Subtle bone white with light umber tint)
- **21–40% (Initial Soil Saturation):** `#ede4d0` (Soft pale mushroom cap)
- **41–60% (Favorable Thermal Window):** `#d8c29d` (Warm sand ochre)
- **61–80% (Prime Fruiting Mycelium):** `#b89569` (Rich porcini cuticle brown)
- **81–100% (Optimal Growth Outbreak):** `#8c6239` (Deep boletus cap chestnut)
Text layered over 0–60% cells defaults to `#1e3a2f`; 61–100% transitions to `#f9f6f0` for strict AA accessibility compliance.

## Typography

Typography pairs editorial field authority with rapid analytical legibility under shifting outdoor ambient conditions.

- **Editorial & Geographic Anchor (Newsreader):** Used for geographic names, forest reserves, peak designations, and principal likelihood summaries. Editorial italics are strictly leveraged for formal scientific taxonomy (*Boletus edulis*, *Boletus pinophilus*, *Boletus aereus*, *Boletus reticulatus*).
- **Cartographic & Meteorological Instrumentation (DM Sans):** Used across elevation charts, millimeter precipitation indicators, lunar cycle phases, temperature readings, and interactive controls. Clean geometric glyphs ensure numbers never blur or misread on high-density map displays.
- **Labels & Micro-Data (DM Sans Uppercase):** All geodetic coordinates, compass azimuths, and legal disclaimers employ letter-spaced uppercase formatting (`letterSpacing: 0.06em` to `0.08em`) to mirror surveyor benchmark engravings.

## Layout & Spacing

The structural layout uses an asymmetrical spatial model tailored for cartographic exploration alongside high-density telemetry data panels.

### Grid & Breakpoints
- **Desktop (≥1200px):** 12-column asymmetric layout with a fixed 380px or 440px expandable field-log panel on the left/right, while the remaining columns host the full-height interactive topographic engine. Gutters are locked at `1.5rem` (`24px`), margins at `2.5rem` (`40px`).
- **Tablet (768px – 1199px):** 8-column layout. Map runs full viewport width; telemetry and forest layer controls sit inside a semi-docked or bottom-anchored modal sheet. Gutters adjust to `1.25rem` (`20px`), margins to `1.5rem` (`24px`).
- **Mobile (≤767px):** 4-column layout. The cartographic interface occupies the full background canvas. An expandable drag-sheet anchors to the bottom with peek states: Mini (80px - quick likelihood score), Half (45% screen - rainfall and slope analytics), and Full (complete mycological weather breakdown). Margin and gutter set to `1rem` (`16px`).

### Component Spacing Rhythm
Component spacing follows strict 4px sub-intervals. Micro-data tables (soil pH, 72-hour rain accumulation, thermic shock differentials) prioritize dense baseline rhythm (`space-xs` and `space-sm`) to maximize visible indicators without vertical scrolling.

## Elevation & Depth

Visual hierarchy rejects exaggerated drop shadows and blurry blurs, relying instead on **tactile micro-elevation and hairline cartographic boundaries**.

- **Level 0 (Map Base / Canvas):** Parchment backdrop (`#f9f6f0` to `#f2ece1`) with subtle vector topographical contour lines rendered in `#3d2c1d` at 12% opacity.
- **Level 1 (Card & Module Layer):** Solid surface tint (`#f9f6f0`), bounded by a 1px solid stroke in `#3d2c1d` at 14% opacity. Zero shadow or micro-offset shadow: `0 1px 2px rgba(61, 44, 29, 0.05)`.
- **Level 2 (Floating Map Controls & Popovers):** Elevated surface with 1px stroke in `#1e3a2f` at 18% opacity, reinforced by a directional earth-tinted shadow: `0 3px 8px -1px rgba(30, 58, 47, 0.12), 0 1px 3px rgba(61, 44, 29, 0.06)`.
- **Level 3 (Modal Sheets & Inspection Drawers):** High-layer tactile depth framed by 1px solid `#1e3a2f` border and grounding ambient shadow: `0 12px 28px -4px rgba(30, 58, 47, 0.18), 0 4px 10px -2px rgba(61, 44, 29, 0.08)`.
- **Tactile Engraving Effect:** Recessed fields, input boxes, and likelihood scale legends use an inner hairline shadow (`inset 0 1px 2px rgba(61, 44, 29, 0.06)`) on a slightly darker parchment tone (`#eae3d2`).

## Shapes

The interface utilizes structured, utilitarian geometry with subdued corner radius curvature (`roundedness: 1`).

- **Controls and Cards:** Default corner radius sits at `0.25rem` (`4px`), providing the crispness of precision field notebooks and brass-mounted instruments.
- **Containers and Floating Drawers (`rounded-lg`):** Clamped to `0.5rem` (`8px`) to maintain structural integrity alongside dense data columns.
- **Likelihood Matrix Cells:** Absolute sharp squares (`0px` radius) or micro-beveled `2px` corners to preserve continuous pixel-grid scanning over geographic terrain.
- **Map Control Floating Anchors:** Compass, altitude scale, layer toggles, and coordinate crosshairs feature uniform `4px` corner beveling with 1px structural framing strokes.

## Components

### Buttons & Interactive Controls
- **Primary Field Action:** Solid `#1e3a2f` background, `#f9f6f0` text, `4px` border radius, padding `0.5rem 1rem`. Active state presses down 1px with `#152921`.
- **Secondary / Elevation Toggle:** `#f2ece1` background with 1px solid `#3d2c1d` (25% opacity), `#1e3a2f` text. Hover state darkens background to `#e6decb`.
- **Tactical Map Anchors:** Square `36x36px` or `44x44px` icon buttons with `#f9f6f0` fill, 1px solid `#1e3a2f` (30% opacity), featuring crisp dark green icons and high-contrast focus rings (`#b87333`, 2px offset).

### Likelihood Matrix (Porcini Probability Grid)
- Micro-cells formatted as compact data squares (`32x32px` on mobile, `40x40px` on desktop) colored along the specialized 0–100% gradient.
- Each cell displays the numeric score centered in `label-sm` font weight. Active/inspected cell outlines with a 2px solid `#1e3a2f` frame and an amber corner pip (`#b87333`).

### Chips & Filter Tags (Forest Typology & Tree Species)
- Used for selecting canopy profiles: *Faggeta* (Beech), *Castagneto* (Chestnut), *Abetaia* (Fir/Spruce), *Querceto* (Oak).
- Inactive state: Bordered in `#3d2c1d` (20% opacity) with `#3d2c1d` typography on transparent background.
- Active state: `#1e3a2f` background, `#f9f6f0` text, leading icon indicates leaf/needle silhouette.

### Input Fields & Search Bars
- Background set to `#f9f6f0` with 1px border `#3d2c1d` (30% opacity).
- Focused state applies 1px solid border `#1e3a2f` with a subtle outer glow: `0 0 0 2px rgba(30, 58, 47, 0.15)`.
- Monospaced placeholder formatting for altitude, commune, or coordinate queries (e.g., *44°12'N 10°28'E* or *Passo della Cisa*).

### Telemetry Cards & Metric Lists
- Dense list rows separated by 1px hairline divider (`#3d2c1d` at 10% opacity).
- Metric titles align left in `label-md`; values, units, and trend chevrons align right in DM Sans tabular figures.
- Moisture and rain-shock indicators pair numerical values with a thin 3px linear bar gauge tracking cumulative 14-day rainfall.

### Data Disclaimers & Field Warnings
- Prominent parchment warning cards demarcated with a left accent border in `#b87333` (3px thickness).
- Explicit bilingual safety disclaimers for mycological ingestion safety, mountain hazard conditions, and algorithmic prediction accuracy set in `body-sm` (`#3d2c1d`).
