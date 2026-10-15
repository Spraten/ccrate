import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = readFileSync(new URL('../label-ui/src/editor-host.ts', import.meta.url), 'utf8')
const host = readFileSync(new URL('../homebox-ui/overlay/components/Workshop/LabelDesigner.vue', import.meta.url), 'utf8')
const generator = readFileSync(new URL('../homebox-ui/overlay/components/Workshop/LabelGenerator.vue', import.meta.url), 'utf8')

function loadSourceFunction(name, parameters) {
  const marker = `export function ${name}(`
  const start = source.indexOf(marker)
  assert.notEqual(start, -1, `${name} is implemented in the maintained editor host`)
  const open = source.indexOf('{', start)
  let depth = 1
  let quote = ''
  let escaped = false
  for (let index = open + 1; index < source.length; index++) {
    const character = source[index]
    if (quote) {
      if (escaped) escaped = false
      else if (character === '\\') escaped = true
      else if (character === quote) quote = ''
      continue
    }
    if (character === '"' || character === "'" || character === '`') quote = character
    else if (character === '{') depth++
    else if (character === '}' && --depth === 0)
      return new Function(...parameters, source.slice(open + 1, index).replace(/:\s*(any|string|boolean)\b/g, ''))
  }
  assert.fail(`Could not read ${name} body`)
}

