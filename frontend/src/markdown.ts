import DOMPurify from 'dompurify'
import { marked } from 'marked'

const FADE_MS = 400 // keep in sync with the .w animation in ChatApp.vue

/**
 * Assistant Markdown -> sanitized HTML.
 * While streaming, `births` holds when each word first appeared: a word younger than FADE_MS gets a fade-in
 * that resumes where it was (negative delay), so re-rendering every frame does not restart old words.
 */
export function toHtml(md: string, births?: number[], caret = false) {
  const root = DOMPurify.sanitize(marked.parse(md, { async: false }), { RETURN_DOM: true }) as HTMLElement
  for (const a of root.querySelectorAll('a')) {
    a.target = '_blank'
    a.rel = 'noopener noreferrer'
  }
  if (births) {
    const texts: Text[] = []
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
    while (walker.nextNode()) texts.push(walker.currentNode as Text)
    if (caret) {
      const c = document.createElement('span')
      c.className = 'caret'
      // After the last word, so it sits inline at the end of the last paragraph or list item.
      const last = texts.filter((t) => t.data.trim()).pop()
      if (last) last.after(c)
      else root.append(c)
    }
    const now = performance.now()
    let i = 0
    for (const t of texts) {
      const parts = t.data.split(/(\s+)/).map((word) => {
        if (!word.trim()) return word
        const age = now - (births[i] ??= now)
        i++
        if (age >= FADE_MS) return word
        const span = document.createElement('span')
        span.className = 'w'
        span.style.animationDelay = `${-age}ms`
        span.textContent = word
        return span
      })
      t.replaceWith(...parts)
    }
  }
  return root.innerHTML
}
