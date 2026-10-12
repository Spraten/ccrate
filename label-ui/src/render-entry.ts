import { renderToCanvas } from '@print-design-pro/render/render-engine'
import { ensureDocumentFonts, fontStack } from '@print-design-pro/core/fonts'
import { resolveDocument } from '@print-design-pro/core/variables'
import { fitTextToBox } from '@print-design-pro/render/text-layout'
import { templateDocumentSchema, type TemplateDocument } from '@print-design-pro/core/schema/template'
import { computeSheetLayout } from '@print-design-pro/core/sheet-layout'
import { renderReviewedSheetBlobsFrom } from '@print-design-pro/render/export-sheet'
import { exportReviewedSheetPdf, printReviewedSheetPages } from '@print-design-pro/render/export-sheet'
import { validateLabelDocument, type LabelProfile } from './profile-validation'
import './offline-fonts.css'

export type LabelRenderOptions = { dpi?: number, background?: string | null, profile?: LabelProfile }
export type LabelRenderResult = { png_base64: string, width: number, height: number, warnings: string[] }
export type PaperReview = { png_base64: string, width: number, height: number }
export type PaperGeometry = { page_mm: [number, number], label_mm: [number, number], margin_mm: number, gap_mm: number, dpi?: number, cut_guides: boolean }

export async function renderLabelDocument(document: unknown, options: LabelRenderOptions = {}): Promise<LabelRenderResult> {
  const parsed: TemplateDocument = options.profile
    ? validateLabelDocument(document, options.profile, true)
    : templateDocumentSchema.parse(document)
  const resolved = resolveDocument(parsed)
  const dpi = options.dpi ?? 300
  const pxW = Math.round(parsed.page.widthMm * dpi / 25.4), pxH = Math.round(parsed.page.heightMm * dpi / 25.4)
  if (!Number.isFinite(dpi) || dpi <= 0 || pxW > 16384 || pxH > 16384 || pxW * pxH > 12_000_000)
    throw new Error('Label canvas exceeds renderer pixel limits')
  await ensureDocumentFonts(resolved.elements.flatMap(element => element.type === 'text' ? [element.fontFamily] : []))
  const warnings: string[] = []
  const measure = globalThis.document.createElement('canvas').getContext('2d')
  if (!measure) throw new Error('Canvas 2D context unavailable')
  for (const element of resolved.elements) {
    if (element.type !== 'text' || !element.visible) continue
    const sizeMm = element.fontSizePt * 25.4 / 72
    measure.font = `${element.fontWeight} ${sizeMm}px ${fontStack(element.fontFamily, '"DejaVu Sans", sans-serif')}`
    const fitted = fitTextToBox(element.content, element.widthMm, element.heightMm, sizeMm, { measure: value => measure.measureText(value).width })
    if (element.content && fitted.truncated && fitted.lines.length === 0)
      throw new Error(`Text element “${element.name || element.id}” is too small to print legibly`)
    if (fitted.truncated)
      warnings.push(`Text element “${element.name || element.id}” was shortened with an ellipsis to fit its box.`)
  }
  const canvas = await renderToCanvas(resolved, options)
  const data = canvas.toDataURL('image/png').split(',', 2)[1]
  if (!data) throw new Error('PNG encoder returned no image data')
  return { png_base64: data, width: canvas.width, height: canvas.height, warnings }
}

