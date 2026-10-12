import assert from 'node:assert/strict'
import { test } from 'node:test'
import { mountLabelDesigner } from '../kiosk/label-editor.js'

test('proxied selected item context is plain-cloned through the validated bridge and old async results are discarded', async (t) => {
  const prior = Object.fromEntries(['window', 'document', 'location'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  t.after(() => {
    for (const [key, descriptor] of Object.entries(prior)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor)
      else delete globalThis[key]
    }
  })

  const listeners = new Map()
  const sent = []
  const iframe = { contentWindow: { postMessage: (message, origin) => sent.push([structuredClone(message), origin]) }, setAttribute() {}, style: '', src: '', title: '' }
  globalThis.location = { origin: 'https://ccrate.test' }
  globalThis.document = { createElement: () => iframe }
  globalThis.window = {
    crypto: { randomUUID: () => 'nonce-test' },
    addEventListener: (name, fn) => listeners.set(name, fn),
    removeEventListener: name => listeners.delete(name),
    confirm: () => false,
  }
  const container = {
    replaceChildren() {}, append() {}, addEventListener() {}, removeEventListener() {},
  }
  const selected = new Proxy({ generation: 8, instance: 'scope-a', user: new Proxy({ id: 'user-1' }, {}), group: new Proxy({ id: 'group-1' }, {}), selected_item: new Proxy({ entity_id: 'item-1', name: 'Bench drill', asset_code: 'A-4' }, {}) }, {})
  let finishRequest
  const handle = mountLabelDesigner(container, {
    src: '/workshop-api/label-assets/editor.html',
    context: () => selected,
    request: () => new Promise(resolve => { finishRequest = resolve }),
  })
  const nonce = new URL(iframe.src, location.origin).searchParams.get('nonce')
  const dispatch = data => listeners.get('message')({ origin: location.origin, source: iframe.contentWindow, data: { channel: 'label-designer', nonce, ...data } })

  dispatch({ type: 'ready' })
  assert.deepEqual(sent.at(-1)[0].data.context.selected_item, selected.selected_item)
  assert.equal(sent.at(-1)[0].data.epoch, 0)

  const updated = new Proxy({ ...selected, selected_item: new Proxy({ entity_id: 'item-2', name: 'Storage cart', asset_code: '' }, {}) }, {})
  handle.updateContext(updated)
  assert.deepEqual(sent.at(-1)[0].data.context.selected_item, updated.selected_item)

  dispatch({ type: 'request', id: 'stale', action: 'labels/preview', data: { mode: 'item_draft' } })
  handle.invalidate()
  finishRequest({ image: 'data:image/png;base64,AA==' })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(sent.some(([message]) => message.type === 'response'), false)
  handle.dispose()
})
