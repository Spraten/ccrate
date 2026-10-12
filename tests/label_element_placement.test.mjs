import assert from 'node:assert/strict'
import test from 'node:test'
import { fitElementToPage } from '../label-ui/vendor/print-design-pro/src/core/element-placement.js'

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
  const text = fitElementToPage(
    { type: 'text', xMm: -10, yMm: 8, widthMm: 60, heightMm: 12, fontSizePt: 14 },
    { widthMm: 40, heightMm: 28 },
    [
      { type: 'qr', xMm: 2, yMm: 4.5, widthMm: 19, heightMm: 19, visible: true },
      { type: 'text', xMm: 23, yMm: 4, widthMm: 15, heightMm: 7, visible: true },
      { type: 'text', xMm: 23, yMm: 13, widthMm: 15, heightMm: 6, visible: true },
    ],
  )
  assert.deepEqual([text.xMm, text.yMm, text.widthMm, text.heightMm], [21, 19, 19, 8])
})

test('preserves square QR and tall-image proportions when another element occupies the center', () => {
  const page = { widthMm: 40, heightMm: 28 }
  const occupied = [{ type: 'rect', xMm: 10, yMm: 5, widthMm: 20, heightMm: 18, visible: true }]
  const qr = fitElementToPage({ type: 'qr', xMm: 5, yMm: -1, widthMm: 30, heightMm: 30 }, page, occupied)
  assert.equal(qr.widthMm, qr.heightMm)
  assert.ok(qr.xMm >= 0 && qr.yMm >= 0 && qr.xMm + qr.widthMm <= page.widthMm && qr.yMm + qr.heightMm <= page.heightMm)

  const image = fitElementToPage({ type: 'image', xMm: 14, yMm: -32, widthMm: 12, heightMm: 92 }, page, occupied)
  assert.ok(Math.abs(image.widthMm / image.heightMm - 12 / 92) < 0.002)
})
