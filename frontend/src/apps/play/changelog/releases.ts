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
    version: 'v1.4',
    date: '2026-09-08',
    title: 'How sure is that grade?',
    unreleased: true,
    summary:
      'Every grade now says how sure it is, doubtful ones are graded on more '
      + 'deals, and Expert opponents is faster and right about dummy.',
    changes: [
      {
        kind: 'new',
        text: 'A grade is an average over sampled deals, and on a big-swing '
          + 'decision that average can move a lot from one sample to the '
          + 'next — the same play read as “good” or “suboptimal” depending '
          + 'on which deals happened to be dealt. Every grade now carries '
          + 'its own sampling error (hover a decision’s IMPs or Best column '
          + 'for the ± band), and a badge whose grade could read differently '
          + 'on another sample of the same size is marked with a dashed '
          + 'border and a “?”; each seat’s summary counts these marginal '
          + 'grades. And a decision that does not read clearly optimal — or '
          + 'whose grade is marginal — is automatically re-graded on three '
          + 'times the deals (the first sample kept and extended, never '
          + 'redrawn), so the deals go where the doubt is: on a typical hand '
          + 'about one decision in five is extended and the rest cost '
          + 'nothing extra. The switch is under the deals slider if you '
          + 'would rather grade everything at one count.',
      },
      {
        kind: 'fixed',
        text: 'When a defender was graded with Expert opponents on, a play '
          + 'declarer made from dummy was judged once and that single verdict '
          + 'was reused for every sampled deal — but the verdict depends on '
          + 'declarer’s hidden hand, which differs from deal to deal. On some '
          + 'hands every deal was thrown out (the grade fell back to the '
          + 'unfiltered sample and said so); on others every deal was waved '
          + 'through. Each deal is now judged on its own declarer hand, so a '
          + 'defender’s grade reflects what an expert declarer would actually '
          + 'have done on that deal. Declarer’s own grades were never affected.',
      },
      {
        kind: 'improved',
        text: 'Expert opponents, and Strict especially, runs faster: the plays '
          + 'most likely to rule a deal out are judged first, judgements that '
          + 'are already known are not repeated, and the solver is fed in '
          + 'bigger batches. And the opening lead is no longer second-guessed '
          + 'when the deals are filtered — leads are the Opening Lead '
          + 'Simulator’s business, and judging one cost as much as the rest of '
          + 'the hand while it almost never ruled a deal out. Each decision '
          + 'also starts from the deals the previous decision of the same seat '
          + 'kept, so a declarer’s later decisions reuse most of the earlier '
          + 'work. A strict run of a declarer’s hand now takes about a third '
          + 'of the time; the plain single-dummy grades are untouched.',
      },
    ],
  },
  {
    version: 'v1.3',
    date: '2026-09-01',
    title: 'Expert opponents',
    summary:
      'Let the opponents’ earlier plays shape the deals that are sampled — '
      + 'a card they did not play tells you something about what they hold.',
    changes: [
      {
        kind: 'new',
        text: 'A new Expert opponents switch. With it on, every sampled deal '
          + 'must also be one on which each earlier play by an opponent was a '
          + 'best play given what that opponent could see at the time — judged '
          + 'the same way your own cards are graded, from their seat, with the '
          + 'hands they could not see dealt out many ways. A defender who did '
          + 'not give partner a ruff when, from their seat, the ruff was there '
          + 'to find is taken not to hold that card. The grades move with the '
          + 'sample, the way a good player’s inference does.',
      },
      {
        kind: 'new',
        text: 'Each graded card says how many of the sampled deals passed that '
          + 'test, and the filter states its own bar: it drops a deal only when '
          + 'an opponent’s play is shown to be clearly worse than an alternative '
          + '— a missed ruff, not a matter of taste — and the bar tightens as '
          + 'you raise the deal count. When no deal at all passes, the card is '
          + 'graded as before and marked: the opponents probably erred earlier.',
      },
      {
        kind: 'new',
        text: 'A Strict option under Advanced judges every opponent decision, '
          + 'not only the ones that lost a trick on the sampled deal. It is '
          + 'several times slower and it is the only way to catch a play that '
          + 'happened to work — an anti-percentage guess that found the queen.',
      },
      {
        kind: 'improved',
        text: 'Slow analyses now arrive one decision at a time, so the first '
          + 'grades show within seconds while the rest are still being solved '
          + '— and a run the browser gave up on (a laptop that went to sleep, '
          + 'a tab left in the background) keeps what it had and offers '
          + 'Resume, which picks up where it stopped without redoing the '
          + 'finished decisions. Expert opponents is a much slower mode by '
          + 'nature — minutes per seat rather than a second — so the deal '
          + 'count switches to 60 when you turn it on.',
      },
    ],
  },
  {
    version: 'v1.2',
    date: '2026-09-01',
    title: 'What it cost in IMPs, and more example hands',
    summary:
      'Every decision is now priced in points and IMPs, not only tricks — '
      + 'and there are six real hands to start from.',
    changes: [
      {
        kind: 'new',
        text: 'Each graded card shows what it cost in IMPs beside the tricks, '
          + 'using the contract, the vulnerability and any double. A trick '
          + 'that only costs an overtrick and one that lets a game through '
          + 'both read "−1 trick"; now they read very differently. Points are '
          + 'in the tooltip, and every alternative in the options list carries '
          + 'its own score and IMPs.',
      },
      {
        kind: 'improved',
        text: 'The biggest-swings list and the pair summaries rank by IMPs, so '
          + 'the decision that actually decided the board comes first.',
      },
      {
        kind: 'improved',
        text: 'The optimal / good / suboptimal badge now listens to IMPs as '
          + 'well as tricks: a card that costs almost nothing on average but '
          + 'half an IMP or more is at best "good", and two IMPs or more is '
          + '"suboptimal". Tricks alone can no longer call a slam-losing card '
          + 'optimal.',
      },
      {
        kind: 'new',
        text: 'The upload screen now offers six example hands — a grand slam '
          + 'played out and lost, a 3NT down three, a quiet 1NT, a competitive '
          + 'part-score, a championship small slam — so you can see the grader '
          + 'at work before loading a hand of your own. Player names are '
          + 'replaced by seats throughout.',
      },
    ],
  },
  {
    version: 'v1.1',
    date: '2026-09-01',
    title: 'Analyze a pair, or the whole table',
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
