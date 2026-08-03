import { useEffect, useState } from 'react'
import type { Mode } from './api/types'
import LeadApp from './apps/lead/LeadApp'
import ContractApp from './apps/contract/ContractApp'

const TABS = [
  { id: 'lead', label: '♠ Opening Lead' },
  { id: 'contract', label: '♦ Optimal Contract' },
] as const

type TabId = typeof TABS[number]['id']

function tabFromHash(): TabId {
  const id = window.location.hash.replace('#', '')
  return TABS.some((t) => t.id === id) ? (id as TabId) : 'lead'
}

/** Shell for the two tools. Both stay mounted — switching tabs must not throw
 * away a simulation that took ten seconds to produce — so the inactive one is
 * hidden rather than unmounted. The tab lives in the URL hash so a tab can be
 * linked to (nginx already serves the SPA for any path). */
export default function App() {
  const [tab, setTab] = useState<TabId>(tabFromHash)
  const [light, setLight] = useState(false)
  // The scoring mode is shared: it is the same question in both tools.
  const [mode, setMode] = useState<Mode>('imps')

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

      <div hidden={tab !== 'lead'}><LeadApp mode={mode} setMode={setMode} /></div>
      <div hidden={tab !== 'contract'}><ContractApp mode={mode} setMode={setMode} /></div>
    </>
  )
}
