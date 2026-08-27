import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import PlayApp from './apps/play/PlayApp'
// Order matters: the shared tokens and component classes first (they style the
// ConstraintsEditor this app reuses), then Tailwind — whose preflight lands
// after them, so play.css re-asserts the form-control rules it resets.
import './index.css'
import './apps/play/play.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <PlayApp />
  </StrictMode>,
)
