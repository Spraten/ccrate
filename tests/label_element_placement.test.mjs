import assert from 'node:assert/strict'
import { register } from 'node:module'
import test from 'node:test'
import { fitElementToPage, overlapsExisting } from '../label-ui/vendor/print-design-pro/src/core/element-placement.js'
import { excludeOverflowingTrailingSpaces, fitTextToBox, TEXT_LINE_HEIGHT, wrapText } from '../label-ui/vendor/print-design-pro/src/render/text-layout.ts'
function createShortCode(place) {
  return {
    id: 'short-code',
    type: 'text',
    name: 'Short code',
    content: '{{short_code}}',
    rotation: 0,
    locked: false,
    visible: true,
    xMm: place.centerXMm - 30,
    yMm: place.centerYMm - 6,
    widthMm: 60,
    heightMm: 12,
    fontSizePt: 9,
    fontWeight: 400,
  }
}

// Load the real TypeScript factory in Node's native test runner while stubbing
// only its UUID source; its geometry and font defaults remain production code.
const vendorTsLoader = `
export async function resolve(specifier, context, nextResolve) {
  if (context.parentURL?.endsWith('/element-factories.ts') && specifier === './schema/template') {
    return { url: 'data:text/javascript,export%20function%20newId()%7Breturn%20%22factory-test-id%22%7D', shortCircuit: true }
  }
  if (specifier.startsWith('.') && context.parentURL?.includes('/label-ui/vendor/print-design-pro/src/') && !/\\.[a-z0-9]+$/i.test(specifier))
    return nextResolve(specifier + '.ts', context)
  return nextResolve(specifier, context)
}
`
register(`data:text/javascript,${encodeURIComponent(vendorTsLoader)}`, import.meta.url)
await new Promise(resolve => setImmediate(resolve))
const { createText } = await import('../label-ui/vendor/print-design-pro/src/core/element-factories.ts')

test('fits new elements to the active label while keeping their center and proportions', () => {
  const text = fitElementToPage({ type: 'text', xMm: -10, yMm: 8, widthMm: 60, heightMm: 12 }, { widthMm: 40, heightMm: 28 })
  assert.deepEqual([text.xMm, text.yMm, text.widthMm, text.heightMm], [0, 10, 40, 8])

  const qr = fitElementToPage({ type: 'qr', xMm: 5, yMm: -1, widthMm: 30, heightMm: 30 }, { widthMm: 40, heightMm: 28 })
  assert.deepEqual([qr.xMm, qr.yMm, qr.widthMm, qr.heightMm], [6, 0, 28, 28])

  const image = fitElementToPage({ type: 'image', xMm: 14, yMm: -32, widthMm: 12, heightMm: 92 }, { widthMm: 40, heightMm: 28 })
  assert.deepEqual([image.xMm, image.yMm, image.widthMm, image.heightMm], [18.174, 0, 3.652, 28])

  const table = fitElementToPage({ type: 'table', xMm: -30, yMm: -6, widthMm: 100, heightMm: 40, columns: [{ widthMm: 50 }, { widthMm: 20 }, { widthMm: 30 }] }, { widthMm: 40, heightMm: 28 })
  assert.deepEqual([table.xMm, table.yMm, table.widthMm, table.heightMm], [0, 6, 40, 16])
  assert.deepEqual(table.columns.map(column => column.widthMm), [50, 20, 30])
})

