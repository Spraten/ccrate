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
  const style = {}
  const iframe = { contentWindow: { postMessage: (message, origin) => sent.push([structuredClone(message), origin]) }, setAttribute() {}, src: '', title: '' }
  Object.defineProperty(iframe, 'style', {
    get: () => style,
    set: cssText => Object.assign(style, Object.fromEntries(cssText.split(';').filter(Boolean).map(rule => {
      const [name, value] = rule.split(':').map(part => part.trim())
      return [name.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase()), value]
    }))),
  })
  globalThis.location = { origin: 'https://ccrate.test' }
  globalThis.document = { createElement: () => iframe }
  globalThis.window = {
    innerHeight: 800,
    crypto: { randomUUID: () => 'nonce-test' },
    addEventListener: (name, fn) => listeners.set(name, fn),
    removeEventListener: name => listeners.delete(name),
    confirm: () => false,
  }
  let containerTop = 232
  const container = {
    getBoundingClientRect: () => ({ top: containerTop }),
    replaceChildren() {}, append() {}, addEventListener() {}, removeEventListener() {},
  }
  const selected = new Proxy({ generation: 8, instance: 'scope-a', user: new Proxy({ id: 'user-1' }, {}), group: new Proxy({ id: 'group-1' }, {}), selected_item: new Proxy({ entity_id: 'item-1', name: 'Bench drill', asset_code: 'A-4' }, {}) }, {})
  let finishRequest
  const handle = mountLabelDesigner(container, {
    src: '/workshop-api/label-assets/editor.html',
    context: () => selected,
    request: () => new Promise(resolve => { finishRequest = resolve }),
  })
  assert.equal(iframe.style.height, '496px', 'frame leaves room for the native card and footer')
  window.innerHeight = 900
  containerTop = 232
  listeners.get('resize')()
  assert.equal(iframe.style.height, '596px', 'frame height follows the available viewport on resize')
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
  assert.equal(listeners.has('resize'), false, 'dispose removes the viewport listener')
  assert.equal(listeners.has('message'), false, 'dispose keeps bridge cleanup intact')
})
