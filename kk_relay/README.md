# KK Relay display — v1.0

Audience: an AI agent (or developer) picking this project up. Everything here is derived from
`KKRelay.pdf` (McCallum & Woolsey, *KK Relay*, Bridge Winners Press 2021). No git repo yet.

## Goal

An interactive bidding-box page that shows the KK Relay shape-showing structure after a strong 1♣,
to help people learn and remember it. v1.0 covers the full shape-showing tree plus the chapter-12
End-of-the-Line zooms. Nothing after shape is known (Control Ask, DCB) is modelled.

## Files

| File | What it is | Regenerate / run |
|---|---|---|
| `KKRelay.pdf` | Source book, 629 PDF pages. Printed page N = PDF page N + 14. | — |
| `extract_kkrelay.py` | Patches a temp copy of the PDF with ToUnicode maps for the suit-symbol fonts, then runs `pdftotext -layout` per chapter (from the PDF bookmarks). | `python extract_kkrelay.py` (needs `pypdf`, `pdftotext` on PATH) |
| `extracted/` | Output: `NN_chapter.txt` for all 20 chapters, `00_front_matter.txt`, and `KEY_printed_131-149.txt` (the core reference range: end of Three-Suiters, Shape-Showing Summary pp.133–141, Generic Distribution Drills pp.143–149). | produced by the script |
| `kkrelay.js` | Generates the full response tree after 1♣ from the book's rules (UMD: `window.KKRelay` in browser, `module.exports` in Node). | — |
| `verify.js` | Replays every `WEST/EAST` auction in `extracted/` that ends in "so exactly a=b=c=d" against the tree. | `node verify.js` |
| `index.html` | The display. Single page, loads `kkrelay.js` via `<script src>`. | serve the folder: `python -m http.server`, open `index.html` (file:// is blocked for the script in some setups) |

## Why the extraction needs a font patch

The book is LaTeX output. ♠/♣ are drawn from CMSY10, ♥/♦ from a custom font `Kp--M-Syc` as the
letters `r`/`q`, and the second-level list dash is a Type3 glyph. None carry a ToUnicode map, so
plain `pdftotext` drops all suit symbols and `pypdf` prints `r`/`q`. The script adds the maps
(CMSY10: 0x7C→♣, 0x7F→♠; Kp: 0x72→♥, 0x71→♦; Type3 a158→–) and extracts with `-layout` so the
nested bullets of the Summary chapter survive. There are no images in the book.

## Data model (`kkrelay.js`)

`KKRelay.buildTree()` returns a root node for 1♣ whose `children` are Teller's (responder's) calls.

```
{ bid:'2NT', label:'…', relay:'3C', children:[…] }                  // Asker relays next step, Teller continues
{ bid:'3D',  label:'…', shape:'4=4=1=4', generic:'4-4-4-1', counts:{S,H,D,C} }   // exact shape known (ESS call)
{ bid:'3NT', …shape…, zoom:true }                                  // End-of-Line zoom: same shape + control info
{ bid:'1D',  label:'…', terminal:true }                             // outside the modelled structure
```

Bids are strings `1C`…`7NT`; helpers: `parseBid`, `nextStep`, `pretty`, `walk(tree, tellerBids)`, `leaves(tree)`.
Shapes are `♠=♥=♦=♣`. Leaves under balanced sequences carry `kind: 'balanced'` (12–14 route) or
`'balanced15'` (2♦ route); everything else is treated as unbalanced for zoom rules.

Rules encoded (all from the Shape-Showing Summary and Generic Distribution Drills):

- First round: 1♦ = 0–8; 1♥ = 4+♠; 1♠ = 4+♥ (<4♠); 1NT = 5+♣ no 4-card major, or three-suiter short major;
  2♣ = 5+♦; 2♦ = balanced 9–11/15+; 2♥ = solid-suit specialty (terminal); 2♠+ = balanced 12–14.
- Suit-showing order Spades, Hearts, Clubs, Diamonds; MAFIA (4-card major shown first).
  Second-round: 2♥ = Reverser (4-card major first, longer second suit), 2♠ = long two-suiter,
  2NT+ = short two-suiter non-Reverser; idle steps 1♥-1♠-1NT-2♣-**2♦** and 1NT-2♣-**2♥** = three-suiters.
- Shortness HEL among suits not yet shown: 2NT high, 3♣ equal, 3♦+ low (Pivot Point 3♦; 3♥ for long two-suiters).
- Generic ESS tables: one-suiter 3♦..4♣ = 5332, 6331, 7231, 7321, 7330 (plus 6322 variants via 2♠-3♣ / 3♣);
  short two-suiter 3♦..3NT = 5431, 6421, 6430, 7420 (3♣ = 5422, 7411 Swan ignored);
  long two-suiter 3♥..4♣ = 5521, 5530, 5620, 6520 (3♦ then 3♠/3NT = 5611/6511);
  three-suiter 3♦..3NT = 4441, 4450, 4540, 5440 (3♣ then 3♥/3♠ = 4441 singleton honour high/low);
  balanced: 2♠ same-colour-or-4333-major, 2NT same rank, 3♣ 4333 minor, 3♦+ same shape; doubleton bid directly.
- End-of-Line zooms (`addZooms`): EOL 3♠ → 3NT = 3+ controls, then 4♣.. = Super-Positive 4/5/6/7 controls
  (unbalanced) or 15+ 4..8 controls (2♦ balanced); EOL 3NT → 4♣.. likewise; EOL 4♣ → 4♦.. = the 3NT shape
  with 4/5/6 controls. Balanced 12–14 gets only the 3NT zoom and never bids past 3NT.

## Verification status (v1.0)

`node verify.js`: 452 auctions found, 437 reproduce exactly. The 15 leftovers are accepted and ignored:
partially printed "?" examples, the 7-4-1-1 Swan, one 4♠ beyond the modelled zoom steps, and six places
where the book's prose shape contradicts its own printed hand (the hand agrees with the tree):
Ch 14 p.236 hand ♠QJ95 ♥863 ♦A742 ♣K8 (book 4=4=3=2, hand 4=3=4=2); Partnership Test #19, #31, #33, #62, #87.

## Display (`index.html`)

Three panels: bidding box (35 buttons, legal Teller calls highlighted, used calls struck), auction table
West/East with numbered footnotes, meaning panel listing each option and, at a leaf, the exact shape as a
hand diagram. Controls: Undo, Reset, Random hand. Theme toggle Auto/Light/Dark (stored in localStorage;
Auto follows `prefers-color-scheme`). No build step, no dependencies.

## Decisions so far

- Pages "131–149" in the brief are printed pages (PDF 145–163); this is the Summary + generic ESS tables.
- Ignore the 7-4-1-1 Swan and the verification leftovers.
- Step (auto-play one bid) button removed as unclear; Random hand kept.
- 12–14 balanced zooms stay as the book states (3NT = 3+ controls only); checked against Test #45/#83/#88.

## Not modelled / next ideas

Asker's non-relay options, Control Ask and Denial Cue-Bidding (ch. 13–15), specialty hands (ch. 16),
opener's rebids after 1♦. Candidate next features: a self-test drill from the Generic Distribution Drills
chapter (show a hand, user bids it), a hand-to-sequence lookup, full-sequence cheat-sheet view.
