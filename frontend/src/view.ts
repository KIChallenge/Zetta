import { reactive, watch } from 'vue'

const KEY = 'lotse-ansicht' // read by applyView() in public/view.js

function stored() {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '{}') ?? {}
  } catch {
    return {}
  }
}

/** The display settings (Einstellungen > Ansicht), shared with the theme button in the app bar. */
export const view = reactive({ text: 'm', theme: 'auto', contrast: 'normal', motion: false, ...stored() })

watch(view, () => {
  try {
    localStorage.setItem(KEY, JSON.stringify(view))
  } catch {
    // Private mode or storage blocked: the view still applies until reload.
  }
  applyView()
})
