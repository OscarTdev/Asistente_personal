---
name: Aura Admin Panel (admin-web)
description: The boutique concierge's desk — cream paper, bottle-green uniform, brass details, sealing-wax errata.
colors:
  ground: "#f4f1e9"
  panel: "#fffdf8"
  linen-50: "#faf8f1"
  linen-100: "#efeadd"
  linen-200: "#e5dfcd"
  linen-300: "#d6cdb4"
  linen-400: "#b8ad92"
  linen-500: "#918870"
  linen-600: "#6e6653"
  ink: "#211e18"
  ink-soft: "#4c473c"
  pine: "#1d4433"
  pine-deep: "#143325"
  pine-wash: "#e6efe9"
  brass: "#c9a86a"
  brass-deep: "#a5834f"
  brass-bright: "#debf88"
  brass-ink: "#6d5227"
  brass-wash: "#eadbb8"
  ok: "#1e6b4a"
  ok-wash: "#e6efe9"
  lacre: "#9c2f26"
  lacre-wash: "#f6e7e4"
  lacre-tint: "#e2a49d"
  petrol: "#31555c"
  petrol-wash: "#e7eff0"
typography:
  display:
    fontFamily: "EB Garamond, Georgia, 'Times New Roman', serif"
    fontSize: "1.5rem"
    fontWeight: 600
    letterSpacing: "-0.025em"
  brand:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 700
    letterSpacing: "0.22em"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
  control:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 600
    letterSpacing: "0.09em"
  figure:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontFeature: "tabular-nums"
rounded:
  chip: "3px"
  skeleton: "4px"
  md: "6px"
  lg: "8px"
  full: "9999px"
spacing:
  "1.5": "6px"
  "2": "8px"
  "2.5": "10px"
  "3": "12px"
  "4": "16px"
  "5": "20px"
  "6": "24px"
  "8": "32px"
  "10": "40px"
  "14": "56px"
components:
  button-primary:
    backgroundColor: "{colors.pine}"
    textColor: "{colors.ground}"
    typography: "control — system sans, 500, 0.875rem"
    rounded: "{rounded.md}"
    height: "40px"
    padding: "8px 16px"
  button-primary-hover:
    backgroundColor: "{colors.pine-deep}"
  button-destructive:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.lacre}"
    typography: "control — system sans, 500, 0.875rem"
    rounded: "{rounded.md}"
    height: "40px"
    padding: "8px 16px"
  button-destructive-hover:
    backgroundColor: "{colors.lacre-wash}"
  button-outline:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "control — system sans, 500, 0.875rem"
    rounded: "{rounded.md}"
    height: "40px"
    padding: "8px 16px"
  button-outline-hover:
    backgroundColor: "{colors.linen-50}"
  button-secondary:
    backgroundColor: "{colors.linen-100}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    height: "40px"
    padding: "8px 16px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.md}"
    height: "40px"
    padding: "8px 16px"
  button-ghost-hover:
    backgroundColor: "{colors.linen-100}"
    textColor: "{colors.ink}"
  button-link:
    backgroundColor: "transparent"
    textColor: "{colors.pine}"
    typography: "control — system sans, 500, 0.875rem"
  input:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "body — system sans, 400, 0.875rem"
    rounded: "{rounded.md}"
    height: "44px"
    padding: "8px 12px"
  switch-on:
    backgroundColor: "{colors.pine}"
    rounded: "{rounded.full}"
    width: "44px"
    height: "24px"
  switch-off:
    backgroundColor: "{colors.linen-300}"
    rounded: "{rounded.full}"
    width: "44px"
    height: "24px"
  card:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
  error-slip:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.md}"
    padding: "12px 16px"
  badge-draft:
    backgroundColor: "{colors.linen-100}"
    textColor: "{colors.linen-600}"
    rounded: "{rounded.full}"
    padding: "4px 8px"
  badge-sent:
    backgroundColor: "{colors.petrol-wash}"
    textColor: "{colors.petrol}"
    rounded: "{rounded.full}"
    padding: "4px 8px"
  badge-accepted:
    backgroundColor: "{colors.ok-wash}"
    textColor: "{colors.ok}"
    rounded: "{rounded.full}"
    padding: "4px 8px"
  badge-rejected:
    backgroundColor: "{colors.lacre-wash}"
    textColor: "{colors.lacre}"
    rounded: "{rounded.full}"
    padding: "4px 8px"
  badge-expired:
    backgroundColor: "{colors.brass-wash}"
    textColor: "{colors.brass-ink}"
    rounded: "{rounded.full}"
    padding: "4px 8px"
  nav-item-active:
    backgroundColor: "rgba(255, 255, 255, 0.10)"
    textColor: "{colors.brass-bright}"
    rounded: "{rounded.md}"
    height: "40px"
  nav-item-idle:
    backgroundColor: "transparent"
    textColor: "{colors.ground}"
    rounded: "{rounded.md}"
    height: "40px"
  ficha:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
  modal-panel:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    width: "32rem"
  total-card:
    backgroundColor: "{colors.pine-wash}"
    textColor: "{colors.pine}"
    rounded: "{rounded.lg}"
    padding: "16px"
