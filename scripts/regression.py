#!/usr/bin/env python
"""Helper for the `test-deployed` skill (.claude/skills/test-deployed/).

    python scripts/regression.py coverage            # releases vs checklists; exit 1 if a release has no checks
    python scripts/regression.py urls [--base URL]   # share-link URLs for vectors/*.json (lead product)
    python scripts/regression.py log --product play --target prod --tier smoke --result pass [--notes ...]

Standard library only; runs from anywhere inside the repo.
"""
import argparse
import base64
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / '.claude' / 'skills' / 'test-deployed'
LOG = ROOT / 'docs' / 'testing' / 'REGRESSION-LOG.md'

PRODUCTS = {
    'lead': {
        'releases': ROOT / 'frontend/src/apps/changelog/releases.ts',
        'checks': SKILL / 'checks/lead.md',
        'prod': 'https://bridge-leads.icycookie.xyz',
    },
    'play': {
        'releases': ROOT / 'frontend/src/apps/play/changelog/releases.ts',
        'checks': SKILL / 'checks/play.md',
        'prod': 'https://bridge-play.icycookie.xyz',
    },
}

# One release entry: `version`, `date`, `title`, then whatever precedes `changes:`
# (that is where an `unreleased: true` flag sits).
ENTRY_RE = re.compile(
    r"version:\s*'(?P<version>v[\d.]+)',\s*date:\s*'(?P<date>[^']+)',\s*title:\s*'(?P<title>[^']*)',"
    r"(?P<head>.*?)changes:",
    re.S,
)
SECTION_RE = re.compile(r'^## (v[\d.]+)\b', re.M)
LOG_HEADER = (
    '# Regression runs\n\n'
    'Appended by `scripts/regression.py log` (see the `test-deployed` skill). '
    'SHA is what `origin/main` pointed at for prod runs (the deploy tags images '
    'with `github.sha`), `HEAD` for local runs.\n\n'
    '| Date | Product | Version | Target | SHA | Tier | Result | Notes |\n'
    '| --- | --- | --- | --- | --- | --- | --- | --- |\n'
)


def releases(product):
    """[(version, date, title, unreleased)] newest first, straight from releases.ts."""
    src = PRODUCTS[product]['releases'].read_text(encoding='utf-8')
    out = [(m['version'], m['date'], m['title'], 'unreleased: true' in m['head'])
           for m in ENTRY_RE.finditer(src)]
    if not out:
        sys.exit(f'{product}: no release entries parsed from {PRODUCTS[product]["releases"]}')
    return out


def deployed_version(product):
    """The version the deployed header should show: newest entry not flagged unreleased."""
    return next((v for v, _d, _t, unreleased in releases(product) if not unreleased), None)


def cmd_coverage(_args):
    uncovered = False
    for product, cfg in PRODUCTS.items():
        rels = releases(product)
        sections = set(SECTION_RE.findall(cfg['checks'].read_text(encoding='utf-8')))
        print(f'== {product}: deployed header should read {deployed_version(product)}')
        for v, d, title, unreleased in rels:
            flag = '  (unreleased: shows "In development")' if unreleased else ''
            cov = 'ok' if v in sections else 'NO CHECKS'
            uncovered |= v not in sections
            print(f'   {v:6} {d}  {cov:9}  {title}{flag}')
        stray = sorted(sections - {r[0] for r in rels})
        if stray:
            print(f'   sections with no release entry: {", ".join(stray)}')
    if uncovered:
        print('\nAdd a `## vX.Y` section for every release marked NO CHECKS before running the suite.')
        return 1
    return 0


def share_url(base, payload):
    blob = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(',', ':')).encode()).decode().rstrip('=')
    return f"{base.rstrip('/')}/#{payload['tool']}?s={blob}"


def cmd_urls(args):
    base = args.base or PRODUCTS['lead']['prod']
    for p in sorted((SKILL / 'vectors').glob('*.json')):
        payload = json.loads(p.read_text(encoding='utf-8'))
        print(f'{p.stem}\n  {share_url(base, payload)}')
    return 0


def git_sha(ref):
    try:
        return subprocess.check_output(['git', 'rev-parse', '--short', ref], cwd=ROOT,
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, OSError):
        return '?'


def cmd_log(args):
    version = deployed_version(args.product) or '?'
    sha = git_sha('origin/main' if args.target == 'prod' else 'HEAD')
    row = (f'| {date.today().isoformat()} | {args.product} | {version} | {args.target} | `{sha}` '
           f'| {args.tier} | {args.result} | {args.notes.replace("|", "/")} |')
    LOG.parent.mkdir(parents=True, exist_ok=True)
    if not LOG.exists():
        LOG.write_text(LOG_HEADER, encoding='utf-8')
    with LOG.open('a', encoding='utf-8') as f:
        f.write(row + '\n')
    print(row)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('coverage', help='releases.ts vs checklists').set_defaults(fn=cmd_coverage)
    u = sub.add_parser('urls', help='share-link URLs for the lead vectors')
    u.add_argument('--base', help='site base URL (default: prod)')
    u.set_defaults(fn=cmd_urls)
    lg = sub.add_parser('log', help='append a run to docs/testing/REGRESSION-LOG.md')
    lg.add_argument('--product', choices=PRODUCTS, required=True)
    lg.add_argument('--target', choices=['prod', 'local'], default='prod')
    lg.add_argument('--tier', required=True, help='e.g. smoke, full, smoke+v1.2')
    lg.add_argument('--result', choices=['pass', 'fail', 'partial'], required=True)
    lg.add_argument('--notes', default='')
    lg.set_defaults(fn=cmd_log)
    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == '__main__':
    main()
