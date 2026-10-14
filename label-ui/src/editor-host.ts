import { createApp, defineComponent, h, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { createPinia } from 'pinia'
import { secureRandomId } from '@print-design-pro/core/secure-random-id'
import PrintDesigner from '@print-design-pro/components/shell/PrintDesigner.vue'
import { PAGE_PRESETS } from '@print-design-pro/core/schema/page'
import { createEmptyTemplate, type TemplateDocument } from '@print-design-pro/core/schema/template'
import { useDocumentStore } from '@print-design-pro/stores/document-store'
import { useBatchDataStore } from '@print-design-pro/stores/batch-data-store'
import { useHistoryStore } from '@print-design-pro/stores/history-store'
import { useSelectionStore } from '@print-design-pro/stores/selection-store'
import { useViewportStore } from '@print-design-pro/stores/viewport-store'
import { openTemplate } from '@print-design-pro/core/open-template'
import { cloneJson } from '@print-design-pro/core/clone'
import { createDraftPreviewGuard, isSameDocumentSnapshot } from './draft-preview-guard.js'
import starters from './starter-documents.json'
import { validateLabelDocument } from './profile-validation'
import '@print-design-pro/styles/index.css'
import './offline-fonts.css'

type Profile = 'supvan' | 'letter'
type Message = { channel: 'label-designer'; nonce: string; type: string; id?: string; action?: string; data?: any; ok?: boolean; result?: any; error?: string }
export type LabelDesignerBridge = { context?: () => unknown; request?: (action: string, data?: any) => Promise<any>; write?: (action: string, data: any, label: string, subject: string) => Promise<any>; notify?: (message: string) => void; changed?: (document: TemplateDocument) => void; dirty?: (value: boolean) => void; busy?: (value: boolean) => void; activity?: () => void }
export type LabelDesignerHandle = { canLeave: () => boolean; dispose: () => void }

const starterMap = starters as Record<string, TemplateDocument>
export function mmToFontPoints(mm: number): number { return mm * 72 / 25.4 }
declare global { interface Window { labelFontPointsFromMm: typeof mmToFontPoints } }
window.labelFontPointsFromMm = mmToFontPoints

function applyHostTheme(theme: any): void {
  if (!theme || typeof theme !== 'object') return
  const tokens: Record<string, unknown> = {
    '--pp-color-app-bg': theme.background, '--pp-color-app-panel': theme.background,
    '--pp-color-app-inset': theme.muted, '--pp-color-app-border': theme.border,
    '--pp-color-app-border2': theme.border, '--pp-color-app-desk': theme.muted,
    '--pp-color-app-text': theme.foreground, '--pp-color-app-text2': theme.mutedForeground, '--pp-color-app-text3': theme.mutedForeground,
    '--pp-color-brand-500': theme.primary, '--pp-color-brand-600': theme.primary,
    '--pp-color-brand-700': theme.primary, '--pp-color-brand-soft': theme.accent,
    '--pp-color-brand-soft2': theme.accent, '--pp-color-brand-50': theme.accent,
    '--pp-color-brand-100': theme.accent, '--pp-color-app-ok': theme.primary,
    '--pp-color-app-ok-soft': theme.accent,
  }
  for (const [name, value] of Object.entries(tokens))
    if (typeof value === 'string' && value.length < 120) document.documentElement.style.setProperty(name, value)
}

function starter(profile: Profile, kind = 'left'): TemplateDocument {
  const source = starterMap[`starter:${profile}:${kind}`]
  if (source) return cloneJson(source)
  const page = profile === 'supvan' ? { ...PAGE_PRESETS.label50x30, widthMm: 40, heightMm: 28 } : { ...PAGE_PRESETS.a4, widthMm: 60, heightMm: 40 }
  return createEmptyTemplate('Item label', page)
}

function blankDesign(profile: Profile): TemplateDocument {
  return createEmptyTemplate('New label', starter(profile).page)
}

export function mountLabelDesigner(container: HTMLElement, bridge: LabelDesignerBridge = {}): LabelDesignerHandle {
  const nonce = new URLSearchParams(location.search).get('nonce') || ''
  const trustedOrigin = location.origin
  let disposed = false, dirty = false, busy = false, instanceEpoch = 0, activeFieldEpoch = 0
  let bridgeContext: any = null
  let applyBridgeContext: ((context: any) => void) | null = null
  const send = (message: Omit<Message, 'channel' | 'nonce'>) => { if (!disposed && window.parent !== window) window.parent.postMessage({ channel: 'label-designer', nonce, ...message }, trustedOrigin) }
  const requests = new Map<string, { resolve: (v: any) => void; reject: (e: Error) => void }>()
  const request = (action: string, data?: any) => new Promise<any>((resolve, reject) => {
    const id = secureRandomId(); requests.set(id, { resolve, reject }); send({ type: 'request', id, action, data })
  })
  const app = createApp(defineComponent({
    setup() {
      const doc = useDocumentStore(), history = useHistoryStore(), selection = useSelectionStore(), viewport = useViewportStore(), batchData = useBatchDataStore()
      const document = ref(starter('supvan')), revision = ref(0), profile = ref<Profile>('supvan'), selectedId = ref<string | null>('starter:supvan:left')
      const templates = ref<any[]>([]), message = ref(''), preview = ref<any>(null), sampleName = ref('Sample item'), sampleCode = ref(''), sampleShortCode = ref(''), sampleDisplayId = ref(''), selectedItem = ref('')
      const previewDialog = ref<HTMLDialogElement | null>(null)
      let baseline = ''
      let previewOpener: HTMLElement | null = null
      const draftPreview = createDraftPreviewGuard()
      const snapshot = () => cloneJson(doc.document)
      const finishPreview = () => {
        preview.value = null
        const opener = previewOpener
        previewOpener = null
        if (opener?.isConnected)
          queueMicrotask(() => opener.focus())
      }
      const closePreview = () => {
        if (previewDialog.value?.open) previewDialog.value.close()
        else finishPreview()
      }
      let fitVersion = 0
      const fitToPage = (page: TemplateDocument['page']) => {
        const version = ++fitVersion
        void nextTick().then(() => requestAnimationFrame(() => {
          if (version !== fitVersion || disposed) return
          const canvas = container.querySelector<HTMLElement>('[data-pp-viewport]')
          if (canvas) viewport.fitToPage({ width: canvas.clientWidth, height: canvas.clientHeight }, { widthMm: page.widthMm, heightMm: page.heightMm })
        }))
      }
      const changed = () => {
        draftPreview.invalidate(); closePreview()
        const current = snapshot(); dirty = JSON.stringify(current) !== baseline
        bridge.dirty?.(dirty); send({ type: 'dirty', data: { dirty } }); bridge.changed?.(current)
      }
      const notify = (text: string) => { message.value = text; bridge.notify?.(text) }
      const placementWarning = () => notify('This element overlaps existing artwork. It is selected; move it to a clear area before saving.')
      const load = (value: TemplateDocument, id: string | null = null) => {
        document.value = cloneJson(value); openTemplate(document.value, { document: doc, history, selection });
        selectedId.value = id; if (!id) revision.value = 0; baseline = JSON.stringify(snapshot()); dirty = false; draftPreview.invalidate(); closePreview(); bridge.dirty?.(false); send({ type: 'dirty', data: { dirty: false } }); fitToPage(document.value.page)
      }
      applyBridgeContext = (context: any) => {
        applyHostTheme(context?.theme)
        const item = context?.selected_item
        const nextId = typeof item?.entity_id === 'string' ? item.entity_id : ''
        const nextName = typeof item?.name === 'string' ? item.name : 'Sample item'
        const nextCode = typeof item?.asset_code === 'string' ? item.asset_code : ''
        const nextShortCode = typeof item?.short_code === 'string' ? item.short_code : ''
        const nextDisplayId = typeof item?.display_id === 'string' ? item.display_id : ''
        if (nextId !== selectedItem.value || nextName !== sampleName.value || nextCode !== sampleCode.value || nextShortCode !== sampleShortCode.value || nextDisplayId !== sampleDisplayId.value) { draftPreview.invalidate(); closePreview() }
        selectedItem.value = nextId; sampleName.value = nextName; sampleCode.value = nextCode; sampleShortCode.value = nextShortCode; sampleDisplayId.value = nextDisplayId
        batchData.setPreviewOverrides(nextId ? { item_name: nextName, asset_code: nextCode, short_code: nextShortCode, display_id: nextDisplayId, item_path: `/item/${nextId}` } : null)
      }
      const invoke = async (action: string, data: any, write = false) => {
        busy = true; bridge.busy?.(true); send({ type: 'busy', data: { busy: true } })
        try {
          if (write && bridge.write) return await bridge.write(action, data, action === 'labels/templates/save' ? 'Save label template' : 'Label maker', selectedId.value || 'labels')
          if (bridge.request) return await bridge.request(action, data)
          return await request(action, data)
        } finally { busy = false; bridge.busy?.(false); send({ type: 'busy', data: { busy: false } }) }
      }
      const loadList = async () => { const rows = await invoke('labels/templates'); templates.value = Array.isArray(rows) ? rows : rows.templates || []; }
      const loadTemplate = async (id: string) => { const value = id.startsWith('starter:') ? templates.value.find((t: any) => t.id === id) || starterMap[id] : templates.value.find((t: any) => t.id === id); if (!value) throw Error('Template is unavailable. Refresh the saved templates and try again.'); profile.value = value.profile || (id.includes('letter') ? 'letter' : 'supvan'); revision.value = value.revision || 0; load(value.document || value, id); }
      const templateProfile = (template: any): Profile => template.profile || (String(template.id).includes('letter') ? 'letter' : 'supvan')
      const save = async (duplicate = false) => {
        const current = snapshot() // Read Pinia synchronously; PrintDesigner emits after 400 ms.
        const submitted = JSON.stringify(current)
        const checked = validateLabelDocument(current, profile.value)
        const makeCopy = duplicate || !selectedId.value || selectedId.value.startsWith('starter:')
        const key = secureRandomId(), data = { request_key: key, id: makeCopy ? null : selectedId.value, revision: makeCopy ? 0 : revision.value, profile: profile.value, document: checked, name: checked.name }
        try {
          const result = await invoke('labels/templates/save', data, true); selectedId.value = result.id || selectedId.value; revision.value = result.revision || revision.value + 1; if (result.document) current.name = result.name || current.name; baseline = submitted; dirty = JSON.stringify(snapshot()) !== submitted; templates.value = [...templates.value.filter((t: any) => t.id !== result.id), result]; bridge.dirty?.(dirty); send({ type: 'dirty', data: { dirty } }); notify(duplicate ? 'Copy saved.' : 'Template saved.')
        } catch (error) {
          const result = await invoke('labels/templates/result', { request_key: key }).catch(() => null)
          if (!result) throw error
          selectedId.value = result.id || selectedId.value; revision.value = result.revision || revision.value + 1; templates.value = [...templates.value.filter((t: any) => t.id !== result.id), result]; baseline = submitted; dirty = JSON.stringify(snapshot()) !== submitted; bridge.dirty?.(dirty); send({ type: 'dirty', data: { dirty } }); notify('Saved result confirmed.')
        }
      }
      const previewDraft = async () => {
        const version = draftPreview.begin()
        const opener = window.document.activeElement instanceof HTMLElement ? window.document.activeElement : null
        const data = selectedItem.value ? { mode: 'item_draft', entity_id: selectedItem.value, profile: profile.value, document: snapshot() } : { mode: 'synthetic', profile: profile.value, document: snapshot(), sample: { item_name: sampleName.value, asset_code: sampleCode.value, short_code: sampleShortCode.value, display_id: sampleDisplayId.value } }
        const result = await invoke('labels/preview', data)
        if (!draftPreview.accepts(version, disposed)) return
        previewOpener = opener
        preview.value = result; notify('Draft preview ready. It is not saved or printable.')
        await nextTick()
        if (preview.value && draftPreview.accepts(version, disposed) && !previewDialog.value?.open)
          previewDialog.value?.showModal()
      }
      const buttons = () => h('div', { class: 'label-host-toolbar' }, [
        h('label', ['Label size ', h('select', { value: profile.value, onChange: (e: Event) => { if (dirty && !window.confirm('Discard unsaved label design changes?')) { (e.target as HTMLSelectElement).value = profile.value; return } profile.value = (e.target as HTMLSelectElement).value as Profile; load(starter(profile.value), `starter:${profile.value}:left`) } }, [h('option', { value: 'supvan' }, 'SUPVAN · 40 × 28 mm'), h('option', { value: 'letter' }, 'Letter · 60 × 40 mm')])]),
        h('span', { class: 'label-host-paper-size', 'aria-live': 'polite' }, `Paper size: ${document.value.page.widthMm} × ${document.value.page.heightMm} mm`),
        h('label', ['Design ', h('select', { 'aria-label': 'Label design', value: selectedId.value || '', onChange: (e: Event) => { const id = (e.target as HTMLSelectElement).value; if (dirty && !window.confirm('Discard unsaved label design changes?')) { (e.target as HTMLSelectElement).value = selectedId.value || ''; return } if (!id) { load(blankDesign(profile.value), null); return } loadTemplate(id).catch((err: Error) => notify(err.message)) } }, [
          h('option', { value: '' }, 'Blank design'),
          h('optgroup', { label: 'Starter designs' }, [
            ...Object.keys(starterMap).filter(k => k.includes(profile.value)).map(k => h('option', { value: k }, starterMap[k]!.name)),
          ]),
          h('optgroup', { label: 'Saved designs' }, templates.value.filter((t: any) => !String(t.id).startsWith('starter:') && templateProfile(t) === profile.value).map((t: any) => h('option', { value: t.id }, t.name))),
        ])]),
        h('button', { onClick: () => loadList().catch((e: Error) => notify(e.message)) }, 'Refresh designs'),
        h('button', { onClick: () => save(false).catch((e: Error) => notify(e.message)) }, 'Save'), h('button', { onClick: () => save(true).catch((e: Error) => notify(e.message)) }, 'Duplicate'),
        h('button', { onClick: () => { if (dirty && !window.confirm('Discard unsaved label design changes?')) return; selectedId.value ? loadTemplate(selectedId.value).catch((e: Error) => notify(e.message)) : load(blankDesign(profile.value), null) } }, 'Reset design'),
        h('span', { class: 'label-host-selected-item', role: 'status' }, selectedItem.value ? `Draft preview for ${sampleName.value}${sampleDisplayId.value ? ` · ${sampleDisplayId.value}` : ''}` : 'Draft preview with a sample item'),
        h('button', { onClick: () => previewDraft().catch((e: Error) => notify(e.message)) }, 'Preview draft'),
      ])
      watch(() => history.editVersion, changed, { flush: 'sync' })
      onMounted(() => { window.addEventListener('pp-element-placement-warning', placementWarning); load(starter('supvan'), 'starter:supvan:left'); baseline = JSON.stringify(snapshot()); void loadList().catch((e: Error) => notify(e.message)); send({ type: 'ready', data: { nonce } }) })
      onBeforeUnmount(() => { window.removeEventListener('pp-element-placement-warning', placementWarning); if (dirty) bridge.dirty?.(true) })
      return () => h('div', { class: 'label-host' }, [buttons(), h('p', { role: 'status', class: 'label-host-message' }, message.value), h('div', { class: 'label-host-editor' }, [h(PrintDesigner, { modelValue: document.value, 'onUpdate:modelValue': (next: TemplateDocument) => { const unchanged = isSameDocumentSnapshot(next, snapshot()); document.value = next; if (!unchanged) changed() } })]), preview.value ? h('dialog', { ref: previewDialog, class: 'label-preview-dialog', 'aria-labelledby': 'label-preview-title', onClose: finishPreview }, [h('header', [h('h2', { id: 'label-preview-title' }, 'Draft preview'), h('button', { type: 'button', autofocus: true, onClick: closePreview }, 'Close preview')]), h('img', { src: preview.value.image, alt: 'Rendered draft label preview' })]) : null])
    },
  }))
  const exportGuard = document.createElement('style'); exportGuard.textContent = `:root,:root[data-theme="dark"]{--pp-color-app-bg:#f5f7f5;--pp-color-app-panel:#fff;--pp-color-app-inset:#edf1ee;--pp-color-app-border:#d9e1db;--pp-color-app-border2:#b8c7bb;--pp-color-app-desk:#e9eee9;--pp-color-app-text:#1c2b21;--pp-color-app-text2:#53645a;--pp-color-app-text3:#87958b;--pp-color-brand-500:#36704f;--pp-color-brand-600:#285d40;--pp-color-brand-soft:#e7f0e9;--pp-color-brand-soft2:#d5e5d9;--pp-color-brand-50:#e7f0e9;--pp-color-brand-100:#d5e5d9;--pp-color-brand-700:#244f37;--pp-color-app-ok:#36704f;--pp-color-app-ok-soft:#e7f0e9}
[data-pp-export-open],[data-pp-home],[data-pp-home]+div,[data-pp-save-state],[data-pp-paper-preset],[data-pp-paper-select],[data-pp-theme-toggle]{display:none!important}
.label-host{display:flex;height:100%;min-height:0;flex-direction:column}
.label-host-editor{flex:1;min-height:0;overflow:hidden}
.label-host-editor [data-pp-designer]{height:100%!important;min-height:0}
.label-host-editor [data-pp-designer]>div{grid-template-columns:minmax(0,1fr) minmax(220px,264px)!important}
.label-host-editor [data-pp-designer]>div>aside:first-child{display:none}
.label-host-toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:8px;background:var(--pp-color-app-panel);color:var(--pp-color-app-text);border:1px solid var(--pp-color-app-border);border-radius:7px}
.label-host-toolbar button,.label-host-toolbar select,.label-host-toolbar input{min-width:0;max-width:100%;min-height:40px;padding:6px 10px;border:1px solid var(--pp-color-app-border2);border-radius:6px;background:var(--pp-color-app-panel);color:var(--pp-color-app-text);font:inherit}
.label-host-toolbar button:focus-visible,.label-host-toolbar select:focus-visible,.label-host-toolbar input:focus-visible{outline:2px solid var(--pp-color-brand-500);outline-offset:2px}
.label-host-toolbar label{display:flex;gap:6px;align-items:center}
.label-host-paper-size{align-self:center;padding:8px 10px;border-radius:6px;background:var(--pp-color-brand-soft);color:var(--pp-color-brand-700);font-size:.875rem;font-weight:600;white-space:nowrap}
.label-host-message{min-height:1.5em}
.label-host-selected-item{align-self:center;padding:8px 10px;color:var(--pp-color-app-text2);font-size:.875rem}
.label-preview-dialog{position:fixed;inset:0;box-sizing:border-box;width:min(720px,calc(100vw - 24px));max-width:none;max-height:calc(100vh - 24px);margin:auto;padding:12px;overflow:auto;border:1px solid var(--pp-color-app-border2);border-radius:10px;background:var(--pp-color-app-panel);color:var(--pp-color-app-text);box-shadow:0 18px 50px rgb(15 23 42 / .3)}
.label-preview-dialog::backdrop{background:rgb(15 23 42 / .55)}
.label-preview-dialog header{display:flex;align-items:center;justify-content:space-between;gap:12px}
.label-preview-dialog h2{margin:0;font-size:1.125rem}
.label-preview-dialog button{min-height:40px;padding:6px 12px;border:1px solid var(--pp-color-app-border2);border-radius:6px;background:var(--pp-color-app-panel);color:var(--pp-color-app-text);font:inherit}
.label-preview-dialog button:focus-visible{outline:2px solid var(--pp-color-brand-500);outline-offset:2px}
.label-preview-dialog img{display:block;max-width:100%;max-height:min(70vh,calc(100vh - 100px),560px);width:auto;height:auto;object-fit:contain;margin:8px auto 0}
@media(max-width:700px){.label-host{height:auto;min-height:100%}.label-host-editor{height:920px;min-height:920px;flex:none;overflow:auto}.label-host-editor [data-pp-designer]{height:auto!important;min-height:880px;grid-template-rows:52px auto}.label-host-editor [data-pp-designer]>div{grid-template-columns:minmax(0,1fr)!important;grid-template-rows:auto minmax(300px,420px) auto!important}.label-host-editor [data-pp-designer]>div>aside:first-child{display:none}.label-host-editor [data-pp-designer]>div>main{min-height:360px}.label-host-toolbar>*{flex:1 1 135px}}`; document.head.append(exportGuard); app.use(createPinia()); app.mount(container)
  const onMessage = (event: MessageEvent<Message>) => {
    if (disposed || event.origin !== trustedOrigin || event.source !== window.parent || event.data?.channel !== 'label-designer' || event.data.nonce !== nonce) return
    bridge.activity?.()
    const message = event.data
    if (message.type === 'response' && message.id) { const pending = requests.get(message.id); if (pending) { requests.delete(message.id); message.ok ? pending.resolve(message.result) : pending.reject(new Error(message.error || 'Label request failed.')) } }
    if (message.type === 'initialize') { bridgeContext = message.data?.context; applyBridgeContext?.(bridgeContext) }
    if (message.type === 'session-activity') bridge.activity?.()
  }
  window.addEventListener('message', onMessage)
  const activity = () => { bridge.activity?.(); send({ type: 'session-activity' }) }
  const touchFocus = (event: FocusEvent) => { activity(); const field = event.target as HTMLInputElement | HTMLTextAreaElement; if (bridgeContext?.host !== 'terminal' || !field.matches('input,textarea') || !matchMedia('(pointer: coarse)').matches) return; const fieldId = field.dataset.labelField || (field.dataset.labelField = secureRandomId()); const epoch = ++activeFieldEpoch; field.readOnly = true; field.inputMode = 'none'; void request('touch-field', { field_id: fieldId, instance_epoch: epoch, value: field.value, type: field.type || 'text', title: field.getAttribute('aria-label') || field.placeholder || 'Edit label field' }).then((answer:any)=>{if(disposed||epoch!==activeFieldEpoch||document.activeElement!==field||answer?.field_id!==fieldId||answer?.instance_epoch!==epoch||answer?.cancelled)return;field.value=String(answer.value ?? '');field.dispatchEvent(new Event('input',{bubbles:true}));field.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));field.dispatchEvent(new Event('change',{bubbles:true}))}).catch(()=>{}) }
  container.addEventListener('pointerdown', activity, true); container.addEventListener('keydown', activity, true); container.addEventListener('input', activity, true); container.addEventListener('focusin', touchFocus, true)
  return { canLeave: () => !busy && !dirty, dispose: () => { disposed = true; window.removeEventListener('message', onMessage); container.removeEventListener('pointerdown', activity, true); container.removeEventListener('keydown', activity, true); container.removeEventListener('input', activity, true); container.removeEventListener('focusin', touchFocus, true); requests.forEach(v => v.reject(new Error('Editor closed.'))); requests.clear(); app.unmount(); exportGuard.remove() } }
}

if (document.querySelector('#app')) mountLabelDesigner(document.querySelector<HTMLElement>('#app')!)
