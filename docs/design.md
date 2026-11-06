# Design

The Lotse should look like a public health service: calm, white, institutional blue, flat surfaces and a little green. Our users are old, young and disabled people. Legibility, contrast and keyboard access come first. Tokens live in `frontend/src/assets/base.css`, shared parts in `frontend/src/assets/main.css`. Component CSS uses tokens only, never hex values.

## Colour roles

| Role | Token | Light | Use |
|---|---|---|---|
| Ink | `--ink`, `--ink-2`, `--ink-3` | `#001E50` navy | Text. `--ink-3` is the lowest text tone (4.5:1 on every ground). |
| Heading blue | `--head` | `#05498C` | Page titles, card titles, links. |
| Action | `--action`, `--action-hi`, `--on-action` | `#05498C`, hover `#001E50` | Buttons, pressed chips, selection. |
| Green accent | `--accent`, `--accent-bg` | `#1F806A`, mint `#E5F7F0` | Meta labels, avatar, the open chat ("you are here" dot on mint), "Verstanden", plan progress bar, call script numbers, checklist ticks, the entry page band. |
| Positive | `--ready-ink`, `--ready-bg`, `--ready-mark` | green on mint | Done, open now, "Kommt in Frage". |
| Your turn | `--turn-ink`, `--turn-bg`, `--turn-mark` | the same green and mint | The current step, gaps to fill in, the plan bar. There is no amber or gold. |
| Open item | `--todo-bg`, `--todo-ink` | signal yellow `#FFE680`, navy text | Only the small status pills that need the user: "Frage offen", "N offene Schritte", "Jetzt dran". Never a surface, border or button. |
| Waiting | `--wait-*` | lavender | Steps that wait on someone else. |
| Danger | `--danger` | `#B3261E` | Real problems only: errors, deleting. |
| Grounds | `--paper`, `--sheet`, `--sunk`, `--band`, `--navy` | white, white, grey `#F2F5F5`, lavender `#E9EBF8`, navy | Page, cards, quiet zones, selection and user messages, the home pane and the Lotse's messages. |
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

- Radius: `--r-s` 8px (small insets, speech bubbles, the composer), `--r-m` 12px (cards, check rows), `--r-l` 16px (dialogs), `--r-pill` (buttons, chips, inputs, status pills).
- Depth: flat. Cards are white with a hairline (`border: var(--hair)`). Only dialogs float (`--float`). Quiet areas sit on a grey or lavender ground without a border. The composer's edge is a 1px drop shadow in `--rule-2`, so it runs around its tail too.
- Spacing in rem: .25, .5, .75, 1, 1.5, 2, 3. Cards pad 1.25 to 1.4rem.
- Icons: the line sprite in `index.html`, 24px grid, stroke 2, round caps. No icon in a tinted square.
- Targets at least 2.75rem (49px at M).

## Patterns

- Buttons: primary is a filled blue pill, secondary a blue outlined pill, quiet is blue text. One primary per card.
- Chips: white pills with a thin edge; hover lavender; pressed filled blue.
- Plan: a wayfinding line. Done stations are filled green with a tick and say "Erledigt"; the current one is a green ring with a dot, its card has a green border and says "Jetzt dran"; later ones are hollow. Shape and word tell now from done, not colour.
- Navy (`.navy-band`, `--navy`): solid, never a gradient. The home pane (greeting, composer, what the Lotse knows) and, in a chat, the Lotse's messages.
- Speech bubbles: rectangular (`--r-s`), flat, with a small tail. The user's own words sit on lavender with the tail on the right. The Lotse's text replies and its open question sit on navy with white text and the tail on the left; its chips stay white, a pressed one turns blue with a white edge. The composer is a white bubble with the tail on the left.
- Home: two columns on wide screens, each fitting the screen; a column that is too long scrolls on its own, the page never does. Narrow, they stack: the navy part, then the list, then the details on navy again.
  - Left, navy: the greeting ("Guten Tag," small, the name large and bold below it), then the composer as the one white surface on the navy, so it leads. What the Lotse knows sits below it right on the navy, without a card: a filled-in form, since these details go into the forms. One field per detail with its line icon and label; the value sits on a form line (`--rule-2`). An empty field is a dashed line with "Ergänzen", which opens the settings. In a chat it is one line that opens on demand.
  - Right, on the page: "Was jetzt ansteht". One white sheet with hairline rows, like an appointment slip, not a grid of cards. Per chat that needs the user: the status pill ("Frage offen", "Jetzt dran"), the chat's title, the next action in heading blue with its line icon (the open question or the step's title), then the institution and "jetzt erreichbar" for a call. The whole row opens the chat. Chats that wait on someone else follow under "Wartet auf Antwort" in quieter rows; finished chats are not listed. When nothing needs the user, a blank slip with a dashed edge (like an empty form field) says so in one line and what will appear there.
- App bar: one white line with a hairline under it, on every screen. The mark and "SV KI-Lotse" on the left, where the sidebar's content starts; on the right "Dunkel"/"Hell", the avatar with the name and "Einstellungen", and "Abmelden" (before signing in: the language and "Dunkel"/"Hell"). Signed in on wide screens, the bar follows the page's columns: the brand cell is the sidebar's width and the sidebar's hairline runs on up through it. Narrow, the buttons are round icons with a short label, and "Alle Gespräche" leads back to the list.
- Footer: on the login page and the home view only, a navy band across the full width. The mark and "SV KI-Lotse" on the left; on the right "Medizinische Fragen:" with Gesundheitsberatung 1450 and "Im Notfall:" with Rettungsnotruf 144 as outlined pills that call. Narrow, only the two pills; the labels and names stay for screen readers. Nothing else, and never links to pages that do not exist.
- Brand mark: a navy disc with a white ring and a green dot, a "you are here" marker. Also the favicon.

## Do

- Use a token for every colour, and add a role here before adding a token.
- Keep one action per card, and show status in words, not only colour.
- Check new screens at 1280x720 and 375px, in light, dark and high contrast, and at text size XL.

## Don't

- No gradients, emoji, stock images, glow or soft card shadows.
- No coloured side stripes on cards, no decorative numbering (number real sequences only), no progress rings or scores for filling in the profile.
- No uppercase outside `.caps`, no accent colour on single headline words.
- No other fonts, and never Inter or the system font alone.
- No ÖGK logo, wordmark, name or layout copied one to one.
