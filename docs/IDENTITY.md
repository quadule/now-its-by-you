# Songbird's look

**The idea.** Every page is a leaf of the same printed song: a broadside set in a book face on cream paper,
in one letterpress ink, headed in a printer's red, with whatever a person chose or wrote added in a second
hand's indigo, the way a song copied from hand to hand picks up a later copyist's marks.

The artist's brief: "a consistent design between all pages that feels connected to its tradition and is free
of AI design cliches." It covers the singing page, each singer's own page, the seed page (now.itsby.you) and
the studio. The packet's README and the command line are text and stay text.

**Where it lives.** `identity.css` holds the tokens and the shared pieces (masthead, card, button, field,
link, audio control, double rule). It is one file in two places, byte for byte: `web/sing/page/identity.css`
(served by the worker, stamped by `tools/sing_site.py`'s `versioned()`) and `songbird/studio/identity.css`
(served by `songbird/studio.py`); a test holds them equal. Edit one, copy it over the other. Each page loads
it first, then its stylesheet (`sing.css`, `yours.css`, `studio.css`) for its layout. The reading
pages mark `<body class="leaf">`, so their plain `<button>`s and fields take the shared look; the studio
uses `.btn`.

## Palette

| token | light | dark (by lamplight) | from | contrast (light / dark, on paper) |
|---|---|---|---|---|
| `--paper` | `#f4ecdc` | `#17130e` | cream laid paper of a broadside | — |
| `--card` | `#fbf7ee` | `#211b14` | a fresh leaf; an index card | — |
| `--wash` | `#ebe0c9` | `#2a2219` | ochre and manila papers, a seed packet's | — |
| `--ink` | `#2b231d` | `#ede3cf` | letterpress black, a brown-black | 13.1 / 14.5 |
| `--ink-2` | `#554737` | `#c9bba4` | the same ink, lighter struck | 7.6 / 9.8 |
| `--ink-3` | `#6b5c4b` | `#a89985` | small print, hints | 5.5 / 6.7 (4.9 / 5.6 on wash) |
| `--hand` | `#2b4474` | `#a9c2ea` | indigo, iron-gall blue-black: a second hand | 8.2 / 10.2 |
| `--red` | `#a3361f` | `#e8937c` | a printer's red, the rubricator's | 5.8 / 7.8 |
| `--rule` | `#d6c8ae` | `#3d3429` | hairlines between things (not text) | — |
| `--rule-strong` | `#8f7d66` | `#7d6d5a` | the edge of a button or field | 3.4 / 3.7 (3:1 for a control's edge) |
| `--ochre` | `#7f5610` | `#dcaa52` | time, caution | 5.5 / 8.7 |
| `--green` | `#44683a` | `#98bd8b` | sap green: sent, kept | 5.4 / 8.8 |
| `--stage` | `#1b1611` | `#0e0b08` | the stage: a page lit in the dark | — |
| `--stage-ink` / `--sung` / `--stage-red` | `#efe6da` / `#f2b25c` / `#e0664d` | same | lamplight on the page; the canvas (tools/karaoke.js) draws in these | 14.5 / 9.7 / 5.3 |

Every text colour clears 4.5:1 on paper, card and wash in both schemes; the primary button's cream on ink is
14:1. The studio's legend adds `--parent` (`#7a4a2c` / `#d6a784`, an older hand's iron-gall brown,
6.3 / 8.6) and `--chance`; everything else it names (`--you`, `--rubric`, `--soft`...) is an alias of these.

## Type

- **The book face** for words and titles: `--serif`, the system's old-style serif (Iowan Old Style on Apple
  devices, Palatino elsewhere, Georgia last). Reading text 17 px on 1.55 leading, a measure of at most
  720 px (about 70 characters). Titles 30 to 42 px, semibold; step and card headings 21 px.
- **The system sans** (`--sans`) only where a control needs it: button labels, the speed switch, the
  studio's settings. **Mono** (`--mono`) only for commands to type (the seed page's `python3 ...`).
- **The kicker** above each title (SONGBIRD, THE VOLUNTEERS) is red small capitals, letterspaced, as a
  ballad sheet's first line. **Rubrics**, the names of the song's parts (Verse 1, Refrain, a card's label),
  are the same red small capitals, as tune books and hymnals set them. Headings are ink, not red.

## Rules, and the pieces

- **The masthead** (`.masthead`): kicker, title, then a thin-and-thick rule (1 px over 2 px), the way a
  broadside closes its heading. One on every page, the studio's under its toolbar.
- **The double rule** (`3px double`), from a seed packet's border: only for notices and documents: the AI
  disclosure, the releases a singer agrees to, dialogs, the studio's player strip and tour.
- **A card** is an index card: card paper, a 1 px hairline, a 2 px corner, and its heading ruled off
  underneath in a faint red hairline, as a field recordist's card has its red head line.
- **A button** is a small squared block, as set on a letterpress: sans label, 1 px edge in `--rule-strong`,
  2 px corners, 44 px tall on the phone pages. The primary one is solid ink with cream letters. A warning
  button (withdraw, delete) is red letters in a red edge.
- **A link** is ink, underlined in red; red on hover. So an underline always means a link.
- **A field** is a ruled box on paper, and what a person types into it is in the second hand: indigo, in
  the book face. The placeholder is italic small print.
- **An audio control** is the browser's own, full width, squared, on card paper in a ruled edge. The
  studio's player buttons are squared too, not round.
- **The stage** on the singing page is dark in both schemes, framed in a faint cream double rule: the words
  set in the book face, sung syllables filling in lamplight amber, the part's name as a red rubric.

## A person's own changes

Whatever a person chose or wrote is in `--hand`: words they picked or wrote in the studio (with a 2 px
indigo rule in the margin beside a section they changed, as a later hand marks a copy), the cards they
changed, the notes they moved; on the singing page the words they send and anything they type; on their
own page the words they sent. The printed song stays in ink. Nothing else is indigo, so the second hand is
always legible as a second hand.

## Not done

Gradients (the only ones draw hard-edged lines: a syllable's fill, the studio's margin rule, a select's
caret, the piano roll's grid); glass or blur; rounded pills or big radii (2 px is the most); drop shadows or
glows; emoji; purple, teal or neon; hero images, textures, drawn wear or fake-old type; downloaded fonts;
the system sans as the voice of every page; letterspaced uppercase grey labels. The `▶ ● ■ ✓ ✗ ⛶` in some
button labels are the pages' wording, typographic signs rather than emoji, and stay.
