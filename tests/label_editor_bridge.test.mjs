import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createLabelDesignerSaveHandlers, mountLabelDesigner } from '../kiosk/label-editor.js'

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

test('label template saves use the write callback and preserve their idempotency key', async (t) => {
  const prior = Object.fromEntries(['window', 'document', 'location'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  t.after(() => {
    for (const [key, descriptor] of Object.entries(prior)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor)
      else delete globalThis[key]
    }
  })

  const listeners = new Map(), sent = [], writes = [], requests = [], style = {}
  const iframe = { contentWindow: { postMessage: (message, origin) => sent.push([message, origin]) }, setAttribute() {}, src: '', title: '' }
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
  const container = { getBoundingClientRect: () => ({ top: 0 }), replaceChildren() {}, append() {}, addEventListener() {}, removeEventListener() {} }
  mountLabelDesigner(container, {
    src: '/editor.html',
    context: () => ({ generation: 4, instance: 'session-a' }),
    request: async (action, data) => { requests.push([action, data]); return null },
    write: async (...args) => { writes.push(args); if (args[1].request_key === 'save-key-2') throw Object.assign(new Error('Template revision conflict'), { status: 409 }); return { id: 'template-1', revision: 1 } },
  })
  const nonce = new URL(iframe.src, location.origin).searchParams.get('nonce')
  const payload = { request_key: 'save-key-1', id: null, revision: 0, name: 'My label' }
  await listeners.get('message')({ origin: location.origin, source: iframe.contentWindow, data: { channel: 'label-designer', nonce, type: 'request', id: 'save-1', action: 'labels/templates/save', data: payload } })

  assert.equal(writes.length, 1)
  assert.equal(writes[0][0], 'labels/templates/save')
  assert.equal(writes[0][1].request_key, 'save-key-1')
  assert.equal(writes[0][1].session_generation, 4)
  assert.equal(writes[0][1].session_instance, 'session-a')
  assert.deepEqual(requests, [])
  assert.equal(sent.at(-1)[0].ok, true)
  await listeners.get('message')({ origin: location.origin, source: iframe.contentWindow, data: { channel: 'label-designer', nonce, type: 'request', id: 'save-2', action: 'labels/templates/save', data: { ...payload, request_key: 'save-key-2' } } })
  assert.equal(sent.at(-1)[0].ok, false)
  assert.equal(sent.at(-1)[0].status, 409, 'the iframe bridge preserves an authoritative rejection status for recovery')
})

test('only an explicit confirmed template-saved bridge message invokes the saved callback', async (t) => {
  const prior = Object.fromEntries(['window', 'document', 'location'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  t.after(() => {
    for (const [key, descriptor] of Object.entries(prior)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor)
      else delete globalThis[key]
    }
  })

  const listeners = new Map(), style = {}, iframe = { contentWindow: { postMessage() {} }, setAttribute() {}, src: '', title: '' }
  Object.defineProperty(iframe, 'style', { get: () => style, set: cssText => Object.assign(style, Object.fromEntries(cssText.split(';').filter(Boolean).map(rule => { const [name, value] = rule.split(':').map(part => part.trim()); return [name.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase()), value] }))) })
  globalThis.location = { origin: 'https://ccrate.test' }
  globalThis.document = { createElement: () => iframe }
  globalThis.window = { innerHeight: 800, crypto: { randomUUID: () => 'nonce-test' }, addEventListener: (name, fn) => listeners.set(name, fn), removeEventListener: name => listeners.delete(name) }
  const container = { getBoundingClientRect: () => ({ top: 0 }), replaceChildren() {}, append() {}, addEventListener() {}, removeEventListener() {} }
  const saved = []
  mountLabelDesigner(container, { src: '/editor.html', context: () => ({ generation: 1, instance: 'a' }), request: async () => null, saved: result => saved.push(result) })
  const nonce = new URL(iframe.src, location.origin).searchParams.get('nonce')
  const dispatch = data => listeners.get('message')({ origin: location.origin, source: iframe.contentWindow, data: { channel: 'label-designer', nonce, ...data } })

  dispatch({ type: 'dirty', data: { dirty: true } })
  dispatch({ type: 'dirty', data: { dirty: false } })
  assert.deepEqual(saved, [])
  dispatch({ type: 'template-saved', data: { id: 'template-1', revision: 2 } })
  assert.deepEqual(saved, [{ id: 'template-1', revision: 2 }])
})

test('dirty transitions preserve parent label reviews, while confirmed save invalidates before a failed refresh', async () => {
  const workspace = { templateId: 'template-kept', templates: [], reviews: ['review'], pages: ['letter-page'] }
  let dirty = false, invalidations = 0, refreshStarted = false, refreshFailure
  const handlers = createLabelDesignerSaveHandlers({
    workspace,
    setDirty: value => { dirty = value },
    clearReviews: () => { invalidations++; workspace.reviews = []; workspace.pages = [] },
    refresh: async () => { refreshStarted = true; throw new Error('503') },
    onTemplates: rows => { workspace.templates = rows },
    onError: error => { refreshFailure = error.message },
  })

  handlers.designerDirty(true)
  handlers.designerDirty(false)
  assert.equal(dirty, false)
  assert.equal(workspace.templateId, 'template-kept')
  assert.deepEqual(workspace.reviews, ['review'])
  assert.deepEqual(workspace.pages, ['letter-page'])
  assert.equal(invalidations, 0)

  handlers.designerSaved()
  assert.equal(invalidations, 1)
  assert.equal(workspace.templateId, '')
  assert.deepEqual(workspace.reviews, [])
  assert.deepEqual(workspace.pages, [])
  assert.equal(refreshStarted, false, 'refresh starts after synchronous invalidation')
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(refreshStarted, true)
  assert.equal(refreshFailure, '503')
})
