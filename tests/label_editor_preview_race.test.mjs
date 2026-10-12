import assert from 'node:assert/strict'
import test from 'node:test'
import { createDraftPreviewGuard, isSameDocumentSnapshot } from '../label-ui/src/draft-preview-guard.js'

function deferred() {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

test('an identical delayed editor echo does not discard an in-flight preview', async () => {
  const guard = createDraftPreviewGuard()
  const current = { name: 'Item label', page: { widthMm: 40, heightMm: 28 }, elements: [{ id: 'name', content: 'Item name' }] }
  const requestRevision = guard.begin()
  const response = deferred()
  let rendered = null

  const completion = response.promise.then(result => {
    if (guard.accepts(requestRevision)) rendered = result
  })
  const debouncedEcho = structuredClone(current)
  if (!isSameDocumentSnapshot(debouncedEcho, current)) guard.invalidate()
  response.resolve({ image: 'mock-image-data' })
  await completion

  assert.deepEqual(rendered, { image: 'mock-image-data' })
})

test('a real in-flight document edit still rejects a stale preview result', async () => {
  const guard = createDraftPreviewGuard()
  const current = { page: { widthMm: 40, heightMm: 28 }, elements: [{ id: 'name', content: 'Item name' }] }
  const requestRevision = guard.begin()
  const response = deferred()
  let rendered = false

  const completion = response.promise.then(() => {
    if (guard.accepts(requestRevision)) rendered = true
  })
  const edited = structuredClone(current)
  edited.elements[0].content = 'Changed name'
  if (!isSameDocumentSnapshot(edited, current)) guard.invalidate()
  response.resolve({ image: 'stale-image-data' })
  await completion

  assert.equal(rendered, false)
  assert.equal(guard.accepts(requestRevision), false)
})
