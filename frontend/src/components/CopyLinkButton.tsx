import { useState } from 'react'

interface Props {
  /** Built at click time so it captures the current view state. */
  getUrl: () => string
}

/** Copy a share link for the current result. The whole query lives in the
 * URL, so the recipient reproduces the identical numbers — no account, no
 * server-side storage. */
export default function CopyLinkButton({ getUrl }: Props) {
  const [copied, setCopied] = useState(false)
  const onClick = async () => {
    const url = getUrl()
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard can be unavailable (permissions, http) — hand the URL over.
      window.prompt('Copy this link:', url)
    }
  }
  return (
    <button className="btn btn-small" onClick={onClick} title="Copy a link that reproduces this exact result">
      {copied ? '✓ Copied' : '🔗 Copy link'}
    </button>
  )
}
