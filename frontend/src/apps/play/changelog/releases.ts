// The play solver's release notes, newest first — ITS OWN version line
// (v1.0, v1.1, …), separate from the lead/contract app's
// `apps/changelog/releases.ts`. This is the source of truth for the play
// solver's version numbers; `docs/play/ROADMAP.md` follows it.
//
// This is the changelog *players* read, so entries describe what changed for
// them — not how. Keep it free of module names, endpoints and test counts.
// Dates are the date the work landed. Add a new entry at the top whenever a
// release ships something a user would notice; mark it `unreleased` until it
// is deployed so the local build can track work in progress.

import type { Release } from '../../../components/Changelog'

export type { Change, ChangeKind, Release } from '../../../components/Changelog'
export { KIND_LABEL } from '../../../components/Changelog'

export const RELEASES: Release[] = [
  {
    version: 'v1.1',
    date: '2026-09-01',
    title: 'Analyze a pair, or the whole table',
    unreleased: true,
    summary:
      'Grade both members of a partnership in one go — or all four seats — '
      + 'and see whose decisions cost the most.',
    changes: [
      {
        kind: 'new',
        text: 'Three ways to analyze instead of one seat at a time: N/S, E/W, '
          + 'or the whole table. A pair is always graded as a pair — the '
          + 'declaring side through declarer (dummy’s cards are declarer’s '
          + 'decisions), the defending side through each defender in turn.',
      },
      {
        kind: 'new',
        text: 'Results arrive seat by seat, so the first grades appear as '
          + 'quickly as a single seat used to. Each pair gets its own summary '
          + 'of tricks given up.',
      },
      {
        kind: 'new',
        text: 'The whole-table view opens with the biggest swings: every '
          + 'decision that cost tricks, from any seat, worst first — click one '
          + 'to jump the table to that moment.',
      },
      {
        kind: 'improved',
        text: 'Constraints are now entered once per hand — what the bidding '
          + 'revealed about each player — and applied to every grade that '
          + 'could not see that hand. Because the real deal is known, the '
          + 'editor warns when a constraint would rule out the hand a player '
          + 'actually held.',
      },
      {
        kind: 'improved',
        text: 'The card table now follows dark mode instead of staying light '
          + 'on its own; the light-mode look is unchanged.',
      },
    ],
  },
  {
    version: 'v1.0',
    date: '2026-08-27',
    title: 'Replay a hand and grade every card',
    summary:
      'The first version of the play solver: load a hand you played, step '
      + 'through it, and see what each decision cost — judged by what you '
      + 'could see at the time, not by hindsight.',
    changes: [
      {
        kind: 'new',
        text: 'Load a completed hand as a BBO .lin file — drop it on the page, '
          + 'paste the text, or start from the built-in example. The file is '
          + 'read in your browser; only the deal, the contract and the cards '
          + 'played are sent for solving, never the player names.',
      },
      {
        kind: 'new',
        text: 'Step through the play card by card or trick by trick (arrow '
          + 'keys work), with the current trick laid out on the table and '
          + 'played cards struck through in each hand.',
      },
      {
        kind: 'new',
        text: 'Pick a seat and press Analyze: every decision that seat made '
          + 'is graded optimal, good or suboptimal against the best card '
          + 'available, with the tricks each choice was worth. Declarer is '
          + 'graded on both hands; forced plays are marked and left alone.',
      },
      {
        kind: 'new',
        text: 'Grades are "best given what you could see": the two hands the '
          + 'player could not see are dealt out many ways, consistent with '
          + 'every card already played, and each option is solved on all of '
          + 'them. Switch to double-dummy to see what was best with all four '
          + 'hands open.',
      },
      {
        kind: 'new',
        text: 'Expand any decision to see every legal card ranked, and click '
          + 'it to jump the table to that moment. Optional constraints on the '
          + 'unseen hands — points, suit lengths, shapes, specific cards — '
          + 'let you tell the solver what the bidding had revealed.',
      },
    ],
  },
]