test('places readable text into available space around starter artwork without touching the item QR', () => {
  const textToolElement = createText({ centerXMm: 20, centerYMm: 14 })
  assert.equal(textToolElement.fontSizePt, 9, 'the editor text tool uses its maintained printable default')
  const shortCodeToolElement = createText({ centerXMm: 20, centerYMm: 14 }, '{{short_code}}')
  assert.equal(shortCodeToolElement.content, '{{short_code}}')
  assert.equal(shortCodeToolElement.fontSizePt, 9, 'short-code labels use the same printable text factory')
  const text = fitElementToPage(
    textToolElement,
    { widthMm: 40, heightMm: 28 },
    [
      { type: 'qr', xMm: 2, yMm: 4.5, widthMm: 19, heightMm: 19, visible: true },
      { type: 'text', xMm: 23, yMm: 4, widthMm: 15, heightMm: 7, visible: true },
      { type: 'text', xMm: 23, yMm: 13, widthMm: 15, heightMm: 6, visible: true },
    ],
  )
  assert.ok(text.xMm >= 0 && text.yMm >= 0 && text.xMm + text.widthMm <= 40 && text.yMm + text.heightMm <= 28)
  assert.ok(text.widthMm >= 18.5 && text.heightMm >= textToolElement.fontSizePt * 25.4 / 72 * TEXT_LINE_HEIGHT)
  const rendered = fitTextToBox(text.content, text.widthMm, text.heightMm, text.fontSizePt * 25.4 / 72, { measure: value => [...value].length * 2 })
  assert.deepEqual(rendered, { lines: ['Text'], truncated: false }, 'the actual print layout keeps the inserted default text legible')
  assert.equal(overlapsExisting(text, [
    { xMm: 2, yMm: 4.5, widthMm: 19, heightMm: 19, visible: true },
    { xMm: 23, yMm: 4, widthMm: 15, heightMm: 7, visible: true },
    { xMm: 23, yMm: 13, widthMm: 15, heightMm: 6, visible: true },
  ]), false)
})

test('short-code insertion stays centered on blank SUPVAN and keeps 1000-growth codes on one line', () => {
  const page = { widthMm: 40, heightMm: 28 }
  const blank = fitElementToPage(createShortCode({ centerXMm: 20, centerYMm: 14 }), page)
  assert.deepEqual([blank.xMm, blank.yMm, blank.widthMm, blank.heightMm], [0, 10, 40, 8])
  assert.equal(blank.content, '{{short_code}}')
  assert.ok(blank.fontSizePt >= 8.504, 'small-paper text stays above the print floor')
  assert.equal(blank.fontWeight, 400)

  const starter = fitElementToPage(createShortCode({ centerXMm: 20, centerYMm: 14 }), page, [
    { type: 'qr', xMm: 2, yMm: 4.5, widthMm: 19, heightMm: 19, visible: true },
    { type: 'text', xMm: 23, yMm: 4, widthMm: 15, heightMm: 7, visible: true },
    { type: 'text', xMm: 23, yMm: 13, widthMm: 15, heightMm: 6, visible: true },
  ])
  const measure = value => [...value].length * (18.515 / 8)
  for (const code of ['DHP-001', 'WWW-1000']) {
    assert.deepEqual(fitTextToBox(code, starter.widthMm, starter.heightMm, starter.fontSizePt * 25.4 / 72, { measure }), { lines: [code], truncated: false })
  }

  const letterPage = { widthMm: 60, heightMm: 40 }
  const blankLetter = fitElementToPage(createShortCode({ centerXMm: 30, centerYMm: 20 }), letterPage)
  assert.deepEqual([blankLetter.xMm, blankLetter.yMm, blankLetter.widthMm, blankLetter.heightMm], [0, 14, 60, 12])
  const letterStarter = fitElementToPage(createShortCode({ centerXMm: 30, centerYMm: 20 }), letterPage, [
    { type: 'qr', xMm: 2, yMm: 9, widthMm: 22, heightMm: 22, visible: true },
    { type: 'text', xMm: 29, yMm: 6, widthMm: 28, heightMm: 7, visible: true },
    { type: 'text', xMm: 29, yMm: 15, widthMm: 28, heightMm: 7, visible: true },
  ])
  assert.deepEqual(fitTextToBox('WWW-1000', letterStarter.widthMm, letterStarter.heightMm, letterStarter.fontSizePt * 25.4 / 72, { measure }), { lines: ['WWW-1000'], truncated: false })
})

test('marks a grapheme wider than its text box as truncated without emitting it', () => {
  assert.deepEqual(
    fitTextToBox('W', 1, 10, 2, { measure: value => [...value].length * 2 }),
    { lines: [], truncated: true },
  )
  assert.deepEqual(
    fitTextToBox('e\u0301', 1, 10, 2, { measure: value => value === 'e\u0301' ? 2 : 0.5 }),
    { lines: ['…'], truncated: true },
  )
})

test('keeps a flag grapheme intact when breaking an overlong word', () => {
  assert.deepEqual(
    fitTextToBox('aa🇺🇸', 3, 10, 1, { measure: text => [...text].length }),
    { lines: ['aa', '🇺🇸'], truncated: false },
  )
})