test('uncertain template saves use status-only checks and stay locked until the result is found', async () => {
  assert.match(source, /const saveRecovery = createTemplateSaveRecovery\(/)
  assert.match(source, /pendingTemplateSave\.value \? h\('button',[\s\S]*?'Check save result'/)
  assert.match(source, /saveRecovery\.save\(/)
  assert.match(source, /saveRecovery\.check\(\)/)
  assert.match(source, /restorePendingTemplateSave\?\.\(context\?\.pending_template_save\)/)
  assert.match(source, /status: message\.status/)
  assert.match(source, /if \(intent\.legacy && result\.document\)[\s\S]*?load\(result\.document, result\.id \|\| null, true\)/)
  assert.match(host, /pending_template_save: workshop\.pendingTemplateSave\(\)/)
  assert.match(source, /disabled: !!pendingTemplateSave\.value/)
  assert.match(source, /class: 'label-host-editor', inert: !!pendingTemplateSave\.value/)
  const createRecovery = loadSourceFunction('createTemplateSaveRecovery', ['makeKey', 'write', 'lookup', 'setPending', 'reconcile', 'notify', 'cloneJson'])
  const applyResult = loadSourceFunction('applyTemplateSaveResult', ['state', 'intent', 'result', 'currentSnapshot'])
  const keys = []
  const writes = []
  const lookups = []
  const messages = []
  const templateState = { pending: null, selectedId: 'starter:supvan:left', revision: 0, templates: [], baseline: '', dirty: true }
  let lookupResult = new Error('result endpoint unavailable')
  const recovery = createRecovery(
    () => { const key = `save-key-${keys.length + 1}`; keys.push(key); return key },
    async payload => { writes.push(payload); throw new Error('save reply lost') },
    async key => { lookups.push(key); if (lookupResult instanceof Error) throw lookupResult; return lookupResult },
    intent => { templateState.pending = intent },
    (intent, result) => applyResult(templateState, intent, result, {}),
    message => messages.push(message),
    value => JSON.parse(JSON.stringify(value)),
  )

  await assert.rejects(recovery.save({ id: null, revision: 0, name: 'Bench label' }, '{}', false, { name: 'Bench label' }), /outcome is unknown/i)
  assert.equal(templateState.pending.data.request_key, 'save-key-1')
  assert.deepEqual(templateState.pending.data, { id: null, revision: 0, name: 'Bench label', request_key: 'save-key-1' }, 'the exact original payload remains available for reconciliation')
  await recovery.save({ id: 'different', revision: 8, name: 'Changed label' }, '{"name":"changed"}', true, { name: 'Changed label' })
  assert.deepEqual(keys, ['save-key-1'], 'blocked Save does not allocate a replacement request key')
  assert.equal(writes.length, 1, 'blocked Save does not issue another write')

  lookupResult = null
  assert.equal((await recovery.check()).status, 'pending')
  assert.equal(templateState.pending.data.request_key, 'save-key-1')
  assert.equal(writes.length, 1, 'a null status result never retries the write')
  await recovery.save({ id: 'different', revision: 8, name: 'Changed label' }, '{"name":"changed"}', true, { name: 'Changed label' })
  assert.deepEqual(keys, ['save-key-1'], 'a missing status result keeps subsequent Save blocked')
  assert.equal(writes.length, 1)

  lookupResult = new Error('result endpoint still unavailable')
  assert.equal((await recovery.check()).status, 'uncertain')
  assert.equal(templateState.pending.data.request_key, 'save-key-1')
  assert.equal(writes.length, 1, 'a failed status lookup never retries the write')

  lookupResult = { id: 'template-7', revision: 3, name: 'Bench label', profile: 'supvan', document: { name: 'Bench label' } }
  assert.equal((await recovery.check()).status, 'saved')
  assert.deepEqual(lookups, ['save-key-1', 'save-key-1', 'save-key-1', 'save-key-1'])
  assert.equal(templateState.pending, null)
  assert.equal(templateState.selectedId, 'template-7')
  assert.equal(templateState.revision, 3)
  assert.equal(templateState.templates[0].id, 'template-7')
  assert.equal(templateState.baseline, '{}')

  const nextWrite = await recovery.save({ id: 'template-7', revision: 3, name: 'Next revision' }, '{"name":"next"}', false, { name: 'Next revision' })
  assert.equal(nextWrite.status, 'saved', 'a new save is allowed after the prior result is confirmed')
  assert.deepEqual(keys, ['save-key-1', 'save-key-2'])
  assert.equal(writes.length, 2)
  assert.equal(messages.length > 0, true)

  const restoredRow = { key: 'persisted-key', path: 'labels/templates/save', identity: 'identity-7', group_id: 'group-1', user_id: 'user-1', intent: { request_key: 'persisted-key', id: null, revision: 0, profile: 'supvan', name: 'Restored label', document: { name: 'Restored label' } } }
  const restoredState = { pending: null, selectedId: null, revision: 0, templates: [], baseline: '', dirty: true }
  let restoredWrites = 0
  let restoredLookup = null
  const remounted = createRecovery(
    () => { throw new Error('rehydrated state must keep its original key') },
    async () => { restoredWrites++; throw new Error('status-only recovery must not write') },
    async key => { assert.equal(key, 'persisted-key'); return restoredLookup },
    intent => { restoredState.pending = intent },
    (intent, result) => applyResult(restoredState, intent, result, { name: 'Restored label' }),
    message => messages.push(message),
    value => JSON.parse(JSON.stringify(value)),
  )
  assert.equal(remounted.restore(restoredRow).data, restoredRow.intent)
  assert.equal((await remounted.check()).status, 'pending', 'remount checks status only when no saved result exists')
  assert.equal(restoredState.pending.data.request_key, 'persisted-key')
  assert.deepEqual(restoredState.pending.data, restoredRow.intent, 'remount retains the exact saved payload')
  assert.equal(restoredWrites, 0)
  restoredLookup = { id: 'restored-id', revision: 1, name: 'Restored label', profile: 'supvan', document: { name: 'Restored label' } }
  assert.equal((await remounted.check()).status, 'saved')
  assert.equal(restoredState.selectedId, 'restored-id', 'found result reconciles the restored template state')
  assert.equal(restoredState.pending, null)
  assert.equal(restoredWrites, 0)

  const legacyRow = { key: 'legacy-key', path: 'labels/templates/save' }
  const legacyState = { pending: null, selectedId: null, revision: 0, templates: [], baseline: '', dirty: false, document: null }
  const legacy = createRecovery(
    () => { throw new Error('legacy pending state must block a new key') },
    async () => { throw new Error('legacy result checks must not write') },
    async key => { assert.equal(key, 'legacy-key'); return restoredLookup },
    intent => { legacyState.pending = intent },
    (intent, result) => {
      if (intent.legacy) {
        legacyState.document = result.document
        intent.current = result.document
        intent.submitted = JSON.stringify(result.document)
      }
      applyResult(legacyState, intent, result, legacyState.document || {})
    },
    message => messages.push(message),
    value => JSON.parse(JSON.stringify(value)),
  )
  assert.equal(legacy.restore(legacyRow).legacy, true)
  assert.equal((await legacy.save({ name: 'Wrong draft' }, '{}', false, {})).status, 'blocked')
  assert.equal((await legacy.check()).status, 'saved')
  assert.deepEqual(legacyState.document, restoredLookup.document, 'legacy saves reconcile from the server-returned template document')
  assert.equal(legacyState.selectedId, restoredLookup.id)
  assert.equal(legacyState.pending, null)

  const rejectedState = { pending: null, selectedId: 'template-old', revision: 1, templates: [], baseline: '', dirty: true }
  const rejectionKeys = []
  let rejectionWrites = 0
  let rejectionLookups = 0
  const rejection = createRecovery(
    () => { const key = `rejected-key-${rejectionKeys.length + 1}`; rejectionKeys.push(key); return key },
    async payload => {
      rejectionWrites++
      if (rejectionWrites === 1) throw Object.assign(new Error('Template revision conflict'), { status: 409 })
      return { id: 'template-old', revision: 3, name: 'Updated label', document: { name: 'Updated label' } }
    },
    async () => { rejectionLookups++; throw new Error('authoritative rejection must not trigger a status lookup') },
    intent => { rejectedState.pending = intent },
    (intent, result) => applyResult(rejectedState, intent, result, {}),
    message => messages.push(message),
    value => JSON.parse(JSON.stringify(value)),
  )
  assert.equal((await rejection.save({ id: 'template-old', revision: 2, name: 'Updated label' }, '{}', false, {})).status, 'rejected')
  assert.equal(rejectedState.pending, null, 'authoritative 409 clears the editor pending state')
  assert.equal(rejectionLookups, 0, 'authoritative rejection is not converted into an ambiguous status check')
  assert.equal(messages.some(message => message.includes('Template revision conflict')), true, 'the rejection is reported to the user')
  assert.equal((await rejection.save({ id: 'template-old', revision: 2, name: 'Updated label' }, '{}', false, {})).status, 'saved')
  assert.deepEqual(rejectionKeys, ['rejected-key-1', 'rejected-key-2'], 'the next attempt requires a separate user-initiated save and new key')
})

test('template-saved is emitted after direct and recovered save confirmation only', async () => {
  const mountedSaveReconcile = source.slice(source.indexOf('const saveRecovery = createTemplateSaveRecovery('), source.indexOf('const placementWarning'))
  assert.match(mountedSaveReconcile, /sendConfirmedTemplateSave\(send, result\)/, 'the mounted editor signals only from its successful reconcile callback')
  assert.match(host, /saved: \(result: any\) => emit\("saved", result\)/, 'LabelDesigner forwards the host save event')
  assert.match(generator, /@saved="workspace\.actions\.designerSaved"/, 'LabelGenerator forwards the save event to the parent action')

  const createRecovery = loadSourceFunction('createTemplateSaveRecovery', ['makeKey', 'write', 'lookup', 'setPending', 'reconcile', 'notify', 'cloneJson'])
  const sendConfirmed = loadSourceFunction('sendConfirmedTemplateSave', ['send', 'result'])
  const directMessages = []
  const directResult = { id: 'direct-id', revision: 2 }
  const direct = createRecovery(() => 'direct-key', async () => directResult, async () => null, () => {}, (_, result) => sendConfirmed(message => directMessages.push(message), result), () => {}, value => value)
  assert.equal((await direct.save({}, '{}', false, {})).status, 'saved')
  assert.deepEqual(directMessages, [{ type: 'template-saved', data: directResult }])

  const recoveredMessages = []
  let statusResult = null
  const recoveredResult = { id: 'recovered-id', revision: 4 }
  const recovered = createRecovery(() => 'recovered-key', async () => { throw new Error('reply lost') }, async () => statusResult, () => {}, (_, result) => sendConfirmed(message => recoveredMessages.push(message), result), () => {}, value => value)
  await assert.rejects(recovered.save({}, '{}', false, {}), /outcome is unknown/i)
  assert.deepEqual(recoveredMessages, [], 'an unresolved save emits no success signal')
  statusResult = recoveredResult
  assert.equal((await recovered.check()).status, 'saved')
  assert.deepEqual(recoveredMessages, [{ type: 'template-saved', data: recoveredResult }])
})
