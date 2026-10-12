import { createApp, defineComponent, h, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { createPinia } from 'pinia'
import { secureRandomId } from '@print-design-pro/core/secure-random-id'
import PrintDesigner from '@print-design-pro/components/shell/PrintDesigner.vue'
import { PAGE_PRESETS } from '@print-design-pro/core/schema/page'
import { createEmptyTemplate, type TemplateDocument } from '@print-design-pro/core/schema/template'
import { useDocumentStore } from '@print-design-pro/stores/document-store'
import { useHistoryStore } from '@print-design-pro/stores/history-store'
import { useSelectionStore } from '@print-design-pro/stores/selection-store'
import { openTemplate } from '@print-design-pro/core/open-template'
import { cloneJson } from '@print-design-pro/core/clone'
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

function starter(profile: Profile, kind = 'left'): TemplateDocument {
  const source = starterMap[`starter:${profile}:${kind}`]
  if (source) return cloneJson(source)
  const page = profile === 'supvan' ? { ...PAGE_PRESETS.label50x30, widthMm: 40, heightMm: 28 } : { ...PAGE_PRESETS.a4, widthMm: 60, heightMm: 40 }
  return createEmptyTemplate('Item label', page)
}

export function mountLabelDesigner(container: HTMLElement, bridge: LabelDesignerBridge = {}): LabelDesignerHandle {
  const nonce = new URLSearchParams(location.search).get('nonce') || ''
  const trustedOrigin = location.origin
  let disposed = false, dirty = false, busy = false, instanceEpoch = 0, activeFieldEpoch = 0
  let bridgeContext: any = null
  const send = (message: Omit<Message, 'channel' | 'nonce'>) => { if (!disposed && window.parent !== window) window.parent.postMessage({ channel: 'label-designer', nonce, ...message }, trustedOrigin) }
  const requests = new Map<string, { resolve: (v: any) => void; reject: (e: Error) => void }>()
  const request = (action: string, data?: any) => new Promise<any>((resolve, reject) => {
    const id = secureRandomId(); requests.set(id, { resolve, reject }); send({ type: 'request', id, action, data })
  })
  const app = createApp(defineComponent({
    setup() {
      const doc = useDocumentStore(), history = useHistoryStore(), selection = useSelectionStore()
      const document = ref(starter('supvan')), revision = ref(0), profile = ref<Profile>('supvan'), selectedId = ref<string | null>('starter:supvan:left')
      const templates = ref<any[]>([]), message = ref(''), preview = ref<any>(null), sampleName = ref('Sample item'), sampleCode = ref(''), selectedItem = ref('')
      let baseline = ''
      const snapshot = () => cloneJson(doc.document)
      const changed = () => {
        const current = snapshot(); dirty = JSON.stringify(current) !== baseline
        bridge.dirty?.(dirty); send({ type: 'dirty', data: { dirty } }); bridge.changed?.(current)
      }
      const notify = (text: string) => { message.value = text; bridge.notify?.(text) }
      const load = (value: TemplateDocument, id: string | null = null) => {
        document.value = cloneJson(value); openTemplate(document.value, { document: doc, history, selection });
        selectedId.value = id; if (!id) revision.value = 0; baseline = JSON.stringify(snapshot()); dirty = false; bridge.dirty?.(false); send({ type: 'dirty', data: { dirty: false } })
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
        const data = selectedItem.value ? { mode: 'item_draft', entity_id: selectedItem.value, profile: profile.value, document: snapshot() } : { mode: 'synthetic', profile: profile.value, document: snapshot(), sample: { item_name: sampleName.value, asset_code: sampleCode.value } }
        preview.value = await invoke('labels/preview', data); notify('Draft preview ready. It is not saved or printable.')
      }
      const buttons = () => h('div', { class: 'label-host-toolbar' }, [
        h('label', ['Profile ', h('select', { value: profile.value, onChange: (e: Event) => { if (dirty && !window.confirm('Discard unsaved label design changes?')) { (e.target as HTMLSelectElement).value = profile.value; return } profile.value = (e.target as HTMLSelectElement).value as Profile; load(starter(profile.value), null) } }, [h('option', { value: 'supvan' }, 'SUPVAN 40 × 28 mm'), h('option', { value: 'letter' }, 'Letter label 60 × 40 mm')])]),
        h('select', { 'aria-label': 'Saved label template', value: selectedId.value || '', onChange: (e: Event) => { const id = (e.target as HTMLSelectElement).value; if (dirty && !window.confirm('Discard unsaved label design changes?')) { (e.target as HTMLSelectElement).value = selectedId.value || ''; return } if (!id) { load(starter(profile.value), null); return } loadTemplate(id).catch((err: Error) => notify(err.message)) } }, [h('option', { value: '' }, 'New design'), ...templates.value.map((t: any) => h('option', { value: t.id }, t.name)), ...Object.keys(starterMap).filter(k => k.includes(profile.value) && !templates.value.some((t: any) => t.id === k)).map(k => h('option', { value: k }, starterMap[k]!.name))]),
        h('button', { onClick: () => loadList().catch((e: Error) => notify(e.message)) }, 'Refresh'), h('button', { disabled: !history.canUndo, onClick: history.undo }, 'Undo'), h('button', { disabled: !history.canRedo, onClick: history.redo }, 'Redo'),
        h('button', { onClick: () => save(false).catch((e: Error) => notify(e.message)) }, 'Save'), h('button', { onClick: () => save(true).catch((e: Error) => notify(e.message)) }, 'Duplicate'),
        h('button', { onClick: () => { if (dirty && !window.confirm('Discard unsaved label design changes?')) return; const value = selectedId.value && !selectedId.value.startsWith('starter:') ? templates.value.find((t: any) => t.id === selectedId.value) : null; value ? loadTemplate(value.id).catch((e: Error) => notify(e.message)) : load(starter(profile.value), null) } }, 'Reset'),
        h('input', { value: selectedItem.value, placeholder: 'Selected item UUID (optional)', 'aria-label': 'Selected item UUID', onInput: (e: Event) => selectedItem.value = (e.target as HTMLInputElement).value }),
        h('input', { value: sampleName.value, placeholder: 'Sample item name', 'aria-label': 'Sample item name', onInput: (e: Event) => sampleName.value = (e.target as HTMLInputElement).value }),
        h('input', { value: sampleCode.value, placeholder: 'Asset code', 'aria-label': 'Asset code', onInput: (e: Event) => sampleCode.value = (e.target as HTMLInputElement).value }),
        h('button', { onClick: () => previewDraft().catch((e: Error) => notify(e.message)) }, 'Preview draft'),
      ])
      watch(() => history.editVersion, changed, { flush: 'sync' })
      onMounted(() => { baseline = JSON.stringify(snapshot()); void loadList().catch((e: Error) => notify(e.message)); send({ type: 'ready', data: { nonce } }) })
      onBeforeUnmount(() => { if (dirty) bridge.dirty?.(true) })
      return () => h('div', { class: 'label-host' }, [buttons(), h('p', { role: 'status', class: 'label-host-message' }, message.value), h('div', { class: 'label-host-editor' }, [h(PrintDesigner, { modelValue: document.value, 'onUpdate:modelValue': (next: TemplateDocument) => { document.value = next; changed() } })]), preview.value ? h('section', { class: 'label-preview' }, [h('h2', 'Draft preview'), h('img', { src: preview.value.image, alt: 'Draft label preview' }), h('button', { onClick: () => preview.value = null }, 'Close preview')]) : null])
    },
  }))
  const exportGuard = document.createElement('style'); exportGuard.textContent = '[data-pp-export-open]{display:none!important} .label-host-editor{height:min(74vh,820px);min-height:520px} .label-host-editor [data-pp-designer]{height:100%!important;min-height:520px} .label-host-toolbar{display:flex;flex-wrap:wrap;gap:6px;padding:8px;background:#eef2f5;color:#183348} .label-host-toolbar button,.label-host-toolbar select,.label-host-toolbar input{min-height:40px;padding:6px 10px;border:1px solid #a3b6c5;border-radius:6px;font:inherit} .label-host-toolbar label{display:flex;gap:6px;align-items:center} .label-host-message{min-height:1.5em} .label-preview img{max-width:100%;image-rendering:pixelated}'; document.head.append(exportGuard); app.use(createPinia()); app.mount(container)
  const onMessage = (event: MessageEvent<Message>) => {
    if (disposed || event.origin !== trustedOrigin || event.source !== window.parent || event.data?.channel !== 'label-designer' || event.data.nonce !== nonce) return
    bridge.activity?.()
    const message = event.data
    if (message.type === 'response' && message.id) { const pending = requests.get(message.id); if (pending) { requests.delete(message.id); message.ok ? pending.resolve(message.result) : pending.reject(new Error(message.error || 'Label request failed.')) } }
    if (message.type === 'initialize') { bridgeContext = message.data?.context; void bridgeContext }
    if (message.type === 'session-activity') bridge.activity?.()
  }
  window.addEventListener('message', onMessage)
  const activity = () => { bridge.activity?.(); send({ type: 'session-activity' }) }
  const touchFocus = (event: FocusEvent) => { activity(); const field = event.target as HTMLInputElement | HTMLTextAreaElement; if (bridgeContext?.host !== 'terminal' || !field.matches('input,textarea') || !matchMedia('(pointer: coarse)').matches) return; const fieldId = field.dataset.labelField || (field.dataset.labelField = secureRandomId()); const epoch = ++activeFieldEpoch; field.readOnly = true; field.inputMode = 'none'; void request('touch-field', { field_id: fieldId, instance_epoch: epoch, value: field.value, type: field.type || 'text', title: field.getAttribute('aria-label') || field.placeholder || 'Edit label field' }).then((answer:any)=>{if(disposed||epoch!==activeFieldEpoch||document.activeElement!==field||answer?.field_id!==fieldId||answer?.instance_epoch!==epoch||answer?.cancelled)return;field.value=String(answer.value ?? '');field.dispatchEvent(new Event('input',{bubbles:true}));field.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));field.dispatchEvent(new Event('change',{bubbles:true}))}).catch(()=>{}) }
  container.addEventListener('pointerdown', activity, true); container.addEventListener('keydown', activity, true); container.addEventListener('input', activity, true); container.addEventListener('focusin', touchFocus, true)
  return { canLeave: () => !busy && !dirty, dispose: () => { disposed = true; window.removeEventListener('message', onMessage); container.removeEventListener('pointerdown', activity, true); container.removeEventListener('keydown', activity, true); container.removeEventListener('input', activity, true); container.removeEventListener('focusin', touchFocus, true); requests.forEach(v => v.reject(new Error('Editor closed.'))); requests.clear(); app.unmount(); exportGuard.remove() } }
}

if (document.querySelector('#app')) mountLabelDesigner(document.querySelector<HTMLElement>('#app')!)
