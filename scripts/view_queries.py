#!/usr/bin/env python3
"""Read the production query log.

The backend writes one SQLite row per simulation (see `app/common/querylog.py`):
timestamp, tool, and the request body as JSON. That raw JSON is unreadable at a
glance, so this decodes each row into a one-line summary of what was actually
asked — contract, hand, deal count, and any constraints.

The log lives on the VPS at /opt/bridge_leads/data/queries.db. By default this
copies it down over scp and reads the copy, so nothing runs against the live
file and a locked or busy database on the server cannot affect you.

Stdlib only — no install, any python3 will do.

    # from the VPS (default host comes from BRIDGE_VPS or --host)
    python scripts/view_queries.py --host deploy@203.0.113.10
    python scripts/view_queries.py --host deploy@203.0.113.10 --summary

    # against a file you already have
    python scripts/view_queries.py --db ./queries.db --since 7d --tool lead
    python scripts/view_queries.py --db ./queries.db --json > queries.jsonl
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone

REMOTE_DB = '/opt/bridge_leads/data/queries.db'
SUIT = {'S': '♠', 'H': '♥', 'D': '♦', 'C': '♣', 'N': 'NT'}
SEAT_ORDER = ['N', 'E', 'S', 'W']


# --- getting hold of the database -----------------------------------------

def fetch_remote(host: str, remote_path: str) -> str:
    """scp the log to a temp file and return the local path."""
    if not shutil.which('scp'):
        sys.exit('scp not found on PATH — copy the file down yourself and use --db.')
    tmp = os.path.join(tempfile.mkdtemp(prefix='querylog-'), 'queries.db')
    src = f'{host}:{remote_path}'
    print(f'fetching {src} ...', file=sys.stderr)
    result = subprocess.run(['scp', '-q', src, tmp])
    if result.returncode != 0:
        sys.exit(f'scp failed (exit {result.returncode}). Check SSH access to {host}.')
    return tmp


def load_rows(db_path: str):
    if not os.path.exists(db_path):
        sys.exit(f'no such database: {db_path}')
    con = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    try:
        con.row_factory = sqlite3.Row
        try:
            cur = con.execute('SELECT id, ts, tool, payload FROM queries ORDER BY id')
        except sqlite3.OperationalError as e:
            sys.exit(f'{db_path} does not look like a query log ({e}).')
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


# --- decoding one query into something readable ---------------------------

def contract_label(level, strain) -> str:
    return f'{level}{SUIT.get(strain, strain)}'


def describe_constraints(c: dict) -> str:
    """Collapse the constraint block into the shortest honest description."""
    if not c:
        return ''
    parts = []
    for seat in SEAT_ORDER:
        bits = []
        lo_hi = (c.get('hcp') or {}).get(seat)
        if lo_hi:
            bits.append(f'{lo_hi[0]}-{lo_hi[1]} HCP')
        for suit, rng in ((c.get('suit_length') or {}).get(seat) or {}).items():
            bits.append(f'{rng[0]}-{rng[1]}{SUIT.get(suit, suit)}')
        for suit, level in ((c.get('quality') or {}).get(seat) or {}).items():
            bits.append(f'{level} {SUIT.get(suit, suit)}')
        cards = (c.get('fixed_cards') or {}).get(seat)
        if cards:
            bits.append('holds ' + ''.join(
                SUIT.get(x[0], x[0]) + x[1:] for x in cards))
        if (c.get('shapes') or {}).get(seat):
            bits.append('shape')
        if bits:
            parts.append(f'{seat} {", ".join(bits)}')
    return '; '.join(parts)


def decode(row: dict) -> dict:
    """One log row -> {ts, tool, what, hand, deals, constraints}."""
    try:
        p = json.loads(row['payload'])
    except (ValueError, TypeError):
        p = {}
    out = {'id': row['id'], 'ts': row['ts'], 'tool': row['tool'],
           'constraints': describe_constraints(p.get('constraints') or {})}
    if row['tool'] == 'lead':
        pen = p.get('penalty', 'none')
        out['what'] = (contract_label(p.get('level', '?'), p.get('strain', '?'))
                       + f" by {p.get('declarer', '?')}"
                       + ('' if pen == 'none' else f' {pen}')
                       + ('' if p.get('vul', 'none') == 'none' else f" vul {p['vul']}"))
        out['hand'] = p.get('leader_hand', '')
        out['deals'] = p.get('num_simulations')
    else:
        strains = p.get('strains') or []
        # Only worth mentioning when the user narrowed it.
        shown = ('' if len(strains) >= 5
                 else ' ' + ''.join(SUIT.get(s, s) for s in strains))
        out['what'] = (f"seat {p.get('seat', '?')}{shown}"
                       + ('' if p.get('vul', 'none') == 'none' else f" vul {p['vul']}"))
        out['hand'] = p.get('hand', '')
        out['deals'] = p.get('num_deals')
    return out


# --- filtering -------------------------------------------------------------

def parse_since(text: str) -> str:
    """'7d' / '12h' / '30m' / an ISO date -> an ISO-8601 UTC cutoff string.

    The stored ts is ISO-8601 UTC, so a plain string compare is a valid time
    compare — no parsing per row."""
    m = re.fullmatch(r'(\d+)([dhm])', text.strip().lower())
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {'d': timedelta(days=n), 'h': timedelta(hours=n),
                 'm': timedelta(minutes=n)}[unit]
        return (datetime.now(timezone.utc) - delta).strftime('%Y-%m-%dT%H:%M:%SZ')
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
        return text + 'T00:00:00Z'
    sys.exit(f"--since wants 7d / 12h / 30m or YYYY-MM-DD, got {text!r}")


# --- output ----------------------------------------------------------------

def print_recent(rows, limit):
    if not rows:
        print('no queries match.')
        return
    shown = rows[-limit:] if limit else rows
    width = max(len(r['what']) for r in shown)
    for r in shown:
        line = (f"{r['ts'][:10]} {r['ts'][11:19]}  {r['tool']:<8}  "
                f"{r['what']:<{width}}  {r['hand']:<17}  {str(r['deals'] or ''):>4}")
        if r['constraints']:
            line += f"  | {r['constraints']}"
        print(line)
    total = len(rows)
    print(f'\n{len(shown)} of {total} quer{"y" if total == 1 else "ies"} shown'
          + (f" (from {rows[0]['ts'][:10]} to {rows[-1]['ts'][:10]})" if total else ''))


def print_summary(rows):
    if not rows:
        print('no queries match.')
        return
    by_day = Counter(r['ts'][:10] for r in rows)
    by_tool = Counter(r['tool'] for r in rows)
    by_hour = Counter(r['ts'][11:13] for r in rows)

    print(f"{len(rows)} queries, {rows[0]['ts'][:10]} to {rows[-1]['ts'][:10]}\n")

    print('by tool')
    for tool, n in by_tool.most_common():
        print(f'  {tool:<10} {n:>6}  {100 * n / len(rows):5.1f}%')

    print('\nby day')
    peak = max(by_day.values())
    for day in sorted(by_day):
        n = by_day[day]
        print(f'  {day}  {n:>5}  {"#" * max(1, round(24 * n / peak))}')

    print('\nbusiest hours (UTC)')
    for hour, n in sorted(by_hour.most_common(5)):
        print(f'  {hour}:00  {n:>5}')

    contracts = Counter(r['what'] for r in rows if r['tool'] == 'lead')
    if contracts:
        print('\nmost-asked contracts (lead tool)')
        for what, n in contracts.most_common(8):
            print(f'  {what:<18} {n:>5}')

    constrained = sum(1 for r in rows if r['constraints'])
    print(f'\n{constrained} of {len(rows)} queries set at least one constraint '
          f'({100 * constrained / len(rows):.0f}%)')


def main():
    ap = argparse.ArgumentParser(
        description='View the production query log (one row per simulation).',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  export BRIDGE_VPS=deploy@203.0.113.10
  view_queries.py                          40 most recent, decoded
  view_queries.py --summary                counts by tool / day / hour
  view_queries.py --since 7d --tool lead   last week's opening-lead queries
  view_queries.py --limit 0                everything
  view_queries.py --db ./queries.db        a file you already copied down
  view_queries.py --json | jq .            decoded rows, for your own filtering

'no queries match.' means the log is there and empty — nobody has used the
app since logging started. That is an answer, not an error.""")
    src = ap.add_mutually_exclusive_group()
    src.add_argument('--db', help='path to a local queries.db')
    src.add_argument('--host', default=os.environ.get('BRIDGE_VPS'),
                     help='ssh target to copy the log from, e.g. deploy@203.0.113.10 '
                          '(defaults to $BRIDGE_VPS)')
    ap.add_argument('--remote-path', default=REMOTE_DB,
                    help=f'path on the server (default {REMOTE_DB})')
    ap.add_argument('--since', help='only queries newer than 7d / 12h / 30m / YYYY-MM-DD')
    ap.add_argument('--tool', choices=['lead', 'contract'], help='only this tool')
    ap.add_argument('--limit', type=int, default=40,
                    help='most recent N (default 40; 0 = all)')
    ap.add_argument('--summary', action='store_true',
                    help='counts by tool/day/hour instead of the query list')
    ap.add_argument('--json', action='store_true',
                    help='decoded rows as JSON lines, for your own filtering')
    args = ap.parse_args()

    if args.db:
        db_path = args.db
    elif args.host:
        db_path = fetch_remote(args.host, args.remote_path)
    else:
        ap.error('give --db for a local file, or --host / $BRIDGE_VPS to fetch it')

    rows = [decode(r) for r in load_rows(db_path)]
    if args.tool:
        rows = [r for r in rows if r['tool'] == args.tool]
    if args.since:
        cutoff = parse_since(args.since)
        rows = [r for r in rows if r['ts'] >= cutoff]

    if args.json:
        for r in rows:
            print(json.dumps(r))
    elif args.summary:
        print_summary(rows)
    else:
        print_recent(rows, args.limit)


if __name__ == '__main__':
    main()