export async function composePaperSheet(reviews: PaperReview[], geometry: PaperGeometry) {
  if (!Array.isArray(reviews) || reviews.length < 1 || reviews.length > 36) throw new Error('Select 1 to 36 reviewed labels')
  if (geometry.page_mm[0] !== 215.9 || geometry.page_mm[1] !== 279.4 || geometry.dpi !== undefined && geometry.dpi !== 300)
    throw new Error('Paper sheet must be US Letter at 300 DPI')
  if (typeof geometry.cut_guides !== 'boolean') throw new Error('Cut guide setting must be explicit')
  const [labelWidth, labelHeight] = geometry.label_mm
  if (![labelWidth, labelHeight, geometry.margin_mm, geometry.gap_mm].every(Number.isFinite)
    || labelWidth <= 0 || labelHeight <= 0 || geometry.margin_mm < 0 || geometry.gap_mm < 0)
    throw new Error('Paper geometry must be finite and valid')
  const dpi = geometry.dpi ?? 300
  const layout = computeSheetLayout(labelWidth, labelHeight, { widthMm: geometry.page_mm[0], heightMm: geometry.page_mm[1] }, {
    marginMm: geometry.margin_mm, gapMm: geometry.gap_mm, orientation: 'portrait',
  })
  if (!layout.perSheet || Math.ceil(reviews.length / layout.perSheet) > 2) throw new Error('Choose geometry that fits the labels on at most two sheets')
  async function* canvases() {
    for (const review of reviews) {
      const expected = [Math.round(labelWidth * dpi / 25.4), Math.round(labelHeight * dpi / 25.4)]
      if (review.width !== expected[0] || review.height !== expected[1]) throw new Error('Reviewed label dimensions do not exactly match sheet slots')
      const image = new Image()
      image.src = `data:image/png;base64,${review.png_base64}`
      await image.decode()
      if (image.naturalWidth !== review.width || image.naturalHeight !== review.height) throw new Error('Reviewed label PNG dimensions are invalid')
      const canvas = document.createElement('canvas'); canvas.width = review.width; canvas.height = review.height
      const ctx = canvas.getContext('2d'); if (!ctx) throw new Error('Canvas 2D context unavailable')
      ctx.drawImage(image, 0, 0); yield canvas
    }
  }
  const blobs = await renderReviewedSheetBlobsFrom(canvases(), reviews.length, layout, dpi, [labelWidth, labelHeight], geometry.cut_guides)
  const pages: Array<{ png_base64: string, width: number, height: number }> = []
  for (const blob of blobs) {
    const bytes = new Uint8Array(await blob.arrayBuffer())
    let binary = ''; for (const byte of bytes) binary += String.fromCharCode(byte)
    pages.push({ png_base64: btoa(binary), width: Math.round(geometry.page_mm[0] * dpi / 25.4), height: Math.round(geometry.page_mm[1] * dpi / 25.4) })
  }
  return { pages, geometry: { ...geometry, dpi, columns: layout.columns, rows: layout.rowsPerSheet } }
}

export async function exportReviewedPaper(pages: Array<{ image: string, sha256: string }>, geometry: PaperGeometry, format: 'print' | 'pdf', isCurrent: () => boolean = () => true) {
  if (!Array.isArray(pages) || pages.length < 1 || pages.length > 2 || geometry.page_mm[0] !== 215.9 || geometry.page_mm[1] !== 279.4)
    throw new Error('Reviewed output must contain one or two US Letter pages')
  const blobs: Blob[] = []
  let encodedSize = 0
  for (const page of pages) {
    const match = /^data:image\/png;base64,([A-Za-z0-9+/]+={0,2})$/.exec(page.image)
    if (!match) throw new Error('Reviewed page image is not a PNG data URI')
    encodedSize += match[1].length
    if (encodedSize > 16 * 1024 * 1024) throw new Error('Reviewed paper output exceeds 16 MiB')
    const binary = atob(match[1]), bytes = Uint8Array.from(binary, value => value.charCodeAt(0))
    const blob = new Blob([bytes], { type: 'image/png' })
    const bitmap = await createImageBitmap(blob)
    const expected = [Math.round(geometry.page_mm[0] * 300 / 25.4), Math.round(geometry.page_mm[1] * 300 / 25.4)]
    if (bitmap.width !== expected[0] || bitmap.height !== expected[1]) throw new Error('Reviewed page dimensions do not match Letter at 300 DPI')
    bitmap.close()
    blobs.push(blob)
  }
  if (!isCurrent()) throw new Error('The current label review changed before export.')
  if (format === 'print') {
    await printReviewedSheetPages(blobs, geometry.page_mm[0], geometry.page_mm[1], isCurrent)
    return { status: 'dialog-closed-unconfirmed' }
  }
  return exportReviewedSheetPdf(blobs, geometry.page_mm[0], geometry.page_mm[1], 'Reviewed label sheet', isCurrent)
}

declare global {
  interface Window {
    renderLabelDocument: typeof renderLabelDocument
    printDesignSheetLayout: typeof computeSheetLayout
    composePaperSheet: typeof composePaperSheet
    exportReviewedPaper: typeof exportReviewedPaper
  }
}
window.renderLabelDocument = renderLabelDocument
window.printDesignSheetLayout = computeSheetLayout
window.composePaperSheet = composePaperSheet
window.exportReviewedPaper = exportReviewedPaper
document.querySelector('#app')?.replaceChildren(Object.assign(document.createElement('p'), { textContent: 'Offline label renderer ready' }))