---

# Design System: Aura Admin Panel (admin-web)

## Overview

**Creative North Star: "El conserje de boutique" (The Boutique Concierge)**

The panel is the concierge's desk of a boutique hotel. The owner arrives between jobs, does one concrete task, and leaves; the interface behaves like the discreet concierge who has already taken note — message slips stacked on the counter, the price book kept immaculate, quotes ready to hand over as PDF. Cream paper (#f4f1e9) is the ground; clear paper panels (#fffdf8) sit on it with 1px hairline seams and almost no elevation; the bottle-green shell (#1d4433) is the concierge's uniform, worn only by the sidebar, the primary buttons and the desk edges. Brass is never decoration: it is a functional detail that marks what is active, focused, or recently changed. Errors are sealing-wax errata slips that stay on the desk until dismissed, never vanishing toasts.

The system is deliberately quiet and Operate-mode dense: system sans for every datum, control and label, with EB Garamond (self-hosted, weights 500/600) reserved as the display voice for page titles only. There is exactly one authored motion — the 3px brass rail that slides down the sidebar to the active section in 150ms ease-out. The user works at a desk, day and night, in Spanish (es-CO); every COP figure is set in tabular numerals.

**Key Characteristics:**

- Cream paper ground with clear paper panels, joined by 1px hairline seams (linen tones), never heavy borders or shadows.
- Bottle-green shell as the only saturated surface: sidebar/top bar, primary buttons, table desk-edge, total card, login letterhead.
- Brass strictly functional: active rail, focus rings, change-hold seam, message-slip tab, expired badge. Never a fill.
- Errors as persistent `role="alert"` errata slips; destructive actions isolated, outlined in sealing-wax red, confirmed.
- Change-hold discipline: edited rows are tinted pine with a brass inset seam until the user actually sees them (mouseenter/focus).
- Every COP price, date, time and count in tabular numerals (`.tabular`, es-CO formatting).
- Loading as written slips (`.skel` shimmer blocks), never spinners.
- Authored SVG icon set, single 1.75px stroke, round caps — no icon library.
- Structural responsiveness at 768px: green sidebar on desktop becomes a green top bar with brass-underlined tabs on mobile; no functionality is desktop-only.

## Colors

The palette is warm paper and hotel furniture: cream and linen neutrals, a committed bottle green, brass as metallic detail, and three muted semantic inks (green success, sealing-wax red, petrol blue). No color outside this set appears in the build.

### Primary

