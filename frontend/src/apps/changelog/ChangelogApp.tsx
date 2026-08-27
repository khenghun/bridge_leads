import Changelog from '../../components/Changelog'
import { RELEASES } from './releases'

/** What's changed in the lead/contract app, newest first. Static content — no
 * simulation, no API call. The rendering is shared with the play solver
 * (`components/Changelog`); the data is not. */
export default function ChangelogApp() {
  return (
    <div className="layout">
      <main className="content">
        <h1>What&rsquo;s new</h1>
        <p className="caption">
          Every release that changed something you can see, newest first.
        </p>
        <Changelog releases={RELEASES} />
      </main>
    </div>
  )
}
