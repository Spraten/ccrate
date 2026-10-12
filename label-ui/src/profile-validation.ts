import { templateDocumentSchema, type TemplateDocument } from '@print-design-pro/core/schema/template'
import { aabbsIntersect, elementAabb } from '@print-design-pro/core/geometry'
import starterDocuments from './starter-documents.json'

export type LabelProfile = 'supvan' | 'letter'
export const SUPVAN_MM: [number, number] = [40, 28]
export const LETTER_LABEL_MM: [number, number] = [60, 40]
export const SYNTHETIC_ITEM_ID = '10000000-0000-4000-8000-000000000001'
export const MAX_ELEMENTS = 128
export const MAX_CONTENT_CHARS = 1000
export const mmToFontPoints = (mm: number): number => mm * 72 / 25.4

const dimensions: Record<LabelProfile, [number, number]> = { supvan: SUPVAN_MM, letter: LETTER_LABEL_MM }

export function validateLabelDocument(document: unknown, profile: LabelProfile, allowBoundItemPath = false): TemplateDocument {
  if (profile !== 'supvan' && profile !== 'letter') throw new Error('Unknown label profile')
  const doc = templateDocumentSchema.parse(document)
  const [defaultWidth, defaultHeight] = dimensions[profile]
  const width = doc.page.widthMm
  const height = doc.page.heightMm
  if (profile === 'supvan' && (width !== defaultWidth || height !== defaultHeight))
    throw new Error('SUPVAN label size is fixed at 40 x 28 mm')
  const dpi = profile === 'supvan' ? 203.2 : 300
  const pxWidth = Math.round(width * dpi / 25.4), pxHeight = Math.round(height * dpi / 25.4)
  if (![width, height].every(Number.isFinite) || width <= 0 || height <= 0 || pxWidth > 16384 || pxHeight > 16384 || pxWidth * pxHeight > 12_000_000)
    throw new Error('Label dimensions exceed renderer limits')
  if (doc.elements.length > MAX_ELEMENTS) throw new Error('A label may contain at most 128 elements')
  const itemQrs = doc.elements.filter(element => element.type === 'qr')
  if (itemQrs.length !== 1 || !itemQrs[0]!.visible) throw new Error('A printable label needs exactly one visible item QR')
  const content = doc.elements.flatMap(element => element.type === 'table'
    ? [...element.columns.map(column => column.title), ...element.rows.flat()]
    : 'content' in element ? [element.content] : [])
  if ([...content, ...Object.values(doc.variables)].some(value => value.length > MAX_CONTENT_CHARS))
    throw new Error('Label content exceeds 1000 characters')

  const minFont = mmToFontPoints(profile === 'supvan' ? 2.25 : 3)
  for (const element of doc.elements) {
    if (element.type === 'text') {
      if (element.fontFamily && element.fontFamily !== 'DejaVu Sans') throw new Error('Only bundled DejaVu Sans is printable')
      if (element.fontSizePt < minFont) throw new Error(`Text must be at least ${profile === 'supvan' ? '2.25' : '3'} mm`)
    }
    if (element.type === 'qr') {
      if (element.content !== '{{item_path}}' && !(allowBoundItemPath && /^\/item\/[0-9a-f-]{36}$/i.test(element.content))) throw new Error('QR content is bound by the item renderer')
      if (element.color.toLowerCase() !== '#000000' || element.backgroundColor.toLowerCase() !== '#ffffff')
        throw new Error('Printable item QR must be black on white')
      if (element.widthMm !== element.heightMm || Math.abs(element.rotation % 90) > 1e-8
        || Math.floor(Math.floor(element.widthMm * dpi / 25.4) / 37) < 4)
        throw new Error('Item QR must be square and provide at least four dots per module')
      const qrBounds = elementAabb(element)
      if (qrBounds.left < 0 || qrBounds.top < 0 || qrBounds.right > width || qrBounds.bottom > height)
        throw new Error('QR must fit inside the label')
      for (const other of doc.elements) {
        if (other.id === element.id || !other.visible) continue
        const raw = elementAabb(other)
        const pad = 'strokeWidthMm' in other ? other.strokeWidthMm : 0
        const otherBounds = { ...raw, left: raw.left - pad, top: raw.top - pad, right: raw.right + pad, bottom: raw.bottom + pad }
        if (aabbsIntersect(qrBounds, otherBounds))
          throw new Error('QR elements cannot overlap other visible elements')
      }
    }
    if (element.type === 'barcode' && element.content !== '{{asset_code}}')
      throw new Error('Barcode content is bound to the native asset code')
    if (element.type === 'image' && element.src) {
      const match = /^data:image\/(png|jpeg);base64,([A-Za-z0-9+/=]+)$/.exec(element.src)
      if (!match || atob(match[2]!).length > 512 * 1024) throw new Error('Images must be PNG or JPEG files up to 512 KiB')
    }
  }
  return doc
}

export function createStarter(profile: LabelProfile, layout: 'left' | 'top' | 'compact'): TemplateDocument {
  return validateLabelDocument(structuredClone(starterDocuments[`starter:${profile}:${layout}` as keyof typeof starterDocuments]), profile)
}

export const STARTER_IDS = (['supvan', 'letter'] as const).flatMap(profile =>
  (['left', 'top', 'compact'] as const).map(layout => `starter:${profile}:${layout}`))
