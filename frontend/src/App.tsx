import { useEffect, useState } from 'react'
import type { Mode } from './api/types'
import { decodeShare, parseHash, type SharePayload } from './lib/share'
import LeadApp from './apps/lead/LeadApp'
import ContractApp from './apps/contract/ContractApp'
import ChangelogApp from './apps/changelog/ChangelogApp'

const TABS = [
  { id: 'lead', label: '♠ Opening Lead' },
  { id: 'contract', label: '♦ Optimal Contract' },
  { id: 'changelog', label: 'What’s new' },
] as const

type TabId = typeof TABS[number]['id']

function tabFromHash(): TabId {
  const { tab } = parseHash(window.location.hash)
  return TABS.some((t) => t.id === tab) ? (tab as TabId) : 'lead'
}

/** Read a share payload from the URL hash, once, at startup.
 * Returns 'error' for a blob that is present but unreadable. */
function shareFromHash(): SharePayload | 'error' | null {
  const { blob } = parseHash(window.location.hash)
  if (!blob) return null
  return decodeShare(blob) ?? 'error'
}

/** Shell for the two tools. Both stay mounted — switching tabs must not throw
 * away a simulation that took ten seconds to produce — so the inactive one is
 * hidden rather than unmounted. The tab lives in the URL hash so a tab can be
 * linked to (nginx already serves the SPA for any path), and a shared result
 * travels as `#<tool>?s=<payload>` in the same hash. */
export default function App() {
  // The share payload is read exactly once — mid-session hash edits are not a
  // supported way to inject a new query.
  const [shared] = useState<SharePayload | 'error' | null>(shareFromHash)
  const [shareError, setShareError] = useState(shared === 'error')
  const [tab, setTab] = useState<TabId>(() => (
    shared && shared !== 'error' ? shared.tool : tabFromHash()
  ))
  const [light, setLight] = useState(false)
  // The scoring mode is shared: it is the same question in both tools.
  const [mode, setMode] = useState<Mode>(() => (
    (shared && shared !== 'error' && shared.view?.mode) || 'imps'
  ))

  useEffect(() => { document.body.classList.toggle('light', light) }, [light])
  useEffect(() => {
    const onHash = () => setTab(tabFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const select = (id: TabId) => {
    window.location.hash = id
    setTab(id)
  }

  return (
    <>
      <header className="topbar">
        <nav className="tabs">
          {TABS.map((t) => (
            <button key={t.id} className={tab === t.id ? 'on' : ''}
              onClick={() => select(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
        <label className="toggle">
          <input type="checkbox" checked={light} onChange={(e) => setLight(e.target.checked)} />
          Light mode
        </label>
      </header>

      {shareError && (
        <div className="banner banner-error" style={{ margin: '0.7rem 1rem' }}>
          Couldn’t read this shared link — it may be truncated or from a newer
          version of the app. Showing the plain simulator instead.{' '}
          <button className="btn btn-small" onClick={() => setShareError(false)}>Dismiss</button>
        </div>
      )}

      <div hidden={tab !== 'lead'}>
        <LeadApp mode={mode} setMode={setMode}
          shared={shared !== 'error' && shared?.tool === 'lead' ? shared : null} />
      </div>
      <div hidden={tab !== 'contract'}>
        <ContractApp mode={mode} setMode={setMode}
          shared={shared !== 'error' && shared?.tool === 'contract' ? shared : null} />
      </div>
      {/* Static, so unlike the tools it costs nothing to mount alongside them. */}
      <div hidden={tab !== 'changelog'}><ChangelogApp /></div>
    </>
  )
}
