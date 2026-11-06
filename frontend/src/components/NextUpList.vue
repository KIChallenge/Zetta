<script setup lang="ts">
import { computed } from 'vue'
import type { Chat } from '../chats'
import { t } from '../i18n'

const props = defineProps<{ chats: Chat[] }>()

// The step's type as a line icon from the sprite; the step's title already says what to do.
const ICON: Record<string, string> = {
  call: 'phone', email: 'mail', form: 'file', documents: 'list-check', upload: 'file', book: 'ext', info: 'info', wait: 'clock',
}

const yours = computed(() => props.chats.filter((c) => c.next?.kind === 'question' || c.next?.kind === 'step'))
const waiting = computed(() => props.chats.filter((c) => c.next?.kind === 'waiting'))
</script>

<template>
  <section class="todo" aria-labelledby="todo-h">
    <h2 id="todo-h">{{ t('Was jetzt ansteht') }}</h2>
    <!-- Nothing to do: a blank slip with a dashed edge, like the empty fields of the form beside it. -->
    <div v-if="!yours.length" class="blank">
      <svg class="i" aria-hidden="true"><use href="#i-route" /></svg>
      <p v-if="chats.length"><b>{{ t('Gerade ist nichts für Sie zu tun.') }}</b> {{ t('Sobald es weitergeht, steht der nächste Schritt hier.') }}</p>
      <div v-else class="first">
        <p><b>{{ t('Noch nichts zu tun.') }}</b> {{ t('Hier steht dann Ihr nächster Schritt.') }}</p>
        <!-- A real sequence, drawn like the plan's later stations: hollow rings on one line. -->
        <ol class="how">
          <li><b>{{ t('Anliegen beschreiben') }}</b>{{ t('In eigenen Worten, unter „Worum geht es?“.') }}</li>
          <li><b>{{ t('Kurze Fragen beantworten') }}</b>{{ t('Meist genügt ein Klick.') }}</li>
          <li><b>{{ t('Schritte erledigen') }}</b>{{ t('Anrufen, schreiben, mitbringen: alles vorbereitet.') }}</li>
        </ol>
      </div>
    </div>
    <ul v-else class="rows">
      <li v-for="c in yours" :key="c.id">
        <a class="row" :href="`#${c.id}`">
          <span class="row-top">
            <span class="pill" data-tone="turn">{{ c.next!.kind === 'question' ? t('Frage offen') : t('Jetzt dran') }}</span>
            <span class="row-chat">{{ c.title }}</span>
          </span>
          <span class="row-do">
            <svg class="i" aria-hidden="true"><use :href="`#i-${c.next!.kind === 'question' ? 'chat' : ICON[c.next!.type ?? ''] ?? 'route'}`" /></svg>
            <span>{{ t(c.next!.text ?? '') }}</span>
          </span>
          <span v-if="c.next!.institution || c.next!.reachable" class="row-meta">
            <span v-if="c.next!.institution">{{ t(c.next!.institution) }}</span>
            <span v-if="c.next!.reachable" class="avail" :data-open="c.next!.reachable.open">{{ t(c.next!.reachable.text) }}</span>
          </span>
          <svg class="i row-go" aria-hidden="true"><use href="#i-arrow" /></svg>
        </a>
      </li>
    </ul>

    <template v-if="waiting.length">
      <h3 class="wait-h">{{ t('Wartet auf Antwort') }}</h3>
      <ul class="rows quiet">
        <li v-for="c in waiting" :key="c.id">
          <a class="row" :href="`#${c.id}`">
            <span class="row-chat">{{ c.title }}</span>
            <span class="row-meta"><svg class="i" aria-hidden="true"><use href="#i-clock" /></svg>{{ t(c.next!.text ?? '') }}</span>
            <svg class="i row-go" aria-hidden="true"><use href="#i-arrow" /></svg>
          </a>
        </li>
      </ul>
    </template>
  </section>
</template>

<style scoped>
.todo { display: grid; align-content: start; gap: .75rem; }
.todo h2 { font-size: var(--fs-h3); color: var(--head); }
.blank { display: flex; gap: .75rem; align-items: flex-start; padding: 1.25rem; border: 1px dashed var(--rule-2); border-radius: var(--r-m); color: var(--ink-2); }
.blank .i { margin-top: .15em; color: var(--head); }
.blank b { display: block; margin-bottom: .2rem; color: var(--ink); }
[data-contrast="high"] .blank { border: 2px dashed var(--ink); }
.first { display: grid; gap: 1.25rem; }
.how { list-style: none; margin: 0; padding: 0; display: grid; gap: 1rem; counter-reset: how; }
.how li { position: relative; display: grid; gap: .1rem; padding-left: 2.6rem; counter-increment: how; }
.how li b { margin: 0; color: var(--head); }
.how li::before { content: counter(how); position: absolute; left: 0; top: -.1rem; width: 1.8rem; height: 1.8rem; display: grid; place-items: center; border: 2px solid var(--rule-2); border-radius: 50%; background: var(--sheet); font-size: var(--fs-small); font-weight: 700; color: var(--head); }
/* The line runs from below one ring to the top of the next (rings sit .1rem above their row, rows 1rem apart). */
.how li:not(:last-child)::after { content: ""; position: absolute; left: calc(.9rem - 1px); top: 1.7rem; bottom: -.9rem; border-left: 2px solid var(--rule-2); }
/* One flat sheet, rows split by hairlines: read like an appointment slip, not a grid of cards. */
.rows { list-style: none; margin: 0; padding: 0; border: var(--hair); border-radius: var(--r-m); background: var(--sheet); overflow: hidden; }
.rows li + li { border-top: var(--hair); }
.row { position: relative; display: grid; gap: .3rem; padding: 1rem 2.75rem 1rem 1.25rem; color: var(--ink); text-decoration: none; transition: background-color .15s; }
.row:hover { background: var(--sunk); }
.row:focus-visible { outline-offset: -3px; }
.row-top { display: flex; flex-wrap: wrap; align-items: center; gap: .3rem .65rem; }
.row-chat { color: var(--ink-2); overflow-wrap: anywhere; }
.row-do { display: flex; gap: .5rem; align-items: flex-start; font-size: var(--fs-lead); font-weight: 600; line-height: 1.3; color: var(--head); }
.row-do .i { margin-top: .1em; }
.row-meta { display: flex; flex-wrap: wrap; align-items: center; gap: .2rem 1rem; font-size: var(--fs-small); color: var(--ink-3); }
.row-meta .avail { font-size: inherit; }
.row-go { position: absolute; right: 1rem; top: 50%; translate: 0 -50%; color: var(--action); }
.row:hover .row-go { translate: .2rem -50%; transition: translate .15s; }
.wait-h { margin-top: .75rem; font-size: 1rem; font-weight: 700; color: var(--ink-2); }
.quiet .row { padding-block: .75rem; gap: .15rem; }
.quiet .row-chat { color: var(--ink); font-weight: 600; }
.quiet .row-meta { gap: .4rem; }
.quiet .row-meta .i { width: 1em; height: 1em; }
[data-contrast="high"] .rows { border: 2px solid var(--ink); }
[data-contrast="high"] .rows li + li { border-top: 1px solid var(--ink); }
</style>
