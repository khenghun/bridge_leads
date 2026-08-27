// Release notes, rendered. Shared by both products, each with its OWN data
// file — the lead app's `apps/changelog/releases.ts` and the play solver's
// `apps/play/changelog/releases.ts` — because the two are versioned and
// released separately. Only the presentation is common.

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
  /** True while the version is built but not yet deployed — shown as
   * "In development" instead of "Latest", so the local changelog can track
   * work before it ships. */
  unreleased?: boolean
  changes: Change[]
}

export const KIND_LABEL: Record<ChangeKind, string> = {
  new: 'New',
  improved: 'Improved',
  fixed: 'Fixed',
}

// New before Improved before Fixed. Sorting here rather than asking the data to
// be written in order — a stable sort keeps the author's ordering within a kind.
const KIND_ORDER: Record<ChangeKind, number> = { new: 0, improved: 1, fixed: 2 }

/** '2026-08-04' -> '4 August 2026'. Parsed by hand rather than through Date,
 * which would shift the day for anyone west of UTC. */
export function formatDate(iso: string): string {
  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
    'August', 'September', 'October', 'November', 'December']
  const [y, m, d] = iso.split('-').map(Number)
  return `${d} ${MONTHS[m - 1]} ${y}`
}

export function ReleaseCard({ release, latest }: { release: Release; latest: boolean }) {
  return (
    <article className="release">
      <header className="release-head">
        {release.version && <span className="release-version">{release.version}</span>}
        <h2>{release.title}</h2>
        {release.unreleased
          ? <span className="release-latest release-unreleased">In development</span>
          : latest && <span className="release-latest">Latest</span>}
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

/** The list, newest first. Static content — no simulation, no API call. */
export default function Changelog({ releases }: { releases: Release[] }) {
  return (
    <div className="changelog">
      {releases.map((r, i) => (
        <ReleaseCard key={`${r.date}-${r.title}`} release={r} latest={i === 0} />
      ))}
    </div>
  )
}
