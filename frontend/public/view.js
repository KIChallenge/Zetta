// The saved view (Einstellungen > Ansicht) is applied before the first paint, so nothing flashes.
function applyView() {
  var s = {}, r = document.documentElement, mm = function (q) { return matchMedia(q).matches }
  try { s = JSON.parse(localStorage.getItem('lotse-ansicht')) || {} } catch (e) {}
  r.dataset.text = s.text || 'm'
  r.dataset.contrast = s.contrast || 'normal'
  r.dataset.scheme = s.theme === 'light' || s.theme === 'dark' ? s.theme : mm('(prefers-color-scheme: dark)') ? 'dark' : 'light'
  r.dataset.motion = s.motion || mm('(prefers-reduced-motion: reduce)') ? 'reduce' : 'full'
}
applyView()
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyView)
matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', applyView)