- **Pine** (#1d4433): The concierge's uniform. Desktop sidebar (240px) and mobile top bar, primary buttons, table header desk-edge (2px rule), switch-on state, quote total card (on #e6efe9 wash), login letterhead, "Editar/Abrir" row links. It is the only large saturated surface in the system.
- **Pine Deep** (#143325): Hover state of primary buttons. Nothing else.
- **Pine Wash** (#e6efe9): Change-hold background for edited rows and toggled module cards; total card fill; hover tint of pine row links.

### Secondary

- **Brass** (#c9a86a): The sliding active-section rail in the sidebar.
- **Brass Deep** (#a5834f): Focus rings (buttons, inputs, switch) and the wax-seam inset on change-hold rows; the 34×3px tab on every message slip (`ficha::before`).
- **Brass Bright** (#debf88): Active nav-item text on the green shell; "Reconectando…" status dot.
- **Brass Ink** (#6d5227): Text on the expired badge (brass-wash ground) — the only place brass carries text.
- **Brass Wash** (#eadbb8): Expired badge fill; text-selection background.

### Tertiary (semantic inks)

- **Ok Green** (#1e6b4a): Success ink on #e6efe9 wash — "Aceptada" badge, "En el libro" badge, "En servicio" states, received-message dot. Reuses the pine-wash tint as its ground.
- **Lacre** (#9c2f26): Sealing wax. Inline validation text, errata slips (label on #f6e7e4-adjacent border #ecc8c1, panel ground), destructive buttons ("Retirar"/"Eliminar", 40% lacre border), the "Rechazada" badge (lacre-wash ground), and logout link text (#e2a49d tint on the green shell).
- **Petrol** (#31555c): Informational blue-green. The "Enviada" quote badge (petrol-wash ground #e7eff0) and the first stationery chip in the module-card palette.

### Neutral

- **Ground** (#f4f1e9): Page background — the desk itself. Also the text color on the green shell and the ring-offset color for focus rings.
- **Panel** (#fffdf8): Every card, slip, ficha, input, modal and table cell background — clear paper.
- **Linen 50–100** (#faf8f1 / #efeadd): Table row hover, skeleton blocks, secondary buttons, ghost-hover, row seams (divide/border at 1px).
- **Linen 200** (#e5dfcd): The canonical hairline: every card, ficha, slip and modal border; input-adjacent separators.
- **Linen 300** (#d6cdb4): Input borders, switch-off track, scrollbar thumb.
- **Linen 400** (#b8ad92): Muted status dots (sent messages, offline state).
- **Linen 500** (#918870): Icon-only dismiss/close buttons before hover.
- **Linen 600** (#6e6653): Secondary text — annotations, helper copy, plate labels, timestamps, pagination.
- **Ink** (#211e18): Primary text on paper; primary titles; body copy.
- **Ink Soft** (#4c473c): Secondary body text inside slips, fichas and cards.

A shadcn-style alias layer (`--color-primary`, `--color-muted`, `--color-ring`, …) is kept in sync in `@theme` for compatibility, but components in the build reference the named palette above directly.

### Named Rules

**The One Uniform Rule.** Pine is worn, not splashed: it appears only as the shell (sidebar/top bar), the primary action, the desk edge under table headers, the total card, and the login letterhead. If pine would fill anything else, the design is wrong.

**The Functional Brass Rule.** Brass never fills a surface. Its five tones appear only as: the sliding rail, focus rings, the change-hold inset seam, the message-slip tab, selection background, and the expired badge (the single text-bearing exception). Brass marks *state*, never *identity*.

**The Sealing-Wax Rule.** Lacre red is reserved for errata, destructive actions, rejected status, and logout. It never appears as a title color, link color, or decoration.

## Typography

**Display Font:** EB Garamond (self-hosted woff2, weights 500 and 600, `font-display: swap`; fallback Georgia → "Times New Roman" → serif). Applied via a single CSS rule to `h1` and `.brand-face`.
**Body Font:** System sans stack (-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif).
**Label/Mono Font:** None distinct — labels are the system sans in 600-weight spaced caps; figures use `font-variant-numeric: tabular-nums` on the same sans.

**Character:** One serif voice speaking only at the top of the page — hotel-stationery lettering for titles — while every datum, control and label below it stays in the working sans. The pairing says: elegant letterhead, working ledger.

### Hierarchy

- **Display** (EB Garamond 600, 1.5rem / `text-2xl`, tracking −0.025em): Page titles only ("Panel de Aura", "Catálogo de precios", "Cotización #…"). One per page. The `.brand-face` hook exists for brand moments; the sidebar wordmark currently uses the sans brand style instead (see drift note below).
- **Brand** (sans 700, uppercase, letter-spacing 0.22em–0.24em, ground-on-pine): The bot name wordmark on the sidebar (1.125rem), mobile top bar (1rem), and login letterhead (1.25rem), with an 11px 600/0.09em-caps sub-line beneath ("Panel de administración", "Asistente por WhatsApp").
- **Title** (sans 600, 1rem for modal headers; 0.875rem for card sections): "Nuevo ítem del catálogo", "Notas", "Ítems".
- **Control** (sans 500, 0.875rem): Buttons, nav items, inputs, row links, labels (`<label>` 0.875rem/500).
- **Body** (sans 400, 0.875rem, ~1.5 line-height): All data text, table cells, descriptions, empty-state copy. Secondary annotations drop to 0.75rem (`text-xs`) in linen-600.
- **Label** (`plate-label`: 0.6875rem, 600, letter-spacing 0.09em, uppercase, linen-600): Stationery plate labels — table headers, field plates ("Preparada", "Válida hasta"), feed metadata ("Recibido"/"Enviado"), module categories. The errata variant (`slip-label`) is 700 in lacre.
- **Figure** (sans, `tabular-nums`): Every COP amount (via `formatCOP`: `Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 2 })`), dates, times (es-CO, 24h), quantities, page counters, quote numbers. Missing values print an em-dash "—".

### Named Rules

**The Two Voices Rule.** EB Garamond speaks only from `h1`/`.brand-face`. No serif in body text, data, buttons, badges or labels — the working face of the panel is the system sans.

**The Tabular Ledger Rule.** Any figure that could sit in a column — price, quantity, date, time, count, ID — carries `.tabular`. A proportional-digit COP amount in a table is a defect.

**The Plate-Label Rule.** Small annotations are brass-plate plates: 11px, 600, 0.09em tracked uppercase in linen-600. They name things ("Fichas de mensaje", "Precio"); they never carry actions.

## Layout

**Spatial model:** A fixed 240px (w-60) pine sidebar owns the left edge on desktop; content flows to its right with 40px horizontal / 32px vertical padding (md:px-10 md:py-8). Pages are single-column: a desk header (title + subtitle + actions, 24px bottom margin), a filter row, persistent errata zone, then one full-width Card (the ledger/table) — modules use a responsive card grid instead (1 / 2 at 640px / 3 at 1280px columns, 16px gap).

**Density:** Table rows are 12px/16px padded (px-4 py-3) with h-12 skeleton stand-ins; summary stat cards are p-4; module and notes cards p-5. Inputs are 44px tall, buttons 40px (36px sm / 44px lg), nav items 40px — mobile targets are ≥44px (h-11 tabs, h-11 logout).

**Responsive behavior:** One structural breakpoint, 768px (Tailwind `md`). Above it: green sidebar with the sliding brass rail. Below it: sticky green top bar (56px) with the wordmark and a horizontally scrollable tab row where the active tab is underlined by a 2px brass border and set in brass-bright. Content padding tightens to 16px/24px. Grids reflow (quote summary 2 → 4 columns at 1024px). Nothing is removed on mobile.

**Spacing rhythm:** Tailwind 4px-base steps; the working set is 6/8/10/12/16/20/24/32/40px. Sections separate at 24px (mb-6/mt-6), cards in grids at 16px (gap-4), related chips at 8px, rows at 12px vertical.

## Elevation & Depth

The system is flat paper with hairline seams. Depth comes from tint layering (ground → panel → washes) and 1px linen borders — not from shadow. There are exactly two drop shadows in the entire build: the modal panel's `shadow-xl` (a paper note lifted over the desk, over an ink/45% scrim, rgba(33,30,24,0.45)) and the switch knob's `shadow-sm`. The change-hold mark is an *inset* 3px brass seam (box-shadow inset), which reads as a wax line on the paper, not an elevation. Browser chrome carries the material too: text selection is brass-wash on ink, scrollbars are thin linen-300 thumbs.

### Shadow Vocabulary

- **Modal panel** (`box-shadow: 0 20px 25px -5px rgba(0,0,0,0.10), 0 8px 10px -6px rgba(0,0,0,0.10)` — Tailwind shadow-xl): Only for dialogs. Never on cards, tables, or hover states.
- **Switch knob** (`box-shadow: 0 1px 2px rgba(0,0,0,0.05)`): Makes the 16px paper knob sit on its track. Decorative shadows elsewhere are absent by design.
- **Change-hold seam** (`box-shadow: inset 3px 0 0 #a5834f`): A wax edge inside the row's left edge, released with the tint over 150ms ease-out.

### Named Rules

**The Flat Paper Rule.** Cards and tables are flat at rest and flat on hover (hover = linen-50 tint, never a shadow). The only lifted object is the modal, because it is physically in the air.

## Shapes

The form language is stationery: softly squared paper, hairline edges, and small brass hardware. Radius ladder: 3px stationery chips (module identity dots), 4px skeletons, 6px (`rounded-md`) for all controls, fichas and slips, 8px (`rounded-lg`) for cards, modal panels and the login letterhead, and full pills for badges, the service-status capsule and the switch. Recurring geometry: 1px linen-200 hairline seams on every paper surface; a 2px pine desk-edge under table headers (`.thead-edge`) with 1px linen-100 rules between rows; the 3px rounded brass rail on the shell's left edge; the 34×3px brass tab (radius 0 0 2px 2px) hanging over each message slip's top edge; 2px brass underline on active mobile tabs; 1.5–2px status dots.

## Components

### Buttons

- **Shape:** 6px radius, 40px tall (sm 36px / lg 44px / icon 40×40px), 16px horizontal padding, sans 500 0.875rem, icons 16px stroke-set, disabled at 50% opacity.
- **Primary:** Pine ground, cream ground text (#f4f1e9); hover pine-deep. Reserved for the page's main action ("Agregar ítem", "Nueva cotización", "Descargar PDF").
- **Destructive:** Panel ground, lacre text, 1px lacre border; hover lacre-wash. Used for "Retirar" (catalog) and guarded by `window.confirm`.
- **Outline:** Panel ground, ink text, 1px linen-300 border; hover linen-50. Cancel/secondary actions.
- **Secondary:** Linen-100 ground, ink text; hover linen-200.
- **Ghost:** Transparent, ink-soft text; hover linen-100 ground + ink text.
- **Link:** Pine text, underline on hover (offset 4px); used for in-page navigation ("Cotizaciones" back link).
- **Focus:** 2px brass-deep ring with a 2px ground-colored offset (double-ring effect on cream). Buttons transition colors only (~150ms).
- **In-row text actions** ("Editar", "Abrir") are bare pine text buttons with pine-wash hover; destructive in-row buttons are outlined lacre/40, lacre text, lacre-wash hover, and are separated by a deliberate 12px gap (`ml-3`) — never adjacent to safe actions.

### Inputs / Fields

- **Style:** 44px tall, 6px radius, 1px linen-300 border, panel ground, 0.875rem ink text, linen-600 placeholders. Textareas share the treatment at 3 rows.
- **Focus:** 2px brass-deep ring (no offset) plus the border shifting to brass-deep — the ring and the seam agree.
- **Error:** Inline field errors in lacre text; form-level failures additionally surface as errata slips. Disabled: 50% opacity, not-allowed cursor.
- **Number/COP fields** carry `.tabular` and are shared via a `numberInputClasses` constant so every ledger field is identical.

### Switch

The concierge's service toggle: 44×24px pill, 6px-radius track. On = pine track with a 16px paper knob at the right (translate-x-6); off = linen-300 track, knob at the left. Track color and knob position transition (~150ms). `role="switch"` with `aria-checked` and `aria-label` in Spanish; focus is a brass-deep ring offset on panel. It sits alone on the module card's right side — the control is deliberately separated from the card's text content.

### Cards / Containers

- **Corner Style:** 8px radius.
- **Background:** Panel (#fffdf8) on the cream ground; borders 1px linen-200.
- **Shadow Strategy:** None (Flat Paper Rule). The modal is the sole exception.
- **Internal Padding:** p-4 for stat tiles, p-5 for content cards; full-bleed tables via `overflow-hidden`.
- **Total card variant:** pine-wash ground, pine/30 border, plate-label in soft ink, total in pine 700 1.125rem tabular — the one card allowed to wear the uniform.
- **Ficha (signature):** the message slip — 6px radius, panel ground, linen-200 hairline, and a 34×3px brass tab (`::before`) fixed 14px from the left edge, overhanging the top border. Stacked at 12px in the feed; each carries contact (semibold 0.875rem), tabular timestamp (0.75rem linen-600), two-line clamped preview, and a direction plate-label with a 6px dot (ok green = received, linen-400 = sent).

### Status Badges

Full pills, 4px/8px padding, 0.75rem/500 text. Single source of truth in `lib/quoteStatus.tsx`: Borrador = linen-100/linen-600 · Enviada = petrol-wash/petrol · Aceptada = ok-wash/ok · Rechazada = lacre-wash/lacre · Vencida = brass-wash/brass-ink. The same wash/ink pairs drive catalog activity badges ("En el libro" = ok-wash/ok, "Retirado" = linen-100/linen-600) and the AI "del catálogo" confirmation chip (ok-wash/ok).

### Error Slip (signature)

Errors are persistent notes in sealing wax, never toasts. `.slip`: 1px #ecc8c1 border, panel ground, 6px radius, 12px/16px padding, `role="alert"`. Content: a `slip-label` ("Errata", 11px/700 caps tracked, lacre) over the message in ink-soft 0.875rem, with an optional linen-500 dismiss button that turns ink on hover. Pages reserve a persistent slip zone between filters and content; loading and mutation errors both land there.

### Navigation

Desktop: fixed pine sidebar. Wordmark block (letterhead) above a white/10 hairline; items are 40px rounded rows — idle ground/90 text, hover white/5, active white/10 ground with **brass-bright** text; the 3px brass rail (40px tall, rounded right corners) slides vertically to the active item over **150ms ease-out** — the system's single authored motion. Footer carries the account email (linen-300 0.75rem) and a lacre-tint logout. Mobile: the desk becomes a 56px sticky pine top bar plus a scrollable tab row; active tab = 2px brass bottom border + brass-bright text.

### Modal

"A paper note brought over the desk": full-screen ink/45% scrim; panel max-w-lg (wide variant max-w-3xl), 8px radius, linen-200 border, panel ground, shadow-xl, capped at 85vh with internal scroll. Header row (16px/24px padding, linen-100 hairline beneath) holds a 1rem/600 title and a linen-500 IconX. Behavior is part of the design: focuses the panel on open, traps Tab, closes on Escape/scrim, returns focus to the opener.

### Loading Skeletons

`.skel`: linen-100 blocks, 4px radius, shimmering with a panel-tinted (rgba(255,253,248,0.85)) gradient sweeping every 1.4s ease-out. Tables show six h-12 rows; pages show structural blocks inside real fichas/cards. Buttons swap their labels for Spanish progress text ("Guardando…", "Generando…", "Importando…") instead of spinners. The shimmer is disabled under `prefers-reduced-motion: reduce`.

### Service Status

A 36px full-pill capsule (panel ground, linen-200 hairline) with an 8px dot: ok = "En servicio", brass = "Reconectando…", linen-400 = "Fuera de servicio", next to ink-soft 0.875rem text. The same dot language marks feed direction.

### Module Cards

Each module is a stationery slip (Card p-5) with an identity ink chip — a 10px, 3px-radius square from a fixed palette of eight muted tint/ink pairs (petrol, ok, ochre #8a6d3b, lacre, violet #5b4a7e, blue #3c5687, brown #8a5a2b, olive #5b5643) chosen by a deterministic hash of the module key. Category as plate-label, description in ink-soft, state line ("En servicio" in ok / "Apagado" in linen-600), switch isolated top-right. Toggling applies the row-hold treatment to the card until seen.

### Icons

Authored inline SVG set (`components/ui/icons.tsx`): 24×24 viewBox, `fill: none`, `stroke: currentColor`, 1.75px width, round caps and joins, `aria-hidden`. Panel, Tag, Receipt, Power, Logout, Plus, Upload, Download, X, ArrowLeft. No icon library, no glyph fonts, no emoji.

## Do's and Don'ts

### Do:

- **Do** set every COP figure with `formatCOP` (es-CO, ≤2 decimals) inside a `.tabular` element; dates and times in es-CO, 24h times in the feed.
- **Do** render all errors — fetch, mutation, PDF — as `ErrorSlip` with `role="alert"` in the page's persistent slip zone.
- **Do** mark just-changed rows/cards with `row-hold` (pine-wash + inset brass seam) and release it on mouseenter/focus — the change stays noted until seen.
- **Do** keep destructive actions: lacre outline style, 12px separated from safe actions, behind `window.confirm`.
- **Do** use the wash/ink badge pairs for every status (accepted=ok, sent=petrol, rejected=lacre, expired=brass, draft/inactive=linen).
- **Do** keep mobile at parity: the 768px switch changes the shell, never the features; touch targets ≥44px on mobile.
- **Do** load with `.skel` skeletons and progress-text buttons; respect `prefers-reduced-motion`.
- **Do** write UI copy in formal es-CO with the desk's vocabulary ("El libro", "En servicio", "Errata", "Guardar en el libro") — code identifiers in English.

### Don't:

- **Don't** fill any surface with brass, and don't add a sixth brass use outside rail / focus ring / hold seam / slip tab / selection / expired badge.
- **Don't** add drop shadows to cards, tables or hover states; depth is hairline seams and washes. The modal is the only lifted surface.
- **Don't** use toasts, spinners, or any animation library — errata slips, `.skel`, and the 150ms rail are the entire motion/feedback vocabulary.
- **Don't** let EB Garamond appear anywhere but page titles (`h1`/`.brand-face`); the serif never sets data, buttons or labels.
- **Don't** pull in an icon library or glyph fonts — extend the authored 1.75px stroke set instead.
- **Don't** place a destructive button next to a safe one, or skip the confirm step.
- **Don't** introduce colors outside the token palette (including new module chips — extend the fixed eight-pair list instead).
- **Don't** suggest in any screen that prices come from the AI: catalog-matched items wear the ok-wash "del catálogo" chip, and copy states that prices always come from the book.
