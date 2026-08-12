export interface RunHistoryItem {
  at: number
  label: string
}

interface Props {
  items: RunHistoryItem[]
  /** Which entry the shown result belongs to (0 = latest run). */
  activeIndex: number
  onSelect: (index: number) => void
}

function hhmm(at: number): string {
  return new Date(at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/** This session's previous runs, restorable with a click — so tweaking a
 * constraint and re-running no longer throws the old answer away. In-memory
 * only (results are hundreds of KB); a reload clears it, and the caption says
 * so. Selecting an entry also repopulates the form from that run's frozen
 * request, exactly like opening a share link minus the re-run. */
export default function RunHistory({ items, activeIndex, onSelect }: Props) {
  if (items.length < 2) return null
  return (
    <div className="run-history">
      <span className="caption">This session’s runs (cleared on reload):</span>
      <div className="chips">
        {items.map((item, i) => (
          <button key={item.at}
            className={`chip${i === activeIndex ? ' chip-selected' : ''}`}
            onClick={() => onSelect(i)}>
            {hhmm(item.at)} · {item.label}
          </button>
        ))}
      </div>
    </div>
  )
}
