import './assets/main.css'

import { createApp } from 'vue'
import App from './App.vue'
import { initialLocale, setLocale } from './i18n'

// The catalog is loaded before the first paint, so German never flashes.
setLocale(initialLocale()).finally(() => createApp(App).mount('#app'))
