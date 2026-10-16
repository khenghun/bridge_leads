/* KK Relay (McCallum & Woolsey, 2021) – responder's shape-showing tree after a 1♣ opening.
 *
 * Built from the book's rules rather than typed in by hand, so that every "continuations
 * as with ..." in the Shape-Showing Summary (printed pp. 133-141) and the generic ESS tables
 * in Generic Distribution Drills (pp. 143-149) are expanded consistently.
 *
 * Conventions used by the book:
 *   - Asker (the 1♣ opener) always relays with the next step.
 *   - Suit order for showing suits: Spades, Hearts, Clubs, Diamonds ("Some Husbands Can't Dance").
 *   - Shortness is shown HEL: High-short, Equal-short, Low-short, measured among the suits
 *     NOT yet shown as long, in rank order (♠ > ♥ > ♦ > ♣).
 *   - Exact shape is written a=b=c=d  (♠=♥=♦=♣).
 *
 * Works in the browser (window.KKRelay) and in Node (module.exports).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.KKRelay = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const RANK = ['S', 'H', 'D', 'C'];               // rank order, high to low
  const SYM = { S: '♠', H: '♥', D: '♦', C: '♣', NT: 'NT' };
  const NAME = { S: 'spades', H: 'hearts', D: 'diamonds', C: 'clubs' };
  const STRAINS = ['C', 'D', 'H', 'S', 'NT'];       // bidding order within a level

  // ---- bid arithmetic -------------------------------------------------------------
  function parseBid(b) { const m = /^([1-7])(C|D|H|S|NT)$/.exec(b); return { level: +m[1], strain: m[2] }; }
  function bidIndex(b) { const { level, strain } = parseBid(b); return (level - 1) * 5 + STRAINS.indexOf(strain); }
  function bidFromIndex(i) { return (Math.floor(i / 5) + 1) + STRAINS[i % 5]; }
  function nextStep(b) { return bidFromIndex(bidIndex(b) + 1); }
  function stepsFrom(start, n) { const out = []; let i = bidIndex(start); for (let k = 0; k < n; k++) out.push(bidFromIndex(i + k)); return out; }
  function pretty(b) { const { level, strain } = parseBid(b); return level + SYM[strain]; }

  // ---- shape helpers --------------------------------------------------------------
  function shape(counts) { return RANK.map(s => counts[s]).join('='); }
  function remaining(...known) { return RANK.filter(s => !known.includes(s)); }
  function generic(counts) { return RANK.map(s => counts[s]).sort((a, b) => b - a).join('-'); }
  function node(bid, label, extra) { return Object.assign({ bid, label }, extra || {}); }
  function leaf(bid, label, counts, gen) {
    const g = gen || generic(counts);
    return node(bid, label + ' — generic ' + g + ', so exactly ' + shape(counts), { shape: shape(counts), generic: g, counts });
  }
  // Attach children: Asker relays with next step after `parent.bid`, then Teller bids `children`.
  function withChildren(parent, children) { parent.relay = nextStep(parent.bid); parent.children = children; return parent; }
  // Assign consecutive bids starting at `start` to a list of [label, counts] pairs.
  function series(start, items) { return stepsFrom(start, items.length).map((b, i) => leaf(b, items[i][0], items[i][1], items[i][2])); }

  // ---- ONE-SUITER (long suit L; three remaining suits hi/mid/lo) ------------------------
  // Unique shortness ESS, starting at the Pivot Point 3♦: 5-3-3-2, 6-3-3-1, 7-2-3-1, 7-3-2-1, 7-3-3-0
  function oneSuiterESS(L, short, start, tag) {
    const [r1, r2] = remaining(L, short);           // r1 higher ranking than r2
    const c = (l, s, a, b) => ({ [L]: l, [short]: s, [r1]: a, [r2]: b });
    return series(start, [
      [tag + '5-3-3-2', c(5, 2, 3, 3)],
      [tag + '6-3-3-1', c(6, 1, 3, 3)],
      [tag + '7-2-3-1 (doubleton higher ranking than tripleton)', c(7, 1, 2, 3)],
      [tag + '7-3-2-1 (tripleton higher ranking than doubleton)', c(7, 1, 3, 2)],
      [tag + '7-3-3-0', c(7, 0, 3, 3)],
    ]);
  }
  function oneSuiter(L) {
    const [hi, mid, lo] = remaining(L);
    const c = (a, b, d) => ({ [L]: 6, [hi]: a, [mid]: b, [lo]: d });
    const n = NAME[L];
    return [
      withChildren(node('2S', `One-suiter (${n}): high-short (short ${NAME[hi]}), or 6-3-2-2 with high doubleton`), [
        withChildren(node('3C', `6-3-2-2 with high doubleton (${NAME[hi]} doubleton)`), [
          leaf('3H', '6-2-2-3 (doubletons in the two highest-ranking suits)', c(2, 2, 3), '6-2-2-3'),
          leaf('3S', '6-2-3-2 (doubletons in highest and lowest-ranking suits)', c(2, 3, 2), '6-2-3-2'),
        ]),
        ...oneSuiterESS(L, hi, '3D', `High-short (${NAME[hi]}): `),
      ]),
      withChildren(node('2NT', `One-suiter (${n}): middle-short (short ${NAME[mid]})`),
        oneSuiterESS(L, mid, '3D', `Middle-short (${NAME[mid]}): `)),
      withChildren(node('3C', `One-suiter (${n}): equal-short — 7-2-2-2, or 6-3-2-2 not high doubleton`), [
        leaf('3H', '7-2-2-2', { [L]: 7, [hi]: 2, [mid]: 2, [lo]: 2 }, '7-2-2-2'),
        leaf('3S', '6-3-2-2 (doubletons in the two lowest-ranking suits)', c(3, 2, 2), '6-3-2-2'),
      ]),
      ...oneSuiterESS(L, lo, '3D', `One-suiter (${n}), low-short (${NAME[lo]}): `),
    ];
  }

  // ---- SHORT TWO-SUITER (5+ in `five`, exactly 4 in `four`) ------------------------
  function s2sESS(five, four, short, start, tag) {
    const other = remaining(five, four, short)[0];
    const c = (l, s, o) => ({ [five]: l, [four]: 4, [short]: s, [other]: o });
    return series(start, [
      [tag + '5-4-3-1', c(5, 1, 3)],
      [tag + '6-4-2-1', c(6, 1, 2)],
      [tag + '6-4-3-0', c(6, 0, 3)],
      [tag + '7-4-2-0', c(7, 0, 2)],
    ]);
  }
  function shortTwoSuiter(five, four, desc) {
    const [hi, lo] = remaining(five, four);
    const d = desc + ': ';
    return [
      withChildren(node('2NT', d + `high-short (short ${NAME[hi]})`), s2sESS(five, four, hi, '3D', `High-short (${NAME[hi]}): `)),
      leaf('3C', d + 'equal-short, 5-4-2-2 (assumed; the rare 7-4-1-1 "Swan" is revealed later)',
        { [five]: 5, [four]: 4, [hi]: 2, [lo]: 2 }, '5-4-2-2'),
      ...s2sESS(five, four, lo, '3D', d + `low-short (${NAME[lo]}): `),
    ];
  }

  // ---- LONG TWO-SUITER (5+ in both a and b) ------------------------------------------
  function longTwoSuiter(a, b, desc) {
    const [hiL, loL] = RANK.filter(s => s === a || s === b);   // higher / lower ranking long suit
    const [hi, lo] = remaining(a, b);
    const ess = (short, start, tag) => {
      const other = remaining(a, b, short)[0];
      const c = (x, y, s, o) => ({ [hiL]: x, [loL]: y, [short]: s, [other]: o });
      return series(start, [
        [tag + '5-5-2-1', c(5, 5, 1, 2)],
        [tag + '5-5-3-0', c(5, 5, 0, 3)],
        [tag + '5-6-2-0 (5-card suit higher ranking)', c(5, 6, 0, 2), '5-6-2-0'],
        [tag + '6-5-2-0 (6-card suit higher ranking)', c(6, 5, 0, 2), '6-5-2-0'],
      ]);
    };
    const d = desc + ': ';
    return [
      withChildren(node('3C', d + `high-short (short ${NAME[hi]})`), ess(hi, '3H', `High-short (${NAME[hi]}): `)),
      withChildren(node('3D', d + 'equal-short (1-1 in the other suits)'), [
        leaf('3S', '5-6-1-1 (5-card suit higher ranking)', { [hiL]: 5, [loL]: 6, [hi]: 1, [lo]: 1 }, '5-6-1-1'),
        leaf('3NT', '6-5-1-1 (6-card suit higher ranking)', { [hiL]: 6, [loL]: 5, [hi]: 1, [lo]: 1 }, '6-5-1-1'),
      ]),
      ...ess(lo, '3H', d + `low-short (${NAME[lo]}): `),
    ];
  }

  // ---- THREE-SUITER (4-4-4-1 or 5-4-4-0) ---------------------------------------------
  function threeSuiter(shortMajor) {
    const [hi, lo] = shortMajor ? ['S', 'H'] : ['D', 'C'];
    const desc = shortMajor ? 'Three-suiter, short major' : 'Three-suiter, short minor';
    const ess = (short, start, tag) => {
      const [L1, L2, L3] = remaining(short);         // the three long suits, high to low
      const c = (s, x, y, z) => ({ [short]: s, [L1]: x, [L2]: y, [L3]: z });
      return series(start, [
        [tag + '4-4-4-1 (small singleton)', c(1, 4, 4, 4)],
        [tag + '4-4-5-0 (5-card suit lowest ranking)', c(0, 4, 4, 5), '4-4-5-0'],
        [tag + '4-5-4-0 (5-card suit middle ranking)', c(0, 4, 5, 4), '4-5-4-0'],
        [tag + '5-4-4-0 (5-card suit highest ranking)', c(0, 5, 4, 4), '5-4-4-0'],
      ]);
    };
    const one = s => Object.fromEntries(RANK.map(x => [x, x === s ? 1 : 4]));
    return [
      withChildren(node('2NT', desc + `: high-short (short ${NAME[hi]})`), ess(hi, '3D', `High-short (${NAME[hi]}): `)),
      withChildren(node('3C', desc + ': 4-4-4-1 with a singleton honor (A, K or Q)'), [
        leaf('3H', `high-short, singleton ${NAME[hi]} honor`, one(hi), '4-4-4-1'),
        leaf('3S', `low-short, singleton ${NAME[lo]} honor`, one(lo), '4-4-4-1'),
      ]),
      ...ess(lo, '3D', desc + `, low-short (${NAME[lo]}): `),
    ];
  }

  // ---- BALANCED (4-3-3-3 / 4-4-3-2) -------------------------------------------------------
  // Teller's doubleton is shown by bidding it: 3♦ = ♦, 3♥ = ♥, 3♠ = ♠, 3NT = ♣.
  function balanced(prefix, fifteenPlus) {
    const p = prefix ? prefix + ': ' : '';
    const sh = (s, h, d, c) => ({ S: s, H: h, D: d, C: c });
    const dbl = (label, shapes) => series('3D', [
      ['doubleton diamond, ' + label[0], shapes[0], '4-4-3-2'],
      ['doubleton heart, ' + label[1], shapes[1], '4-4-3-2'],
      ['doubleton spade, ' + label[2], shapes[2], '4-4-3-2'],
      ['doubleton club, ' + label[3], shapes[3], '4-4-3-2'],
    ]);
    const out = [
      withChildren(node('2S', p + '4-4-3-2 with two suits of the same color, or 4-3-3-3 with a 4-card major'), [
        withChildren(node('3C', '4-3-3-3 with a 4-card major'), [
          leaf('3H', '4 hearts', sh(3, 4, 3, 3), '4-3-3-3'),
          leaf('3S', '4 spades', sh(4, 3, 3, 3), '4-3-3-3'),
        ]),
        ...dbl(['so the black suits', 'so the black suits', 'so the red suits', 'so the red suits'],
          [sh(4, 3, 2, 4), sh(4, 2, 3, 4), sh(2, 4, 4, 3), sh(3, 4, 4, 2)]),
      ]),
      withChildren(node('2NT', p + '4-4-3-2 with two suits of the same rank (both majors or both minors)'),
        dbl(['so both majors', 'so both minors', 'so both minors', 'so both majors'],
          [sh(4, 4, 2, 3), sh(3, 2, 4, 4), sh(2, 3, 4, 4), sh(4, 4, 3, 2)])),
      withChildren(node('3C', p + '4-3-3-3 with a 4-card minor'), [
        leaf('3H', '4 clubs', sh(3, 3, 3, 4), '4-3-3-3'),
        leaf('3S', '4 diamonds', sh(3, 3, 4, 3), '4-3-3-3'),
      ]),
      ...dbl([p + '4-4-3-2 two suits same shape: the rounded suits', p + '4-4-3-2 two suits same shape: the pointed suits',
              p + '4-4-3-2 two suits same shape: the rounded suits', p + '4-4-3-2 two suits same shape: the pointed suits'],
        [sh(3, 4, 2, 4), sh(4, 2, 4, 3), sh(2, 4, 3, 4), sh(4, 3, 4, 2)]),
    ];
    (function mark(list) { list.forEach(n => { n.kind = fifteenPlus ? 'balanced15' : 'balanced'; if (n.children) mark(n.children); }); })(out);
    return out;
  }

  // ---- the full tree after 1♣ --------------------------------------------------------------
  function buildTree() {
    const s2s = (five, four, d) => shortTwoSuiter(five, four, d);
    const children = [
      node('1D', 'Any 0–8 HCP (negative)', { terminal: true }),

      withChildren(node('1H', '4+ spades, 9+ HCP, unbalanced (one-suiter, two-suiter with spades, or three-suiter short minor)'), [
        withChildren(node('1NT', 'Also 4+ hearts: two-suiter spades & hearts, or three-suiter short minor'), [
          withChildren(node('2D', 'Three-suiter, short minor (so 4-4 or 5-4 in the majors)'), [
            node('2S', 'Specialty sequence: semi-solid suit (Chapter 16)', { terminal: true }),
            ...threeSuiter(false),
          ]),
          withChildren(node('2H', 'Reverser: 4 spades, 5+ hearts (short two-suiter)'), s2s('H', 'S', 'S2S 4♠ + 5+♥')),
          withChildren(node('2S', 'Long two-suiter: 5+ spades, 5+ hearts'), longTwoSuiter('S', 'H', 'L2S ♠ + ♥')),
          ...s2s('S', 'H', 'S2S 5+♠ + 4♥ (non-Reverser)'),
        ]),
        withChildren(node('2C', 'Also clubs: two-suiter spades & clubs'), [
          withChildren(node('2H', 'Reverser: 4 spades, 5+ clubs'), s2s('C', 'S', 'S2S 4♠ + 5+♣')),
          withChildren(node('2S', 'Long two-suiter: 5+ spades, 5+ clubs'), longTwoSuiter('S', 'C', 'L2S ♠ + ♣')),
          ...s2s('S', 'C', 'S2S 5+♠ + 4♣ (non-Reverser)'),
        ]),
        withChildren(node('2D', 'Also diamonds, non-Reverser: 5+ spades, 4+ diamonds'), [
          withChildren(node('2S', 'Long two-suiter: 5+ spades, 5+ diamonds'), longTwoSuiter('S', 'D', 'L2S ♠ + ♦')),
          ...s2s('S', 'D', 'S2S 5+♠ + 4♦ (non-Reverser)'),
        ]),
        withChildren(node('2H', 'Reverser: 4 spades, 5+ diamonds'), s2s('D', 'S', 'S2S 4♠ + 5+♦')),
        ...oneSuiter('S'),
      ]),

      withChildren(node('1S', '4+ hearts, fewer than 4 spades, 9+ HCP, unbalanced'), [
        withChildren(node('2C', 'Also clubs: two-suiter hearts & clubs'), [
          withChildren(node('2H', 'Reverser: 4 hearts, 5+ clubs'), s2s('C', 'H', 'S2S 4♥ + 5+♣')),
          withChildren(node('2S', 'Long two-suiter: 5+ hearts, 5+ clubs'), longTwoSuiter('H', 'C', 'L2S ♥ + ♣')),
          ...s2s('H', 'C', 'S2S 5+♥ + 4♣ (non-Reverser)'),
        ]),
        withChildren(node('2D', 'Also diamonds, non-Reverser: 5+ hearts, 4+ diamonds'), [
          withChildren(node('2S', 'Long two-suiter: 5+ hearts, 5+ diamonds'), longTwoSuiter('H', 'D', 'L2S ♥ + ♦')),
          ...s2s('H', 'D', 'S2S 5+♥ + 4♦ (non-Reverser)'),
        ]),
        withChildren(node('2H', 'Reverser: 4 hearts, 5+ diamonds'), s2s('D', 'H', 'S2S 4♥ + 5+♦')),
        ...oneSuiter('H'),
      ]),

      withChildren(node('1NT', '5+ clubs, no 4-card major, 9+ HCP, unbalanced (or three-suiter short major)'), [
        withChildren(node('2D', 'Also diamonds: 5+ clubs, 4+ diamonds'), [
          withChildren(node('2S', 'Long two-suiter: 5+ clubs, 5+ diamonds'), longTwoSuiter('C', 'D', 'L2S ♣ + ♦')),
          ...s2s('C', 'D', 'S2S 5+♣ + 4♦'),
        ]),
        withChildren(node('2H', 'Three-suiter, short major (so 4-4 or 5-4 in the minors)'), threeSuiter(true)),
        ...oneSuiter('C'),
      ]),

      withChildren(node('2C', '5+ diamonds, no 4-card major, fewer than 5 clubs, 9+ HCP, unbalanced'), [
        withChildren(node('2H', '5+ diamonds, 4 clubs (short two-suiter)'), s2s('D', 'C', 'S2S 5+♦ + 4♣')),
        ...oneSuiter('D'),
      ]),

      withChildren(node('2D', 'Balanced (4-3-3-3 or 4-4-3-2), 9–11 or 15+ HCP'), balanced('', true)),
      node('2H', 'Specialty sequence: solid suit (Chapter 16)', { terminal: true }),
      ...balanced('Balanced 12–14 HCP', false),
    ];
    return addZooms({ bid: '1C', label: 'Strong, artificial, 16+ HCP', relay: null, children });
  }


  // ---- End of the Line (Chapter 12): Zooms and Super-Positives ---------------------------
  // In every group of sibling ESS calls the highest one is the End-of-Line (EOL).
  //  - EOL 3♠ : 3NT = same shape, 3+ controls (less than a Super-Positive); 4♣/4♦/4♥ = 4/5/6 controls.
  //  - EOL 3NT: 4♣/4♦/4♥ = the 3NT shape with 4/5/6 controls (Super-Positive: 4 controls & 13+ HCP, or 5+ controls).
  //  - EOL 4♣ : 4♦/4♥/4♠ = the shape 3NT would have shown, with 4/5/6 controls (3NT is passable, 4♣ is forcing).
  //  Balanced hands: 9–11 and 12–14 are limited, so only the 3♠→3NT zoom (3+ controls) applies and 12–14 never bids
  //  past 3NT. After 2♦ a 15+ hand must not bid 3NT, so from a 3♠ or 3NT EOL it bids 4♣+ = 4/5/6/7/8 controls.
  function addZooms(tree) {
    (function rec(n) {
      if (!n.children) return;
      n.children.forEach(rec);
      const leaves = n.children.filter(c => c.shape && !c.zoom);
      if (!leaves.length) return;
      const eol = leaves.reduce((a, b) => bidIndex(a.bid) > bidIndex(b.bid) ? a : b);
      if (bidIndex(eol.bid) !== Math.max(...n.children.map(c => bidIndex(c.bid)))) return;
      const kind = eol.kind || 'unbalanced';
      const z = (bid, src, text) => node(bid, 'Zoom: ' + src.shape + ' (as ' + pretty(src.bid) + '), ' + text,
        { shape: src.shape, generic: src.generic, counts: src.counts, zoom: true, kind: src.kind });
      const sp = (src, start, label, n) => stepsFrom(start, n || 4).map((b, i) => z(b, src, label + (4 + i) + ' controls' + (i === 0 && label.indexOf('15+') < 0 ? ' (Super-Positive: 13+ HCP, or any 5+ controls)' : '')));
      if (eol.bid === '3S') {
        // Balanced: 3NT after the 3♠ EOL shows 3+ controls (9–11 or 12–14); after 2♦ a 15+ hand bids past 3NT showing controls from 4.
        if (kind === 'unbalanced') {
          n.children.push(z('3NT', eol, '3+ controls, less than a Super-Positive'));
          n.children.push(...sp(eol, '4C', 'Super-Positive, '));
        } else {
          n.children.push(z('3NT', eol, (kind === 'balanced15' ? '9–11 HCP, ' : '') + '3+ controls (3♠ would show 0–2)'));
          if (kind === 'balanced15') n.children.push(...sp(eol, '4C', '15+ HCP, ', 5));   // Ch 14 p. 234: 2♦-2♠-3♣-4♦ = 4=3=3=3, 15+, 5 controls
        }
      } else if (eol.bid === '3NT') {
        if (kind === 'unbalanced') n.children.push(...sp(eol, '4C', 'Super-Positive, '));
        if (kind === 'balanced15') n.children.push(...sp(eol, '4C', '15+ HCP, ', 5));
      } else if (eol.bid === '4C') {
        const nt = leaves.find(c => c.bid === '3NT');
        if (nt && kind === 'unbalanced') n.children.push(...sp(nt, '4D', 'Super-Positive, ', 3));
      }
    })(tree);
    return tree;
  }

  // Walk Teller's bids from the root; returns the node reached (or null) and how far it got.
  function walk(tree, tellerBids) {
    let cur = tree; const path = [];
    for (const b of tellerBids) {
      if (!cur.children) break;
      const nxt = cur.children.find(c => c.bid === b);
      if (!nxt) return { node: null, path, failedAt: b };
      cur = nxt; path.push(nxt);
    }
    return { node: cur, path };
  }
  function leaves(tree) { const out = []; (function rec(n, p) { const q = p.concat(n); if (n.children) n.children.forEach(c => rec(c, q)); else out.push(q); })(tree, []); return out.map(p => p.slice(1)); }

  return { RANK, SYM, NAME, STRAINS, parseBid, bidIndex, bidFromIndex, nextStep, pretty, shape, buildTree, walk, leaves };
});
