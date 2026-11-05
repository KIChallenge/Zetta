# Design

The Lotse should look like a public health service: calm, white, institutional blue, flat surfaces and a little green. Our users are old, young and disabled people. Legibility, contrast and keyboard access come first. Tokens live in `frontend/src/assets/base.css`, shared parts in `frontend/src/assets/main.css`. Component CSS uses tokens only, never hex values.

## Colour roles

| Role | Token | Light | Use |
|---|---|---|---|
| Ink | `--ink`, `--ink-2`, `--ink-3` | `#001E50` navy | Text. `--ink-3` is the lowest text tone (4.5:1 on every ground). |
| Heading blue | `--head` | `#05498C` | Page titles, card titles, links. |
| Action | `--action`, `--action-hi`, `--on-action` | `#05498C`, hover `#001E50` | Buttons, pressed chips, selection. |
| Green accent | `--accent`, `--accent-bg` | `#1F806A`, mint `#E5F7F0` | App bar line, meta labels, avatar, the open chat ("you are here" dot on mint), user messages (mint), "Verstanden", plan progress bar, call script numbers, checklist ticks, the entry page band. |
| Positive | `--ready-ink`, `--ready-bg`, `--ready-mark` | green on mint | Done, open now, "Kommt in Frage". |
| Your turn | `--turn-ink`, `--turn-bg`, `--turn-mark` | the same green and mint | The current step, gaps to fill in, the plan bar. There is no amber or gold. |
| Open item | `--todo-bg`, `--todo-ink` | signal yellow `#FFE680`, navy text | Only the small status pills that need the user: "Frage offen", "N offene Schritte", "Jetzt dran". Never a surface, border or button. |
| Waiting | `--wait-*` | lavender | Steps that wait on someone else. |
| Danger | `--danger` | `#B3261E` | Real problems only: errors, deleting. |
| Grounds | `--paper`, `--sheet`, `--sunk`, `--band`, `--navy` | white, white, grey `#F2F5F5`, lavender `#E9EBF8`, navy | Page, cards, quiet zones, selection and user messages, the dark band. |
| Lines | `--rule`, `--rule-2`, `--hair` | hairline, edge `#7D8BA6` | `--hair` separates surfaces; `--rule-2` outlines controls (3:1). |
| Focus | `--focus` | `#0B63CE` | 3px ring. Inside `.navy-band` it turns white. |

Every role exists in all four themes: light, dark (derived from the navy, not grey), high contrast and high contrast dark. Text is at least 4.5:1, control edges and focus at least 3:1.

Green means good or here: done, open, your turn. It is never a button colour. Green text (`--accent`) goes on white only.

## Type

One family: Source Sans 3 (Google Fonts, 400/600/700). Its `l` has a tail, `1` a flag and `0` is narrower than `O`. Figures are tabular everywhere, so hours and phone numbers line up.

| Step | Token | Size at 18px | Use |
|---|---|---|---|
| Meta | `--fs-meta` | 13.5px, 700, uppercase, +1px | `.caps`: small meta labels only (sidebar heading, call script labels). |
| Small | `--fs-small` | 15.75px | Hints, times, pills. |
| Body | `1rem` | 18px | Everything else. Line height 1.5. |
| Lead | `--fs-lead` | 20px | Intro lines, phone numbers, script quotes. |
| H3 | `--fs-h3` | 22.5px, 600 | Card and question titles, in heading blue. |
| H2 | `--fs-h2` | 27px, 600 | Plan heading. |
| H1 | `--fs-h1` | 36px, 400 | Page titles, weight 400 in heading blue. |
| Display | `--fs-display` | 47px, 400 | Entry headline; its first line is bold. |

Text size M/L/XL scales the root (18/21/24px), so everything is in rem.

## Shape and space

- Radius: `--r-s` 8px (small insets), `--r-m` 12px (cards, check rows), `--r-l` 16px (dialogs, bubbles), `--r-pill` (buttons, chips, inputs, status pills).
- Depth: flat. Cards are white with a hairline (`border: var(--hair)`). Only dialogs float (`--float`). Quiet areas sit on a grey or lavender ground without a border.
- Spacing in rem: .25, .5, .75, 1, 1.5, 2, 3. Cards pad 1.25 to 1.4rem.
- Icons: the line sprite in `index.html`, 24px grid, stroke 2, round caps. No icon in a tinted square.
- Targets at least 2.75rem (49px at M).

## Patterns

- Buttons: primary is a filled blue pill, secondary a blue outlined pill, quiet is blue text. One primary per card.
- Chips: white pills with a thin edge; hover lavender; pressed filled blue.
- Plan: a wayfinding line. Done stations are filled green with a tick and say "Erledigt"; the current one is a green ring with a dot, its card has a green border and says "Jetzt dran"; later ones are hollow. Shape and word tell now from done, not colour.
- Navy band (`.navy-band`): one per screen at most (the home greeting and composer).
- Brand mark: a navy disc with a white ring and a green dot, a "you are here" marker. Also the favicon.

## Do

- Use a token for every colour, and add a role here before adding a token.
- Keep one action per card, and show status in words, not only colour.
- Check new screens at 1280x720 and 375px, in light, dark and high contrast, and at text size XL.

## Don't

- No gradients, emoji, stock images, glow or soft card shadows.
- No coloured side stripes on cards, no decorative numbering (number real sequences only).
- No uppercase outside `.caps`, no accent colour on single headline words.
- No other fonts, and never Inter or the system font alone.
- No ÖGK logo, wordmark, name or layout copied one to one.
