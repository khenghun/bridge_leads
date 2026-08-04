// User-facing release notes, newest first.
//
// This is the changelog *players* read, so entries describe what changed for
// them — not how. Keep it free of module names, endpoints and test counts;
// ROADMAP.md and latest_updates.md are where the technical story lives.
//
// Dates are the date the work landed. Add a new entry at the top of the array
// whenever a release ships something a user would notice.

export type ChangeKind = 'new' | 'improved' | 'fixed'

export interface Change {
  kind: ChangeKind
  text: string
}

export interface Release {
  /** Version label, omitted for releases that were not a numbered version. */
  version?: string
  /** ISO date the work landed. */
  date: string
  title: string
  /** One line on why the release exists, shown under the title. */
  summary?: string
  changes: Change[]
}

export const KIND_LABEL: Record<ChangeKind, string> = {
  new: 'New',
  improved: 'Improved',
  fixed: 'Fixed',
}

export const RELEASES: Release[] = [
  {
    version: 'v2.1',
    date: '2026-08-04',
    title: 'Specific cards, and a phone-friendly app',
    summary:
      'Constraints could say how many cards and how good a suit was, but never '
      + 'which cards. Now they can — and the whole app is far easier to use on '
      + 'a phone.',
    changes: [
      {
        kind: 'new',
        text: 'Pin exact cards into a hand you cannot see — open ➕ Specific '
          + 'cards on any seat and type AK in the ♥ row to say that player holds '
          + '♥A and ♥K. The other twelve cards are still simulated around them, '
          + 'under whatever else you have set.',
      },
      {
        kind: 'new',
        text: 'Works in both tools, and agrees with your other constraints '
          + 'rather than sitting beside them — pinned honours count toward that '
          + 'seat’s point range and its suit grade, so asking for something '
          + 'contradictory tells you straight away instead of quietly returning '
          + 'nothing.',
      },
      {
        kind: 'improved',
        text: 'Impossible card assignments are caught as you type — a card you '
          + 'already hold, or the same card given to two players — instead of '
          + 'failing after you press Simulate.',
      },
      {
        kind: 'new',
        text: 'This page. Every release that changed something you can see, '
          + 'newest first.',
      },
      {
        kind: 'fixed',
        text: 'On a phone, the controls panel was stuck at a fixed height with '
          + 'its own near-invisible scrollbar, which put the deal-count slider — '
          + 'and the strain choices on the contract tab — effectively out of '
          + 'reach. It now flows down the page like everything else.',
      },
      {
        kind: 'fixed',
        text: 'Wide results tables no longer drag the whole page sideways. They '
          + 'scroll on their own, so the hand entry, constraint panels and '
          + 'buttons stay where you expect them.',
      },
      {
        kind: 'improved',
        text: 'On a phone, Simulate now stays pinned to the bottom of the '
          + 'screen rather than sitting a long scroll below the controls, your '
          + 'hand and three constraint panels.',
      },
      {
        kind: 'improved',
        text: 'Tapping a field no longer makes iPhones zoom the page in, number '
          + 'fields bring up the number pad, and card boxes are no longer '
          + 'autocorrected — typing KT932 now stays KT932.',
      },
      {
        kind: 'improved',
        text: 'Buttons, dropdowns and text fields are finger-sized on a phone, '
          + 'and the tabs no longer push the light-mode switch off the screen.',
      },
      {
        kind: 'fixed',
        text: 'The strain buttons on the contract tab were nearly invisible in '
          + 'dark mode. They now carry their suit colour, are larger, and clearly '
          + 'dim when you switch a strain off.',
      },
      {
        kind: 'improved',
        text: 'What the table columns mean, and what the two warning flags mean, '
          + 'are now written out under the tables — they used to live only in '
          + 'hover tooltips, which a touchscreen can never show.',
      },
      {
        kind: 'fixed',
        text: 'Opening a constraint box no longer squeezes the other two seats’ '
          + 'number fields into unreadable slivers.',
      },
    ],
  },
  {
    version: 'v2.0',
    date: '2026-08-03',
    title: 'Optimal Contract Calculator',
    summary:
      'A second tool, and the mirror image of the first: where do these two '
      + 'hands belong?',
    changes: [
      {
        kind: 'new',
        text: 'Enter your own hand plus what the auction told you about '
          + 'partner’s and the opponents’ hands, and every contract your '
          + 'side could be in is ranked by how it would actually score.',
      },
      {
        kind: 'new',
        text: 'Contracts are scored against a benchmark — the one you would '
          + 'otherwise be in — because that is how bidding decisions are really '
          + 'framed ("is 6♠ worth it over 4♠?"). You can change the benchmark and '
          + 'the table re-ranks instantly.',
      },
      {
        kind: 'new',
        text: 'Alongside the ranking: how often each contract makes, average '
          + 'tricks against tricks needed, and what it costs on the deals where '
          + 'it fails. A flag tells you when it matters which of you declares, '
          + 'and another warns when a contract’s edge rests on a handful of '
          + 'lucky layouts.',
      },
      {
        kind: 'new',
        text: 'A strain-by-level grid, a compare-two-contracts view, and sample '
          + 'deals split into the ones that make and the ones that fail.',
      },
      {
        kind: 'improved',
        text: 'The two tools now live in tabs. Switching between them keeps your '
          + 'results, so a simulation that took ten seconds is not thrown away.',
      },
    ],
  },
  {
    version: 'v1.2',
    date: '2026-08-03',
    title: 'Suit quality constraint',
    changes: [
      {
        kind: 'new',
        text: 'Grade one suit of one unseen hand as good or poor. Good means two '
          + 'of AKQ, or three of AKQJT — what a preempt or an overcall promises. '
          + 'It is the constraint an auction usually gives you, and one suit is '
          + 'all you can normally infer, so only one can be graded at a time.',
      },
      {
        kind: 'improved',
        text: 'Auctions that describe a suit now simulate far faster — about nine '
          + 'times quicker on a weak-two auction — because the deals are built to '
          + 'match instead of being generated and thrown away.',
      },
    ],
  },
  {
    version: 'v1.1',
    date: '2026-07-25',
    title: 'Compare two opening leads',
    changes: [
      {
        kind: 'new',
        text: 'Pick any two leads and see how they did against each other deal by '
          + 'deal: how often each one wins, draws and loses, plus the average '
          + 'swing between them.',
      },
      {
        kind: 'new',
        text: 'Filter the sample deals by outcome to look at just the deals where '
          + 'your choice would have cost you.',
      },
    ],
  },
  {
    version: 'v1.0',
    date: '2026-07-16',
    title: 'Opening Lead Simulator',
    summary:
      'The first release: which card should you lead? Built up over several '
      + 'rounds through mid-July 2026, and published on the web.',
    changes: [
      {
        kind: 'new',
        text: 'Enter the opening leader’s hand, the contract, and whatever the '
          + 'auction told you about the three hands you cannot see. The app deals '
          + 'thousands of consistent layouts, plays every candidate lead out '
          + 'perfectly on each one, and ranks the leads by matchpoints or IMPs — '
          + 'with the deals where your lead beats the contract shown as full '
          + 'four-hand diagrams.',
      },
      {
        kind: 'new',
        text: 'Describe the unseen hands by point range, suit lengths, or a shape '
          + 'covering several possible distributions. Demo auctions fill all of '
          + 'that in for you, so you need only enter your own hand — suit by '
          + 'suit, pasted in PBN, or dealt at random.',
      },
      {
        kind: 'new',
        text: 'Published at bridge-leads.icycookie.xyz over HTTPS, so there is '
          + 'nothing to install.',
      },
    ],
  },
]
