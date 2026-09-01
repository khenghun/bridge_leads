/**
 * Built-in example hands for the upload screen (play v1.2).
 *
 * Real hands from the author's own BBO sessions, plus one from a published
 * teams championship, with the player names replaced by the seats they sat in
 * (the `pn|` field) — the app never shows or sends names. Chosen to cover
 * different stories so a first visitor can see the grader at work without a
 * `.lin` of their own. Board 17 stays first: it is the deterministic fixture
 * the run-apps skill checks against.
 */
export interface Example {
  id: string
  /** Short label for the button, e.g. 'Board 17 · 1NT by West'. */
  title: string
  /** One or two sentences: what kind of hand it is and what to look for. */
  blurb: string
  /** The complete LIN text, exactly as the upload path would receive it. */
  lin: string
}

export const EXAMPLES: Example[] = [
  {
    id: "board17-1nt",
    title: "Board 17 · 1NT by West",
    blurb: "A plain 1NT, nine tricks recorded then a claim. The defence has the choices here — start with E/W to see declarer, or N/S to grade the defenders.",
    lin: (
    'pn|South,West,North,East|st||md|3SKT3HJT7D87CKQ843,SA54HQ94DT963CAT2,S9872HK85DAJ542C5,SQJ6HA632'
    + 'DKQCJ976|rh||ah|Board 17|sv|o|mb|p|mb|1C|mb|p|mb|1N|mb|p|mb|p|mb|p|pg||pc|S9|pc|SJ|pc|SK|pc|S5|p'
    + 'g||pc|ST|pc|S4|pc|S2|pc|SQ|pg||pc|C6|pc|C4|pc|CT|pc|C5|pg||pc|D3|pc|D5|pc|DQ|pc|D7|pg||pc|H2|pc|'
    + 'HT|pc|HQ|pc|HK|pg||pc|S8|pc|S6|pc|S3|pc|SA|pg||pc|H4|pc|H8|pc|H3|pc|H7|pg||pc|S7|pc|C7|pc|C3|pc|'
    + 'C2|pg||pc|DA|pc|DK|pc|D8|pc|D6|pg||pc|DJ|mc|7|'
  ),
  },
  {
    id: "board6-7nt",
    title: "Board 6 · 7NT by East, played to the last card",
    blurb: "A grand slam bid after a long relay auction and then lost — every one of the 52 cards is on record, so the grader can find the trick where it got away.",
    lin: (
    'pn|South,West,North,East|st||md|4SQJT2HKQT8D96CJ98,SA3HJ9643DAKJC753,S98764H752D3CQ642,SK5HADQT8'
    + '7542CAKT|rh||ah|Board 6|sv|e|mb|1D|mb|p|mb|1H|mb|p|mb|1N|an|Gazilli, 16+ HCP|mb|p|mb|2C|an|7+|mb'
    + '|p|mb|2D|mb|p|mb|3D|mb|p|mb|3N|mb|p|mb|4D|mb|p|mb|4H|mb|p|mb|4S|mb|p|mb|4N|mb|p|mb|5D|mb|p|mb|7N'
    + '|mb|p|mb|p|mb|p|pg||pc|HK|pc|H3|pc|H7|pc|HA|pg||pc|D2|pc|D6|pc|DA|pc|D3|pg||pc|DK|pc|H5|pc|D4|pc'
    + '|D9|pg||pc|DJ|pc|H2|pc|DQ|pc|HT|pg||pc|DT|pc|H8|pc|H4|pc|S4|pg||pc|D8|pc|S2|pc|H6|pc|S8|pg||pc|D'
    + '7|pc|C8|pc|H9|pc|S6|pg||pc|D5|pc|C9|pc|C3|pc|S7|pg||pc|SK|pc|ST|pc|S3|pc|S9|pg||pc|S5|pc|SJ|pc|S'
    + 'A|pc|C6|pg||pc|C5|pc|C4|pc|CK|pc|CJ|pg||pc|CA|pc|HQ|pc|C7|pc|C2|pg||pc|CT|pc|SQ|pc|HJ|pc|CQ|pg||'
  ),
  },
  {
    id: "practice6-3nt",
    title: "Board 6 · 3NT by North, down three",
    blurb: "From a teams practice, played out in full. Three tricks short — was it the contract, the line, or one card early on?",
    lin: (
    'pn|South,West,North,East|st||md|4S79TQH8TQD45TC349,S5JH35D28QKC258TA,S68H29JKAD67ACJQK,|rh||ah|B'
    + 'oard 6|sv|e|mb|p|mb|p|mb|2C|an|5+!c 10-13 not 5332|mb|d|mb|p|mb|2D!|an|guessing lebensohl|mb|p|m'
    + 'b|3N|mb|p|mb|p|mb|p|pc|S3|pc|S7|pc|SJ|pc|S6|pc|D2|pc|D6|pc|DJ|pc|D4|pc|D9|pc|DT|pc|DQ|pc|DA|pc|H'
    + '2|pc|H4|pc|HQ|pc|H5|pc|HT|pc|H3|pc|HA|pc|H6|pc|HK|pc|H7|pc|H8|pc|C8|pc|HJ|pc|S4|pc|D5|pc|C2|pc|H'
    + '9|pc|S2|pc|C3|pc|C5|pc|CK|pc|C7|pc|C4|pc|CA|pc|DK|pc|D7|pc|D3|pc|C9|pc|D8|pc|S8|pc|C6|pc|S9|pc|S'
    + '5|pc|CJ|pc|SK|pc|ST|pc|SA|pc|SQ|pc|CT|pc|CQ|pg||'
  ),
  },
  {
    id: "board14-1nt",
    title: "Board 14 · 1NT by West, made",
    blurb: "A quiet part-score: nine tricks played, then a claim for seven. A good one for asking whether the defence could have beaten it.",
    lin: (
    'pn|South,West,North,East|st||md|4SJ6432HJ752DCQJ83,SKQ7HAQ86D62CA765,SA5HT4DAKJ83CKT42|sv|o|rh||'
    + 'ah|Board 14|mb|p|mb|p|mb|1N|mb|p|mb|p|mb|p|pc|DK|pc|D4|pc|S2|pc|D2|pc|C4|pc|C9|pc|CJ|pc|C5|pc|C3'
    + '|pc|C6|pc|CT|pc|D5|pc|CK|pc|D7|pc|C8|pc|CA|pc|D6|pc|DA|pc|D9|pc|S6|pc|C2|pc|S8|pc|CQ|pc|C7|pc|S3'
    + '|pc|SK|pc|SA|pc|S9|pc|S5|pc|ST|pc|SJ|pc|SQ|pc|S7|pc|D3|pc|DT|pc|S4|mc|7|'
  ),
  },
  {
    id: "board5-2s",
    title: "Board 5 · 2♠ by South over a weak two",
    blurb: "A competitive part-score after a 2♥ opening and a 2♠ overcall; six tricks played before declarer claimed ten.",
    lin: (
    'pn|South,West,North,East|st||md|3SK8752HAT7DAQ7C94,SA64HJ4D9843CAK87,SQT9HK65DKJT6C532,SJ3HQ9832'
    + 'D52CQJT6|rh||ah|Board 5|sv|n|mb|p|mb|2H|mb|2S|mb|p|mb|p|mb|p|pg||pc|HJ|pc|HK|pc|H2|pc|H7|pg||pc|'
    + 'S9|pc|S3|pc|SK|pc|SA|pg||pc|CA|pc|C2|pc|CQ|pc|C4|pg||pc|C8|pc|C3|pc|CT|pc|C9|pg||pc|H3|pc|HT|pc|'
    + 'H4|pc|H5|pg||pc|S2|pc|S4|pc|SQ|pc|SJ|pg||mc|10|'
  ),
  },
  {
    id: "teams17-6c",
    title: "Board 17 · 6♣ by South, from a teams championship",
    blurb: "An international teams match: a thirty-two-call relay auction to a small slam, forty-one cards played, then a claim for all thirteen.",
    lin: (
    'pn|South,West,North,East|st||rh||ah|Board 17|md|3SAJ53HA2DAKCAQJ84,SKT4HKJ3DQ982C763,SHQ987DJT63'
    + 'CKT952,SQ98762HT654D754C|sv|o|mb|p|mb|p|mb|2C|mb|p|mb|2D!|an|waiting|mb|p|mb|2N|mb|p|mb|3C!|an|p'
    + 'uppet stayman|mb|p|mb|3D!|an|1 4 card major|mb|p|mb|3S!|an|hearts|mb|p|mb|3N|mb|p|mb|4C|mb|p|mb|'
    + '4D!|mb|p|mb|4S|mb|p|mb|4N|mb|p|mb|5C|an|1/4|mb|p|mb|5S!|mb|p|mb|6C|mb|p|mb|p|mb|p|pc|c3|pc|c5|pc'
    + '|s2|pc|c8|pg||pc|s3|pc|s4|pc|c2|pc|s6|pg||pc|d3|pc|d4|pc|dK|pc|d2|pg||pc|s5|pc|sT|pc|c9|pc|s8|pg'
    + '||pc|cT|pc|s7|pc|cJ|pc|c6|pg||pc|sJ|pc|sK|pc|cK|pc|s9|pg||pc|h7|pc|h4|pc|hA|pc|h3|pg||pc|cA|pc|c'
    + '7|pc|h8|pc|h5|pg||pc|cQ|pc|d8|pc|d6|pc|d5|pg||pc|sA|pc|hJ|pc|h9|pc|sQ|pg||pc|c4|mc|13|pg||'
  ),
  },
]
