import DOMPurify from 'dompurify'
import { marked } from 'marked'

/** Older free-text assistant replies: Markdown -> sanitized HTML, links open in a new tab. */
export function toHtml(md: string) {
  const root = DOMPurify.sanitize(marked.parse(md, { async: false }), { RETURN_DOM: true }) as HTMLElement
  for (const a of root.querySelectorAll('a')) {
    a.target = '_blank'
    a.rel = 'noopener noreferrer'
  }
  return root.innerHTML
}
