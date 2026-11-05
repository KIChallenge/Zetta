import DOMPurify from 'dompurify'
import { marked } from 'marked'

// What Markdown produces, nothing more: no forms, inputs, styles or media, even if a text contained them.
const ALLOWED_TAGS = ['p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'a', 'code', 'pre', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'hr']

/** Older free-text assistant replies: Markdown -> sanitized HTML, links open in a new tab. */
export function toHtml(md: string) {
  const html = marked.parse(md, { async: false })
  const root = DOMPurify.sanitize(html, { RETURN_DOM: true, ALLOWED_TAGS, ALLOWED_ATTR: ['href'] }) as HTMLElement
  for (const a of root.querySelectorAll('a')) {
    a.target = '_blank'
    a.rel = 'noopener noreferrer'
  }
  return root.innerHTML
}
