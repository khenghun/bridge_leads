import { KIND_LABEL, RELEASES, type ChangeKind, type Release } from './releases'

// New before Improved before Fixed. Sorting here rather than asking the data to
// be written in order — a stable sort keeps the author's ordering within a kind.
const KIND_ORDER: Record<ChangeKind, number> = { new: 0, improved: 1, fixed: 2 }

/** '2026-08-04' -> '4 August 2026'. Parsed by hand rather than through Date,
 * which would shift the day for anyone west of UTC. */
function formatDate(iso: string): string {
  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
    'August', 'September', 'October', 'November', 'December']
  const [y, m, d] = iso.split('-').map(Number)
  return `${d} ${MONTHS[m - 1]} ${y}`
}

function ReleaseCard({ release, latest }: { release: Release; latest: boolean }) {
  return (
    <article className="release">
      <header className="release-head">
        {release.version && <span className="release-version">{release.version}</span>}
        <h2>{release.title}</h2>
        {latest && <span className="release-latest">Latest</span>}
        <time className="release-date" dateTime={release.date}>{formatDate(release.date)}</time>
      </header>
      {release.summary && <p className="caption release-summary">{release.summary}</p>}
      <ul className="release-changes">
        {[...release.changes]
          .sort((a, b) => KIND_ORDER[a.kind] - KIND_ORDER[b.kind])
          .map((c, i) => (
            <li key={i}>
              <span className={`change-tag change-${c.kind}`}>{KIND_LABEL[c.kind]}</span>
              <span>{c.text}</span>
            </li>
          ))}
      </ul>
    </article>
  )
}

/** What's changed, newest first. Static content — no simulation, no API call. */
export default function ChangelogApp() {
  return (
    <div className="layout">
      <main className="content">
        <h1>What&rsquo;s new</h1>
        <p className="caption">
          Every release that changed something you can see, newest first.
        </p>
        <div className="changelog">
          {RELEASES.map((r, i) => (
            <ReleaseCard key={`${r.date}-${r.title}`} release={r} latest={i === 0} />
          ))}
        </div>
      </main>
    </div>
  )
}