test('preserves spaces at wrap boundaries like whitespace-pre-wrap', () => {
  const measureLength = { measure: value => value.length }
  assert.deepEqual(wrapText(' a', 1, measureLength), [' ', 'a'])
  assert.deepEqual(wrapText('a  b', 1, measureLength), ['a  ', 'b'])
  assert.deepEqual(wrapText('a   ', 1, measureLength), ['a   '])
})

test('excludes only overflowing trailing spaces from aligned canvas text', () => {
  const measureLength = { measure: value => value.length }
  assert.equal(excludeOverflowingTrailingSpaces('aa bb ', 5, measureLength), 'aa bb')
  assert.equal(excludeOverflowingTrailingSpaces('aa ', 3, measureLength), 'aa ')
  assert.equal(excludeOverflowingTrailingSpaces('aa  ', 3, measureLength), 'aa ')
})

test('keeps combining marks attached when truncation adds an ellipsis', () => {
  const measure = value => value === 'e\u0301' ? 1 : value === 'W' ? 2 : value === '…' ? 0.6 : value === 'e\u0301…' ? 1.8 : 0.5
  assert.deepEqual(fitTextToBox('e\u0301W', 1.2, 10, 2, { measure }), { lines: ['…'], truncated: true })
})

test('preserves square QR and tall-image proportions when another element occupies the center', () => {
  const page = { widthMm: 40, heightMm: 28 }
  const occupied = [{ type: 'rect', xMm: 10, yMm: 5, widthMm: 20, heightMm: 18, visible: true }]
  const qr = fitElementToPage({ type: 'qr', xMm: 5, yMm: -1, widthMm: 30, heightMm: 30 }, page, occupied)
  assert.equal(qr.widthMm, qr.heightMm)
  assert.ok(qr.widthMm >= 18.5, 'SUPVAN QR stays above the four-dot module floor')
  assert.ok(qr.xMm >= 0 && qr.yMm >= 0 && qr.xMm + qr.widthMm <= page.widthMm && qr.yMm + qr.heightMm <= page.heightMm)

  const image = fitElementToPage({ type: 'image', xMm: 14, yMm: -32, widthMm: 12, heightMm: 92 }, page, occupied)
  assert.ok(Math.abs(image.widthMm / image.heightMm - 12 / 92) < 0.002)
})

test('keeps a QR printable and surfaces its overlap instead of shrinking it below the print floor', () => {
  const page = { widthMm: 40, heightMm: 28 }
  const wall = [{ type: 'rect', xMm: 0, yMm: 0, widthMm: 40, heightMm: 28, visible: true }]
  const qr = fitElementToPage({ type: 'qr', xMm: 5, yMm: -1, widthMm: 30, heightMm: 30 }, page, wall)
  assert.ok(qr.widthMm >= 18.5)
  assert.equal(overlapsExisting(qr, wall), true)
})

test('counts stroked shapes when preventing an overlap with the item QR', () => {
  const qr = { type: 'qr', xMm: 2, yMm: 4.5, widthMm: 19, heightMm: 19, visible: true }
  const touching = { type: 'rect', xMm: 21.2, yMm: 8, widthMm: 5, heightMm: 5, strokeWidthMm: 0.4, visible: true }
  assert.equal(overlapsExisting(touching, [qr]), true)
  for (const type of ['rect', 'line', 'circle']) {
    const placed = fitElementToPage({ ...touching, type }, { widthMm: 40, heightMm: 28 }, [qr])
    assert.equal(overlapsExisting(placed, [qr]), false, `${type} is placed clear of the QR's stroked boundary`)
  }
})

test('bounds dense-label search work at the supported 128-element limit', () => {
  const page = { widthMm: 40, heightMm: 28 }
  const dense = Array.from({ length: 128 }, (_, index) => ({
    type: 'rect', xMm: index % 32, yMm: Math.floor(index / 32) * 7,
    widthMm: 8, heightMm: 7, visible: true,
  }))
  const started = performance.now()
  const text = fitElementToPage(createText({ centerXMm: 20, centerYMm: 14 }), page, dense)
  assert.ok(performance.now() - started < 250, 'dense placement avoids unbounded candidate search')
  assert.ok(text.xMm >= 0 && text.yMm >= 0 && text.xMm + text.widthMm <= page.widthMm && text.yMm + text.heightMm <= page.heightMm)
})
