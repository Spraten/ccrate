import { computeSheetLayout, type SheetLayout } from '../core/sheet-layout'
import type { TemplateDocument } from '../core/schema/template'
import { resolveDocument } from '../core/variables'
import { MM_PER_INCH } from '../core/units'
import { canvasToPngBlob } from './export-image'
import { printReviewedPageBlobs } from './print-browser'
import { MAX_BATCH_ROWS } from './export-pdf'
import { renderToCanvas, type RenderOptions } from './render-engine'

// N-up batch output (round 21): labels tiled onto carrier sheets. Each
// label still renders through the ONE engine (per data row), then gets
// composited onto a white sheet canvas - WYSIWYG parity is untouched.

/** 1mm in PDF points (1pt = 1/72 inch). */
const PT_PER_MM = 72 / 25.4

function guardRows(rows: Array<Record<string, string>>): void {
  if (rows.length === 0)
    throw new Error('Batch export needs at least one data row')
  if (rows.length > MAX_BATCH_ROWS)
    throw new Error(`Batch export supports at most ${MAX_BATCH_ROWS} rows`)
}

/**
 * Render every data row and compose the tiled sheets, SEQUENTIALLY (one
 * label canvas + one sheet canvas alive at a time). Returns PNG blobs.
 */
export async function renderSheetBlobs(
  doc: TemplateDocument,
  rows: Array<Record<string, string>>,
  layout: SheetLayout,
  options: RenderOptions = {},
): Promise<Blob[]> {
  guardRows(rows)
  if (layout.perSheet === 0)
    throw new Error('Label does not fit on the selected sheet')

  async function* labels() {
    for (const row of rows) yield await renderToCanvas(resolveDocument(doc, row), options)
  }
  return composeSheetCanvases(labels(), rows.length, layout, options.dpi ?? 300, [doc.page.widthMm, doc.page.heightMm])
}

/** Compose frozen, already-reviewed label canvases through the same sheet loop. */
export async function renderReviewedSheetBlobs(
  labels: HTMLCanvasElement[],
  layout: SheetLayout,
  dpi = 300,
  labelMm?: [number, number],
  cutGuides = false,
): Promise<Blob[]> {
  async function* canvases() { for (const label of labels) yield label }
  return composeSheetCanvases(canvases(), labels.length, layout, dpi, labelMm, cutGuides)
}

/** Streaming counterpart used when reviewed PNGs are decoded one at a time. */
export function renderReviewedSheetBlobsFrom(
  labels: AsyncIterable<HTMLCanvasElement>,
  count: number,
  layout: SheetLayout,
  dpi = 300,
  labelMm?: [number, number],
  cutGuides = false,
): Promise<Blob[]> {
  return composeSheetCanvases(labels, count, layout, dpi, labelMm, cutGuides)
}

async function composeSheetCanvases(
  labels: AsyncIterable<HTMLCanvasElement>,
  count: number,
  layout: SheetLayout,
  dpi: number,
  labelMm?: [number, number],
  cutGuides = false,
): Promise<Blob[]> {
  if (count === 0 || count > MAX_BATCH_ROWS)
    throw new Error(`Sheet composition requires 1-${MAX_BATCH_ROWS} reviewed labels`)
  if (!Number.isFinite(dpi) || dpi <= 0) throw new Error('Sheet DPI must be positive and finite')
  if (layout.perSheet === 0) throw new Error('Label does not fit on the selected sheet')
  const pxPerMm = dpi / MM_PER_INCH
  if (labelMm) {
    const width = Math.round(labelMm[0] * pxPerMm), height = Math.round(labelMm[1] * pxPerMm)
    for (let row = 0; row < layout.rowsPerSheet; row++) {
      for (let column = 1; column < layout.columns; column++) {
        const previous = layout.positions[row * layout.columns + column - 1]!
        const next = layout.positions[row * layout.columns + column]!
        if (Math.round(next.xMm * pxPerMm) < Math.round(previous.xMm * pxPerMm) + width)
          throw new Error('Reviewed labels overlap after raster rounding; increase the page margin or label gap.')
      }
    }
    for (let row = 1; row < layout.rowsPerSheet; row++) {
      const previous = layout.positions[(row - 1) * layout.columns]!
      const next = layout.positions[row * layout.columns]!
      if (Math.round(next.yMm * pxPerMm) < Math.round(previous.yMm * pxPerMm) + height)
        throw new Error('Reviewed labels overlap after raster rounding; increase the page margin or label gap.')
    }
  }
  const blobs: Blob[] = []
  let sheet: HTMLCanvasElement | null = null
  let ctx: CanvasRenderingContext2D | null = null

  const drawCutGuides = () => {
    if (!cutGuides || !ctx || !labelMm) return
    ctx.save(); ctx.strokeStyle = '#808080'; ctx.lineWidth = Math.max(1, dpi / 300); ctx.setLineDash([dpi / 300, dpi / 600])
    for (let column = 1; column < layout.columns; column++) {
      const leftEdge = Math.round(layout.positions[column - 1]!.xMm * pxPerMm) + Math.round(labelMm[0] * pxPerMm)
      const rightEdge = Math.round(layout.positions[column]!.xMm * pxPerMm)
      const gap = rightEdge - leftEdge
      if (gap < ctx.lineWidth) continue
      ctx.save(); ctx.beginPath(); ctx.rect(leftEdge, 0, gap, sheet!.height); ctx.clip()
      const x = (leftEdge + rightEdge) / 2
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, sheet!.height); ctx.stroke(); ctx.restore()
    }
    for (let row = 1; row < layout.rowsPerSheet; row++) {
      const topEdge = Math.round(layout.positions[(row - 1) * layout.columns]!.yMm * pxPerMm) + Math.round(labelMm[1] * pxPerMm)
      const bottomEdge = Math.round(layout.positions[row * layout.columns]!.yMm * pxPerMm)
      const gap = bottomEdge - topEdge
      if (gap < ctx.lineWidth) continue
      ctx.save(); ctx.beginPath(); ctx.rect(0, topEdge, sheet!.width, gap); ctx.clip()
      const y = (topEdge + bottomEdge) / 2
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(sheet!.width, y); ctx.stroke(); ctx.restore()
    }
    ctx.restore()
  }

  let index = 0
  for await (const label of labels) {
    const cell = index % layout.perSheet
    if (cell === 0) {
      // flush the finished sheet, start a fresh one
      if (sheet) {
        drawCutGuides()
        blobs.push(await canvasToPngBlob(sheet))
      }
      sheet = document.createElement('canvas')
      sheet.width = Math.round(layout.sheet.widthMm * pxPerMm)
      sheet.height = Math.round(layout.sheet.heightMm * pxPerMm)
      if (sheet.width > 16384 || sheet.height > 16384 || sheet.width * sheet.height > 12_000_000)
        throw new Error('Sheet page exceeds renderer pixel limits')
      ctx = sheet.getContext('2d')
      if (!ctx)
        throw new Error('Canvas 2D context unavailable')
      ctx.fillStyle = '#ffffff'
      ctx.fillRect(0, 0, sheet.width, sheet.height)
    }

    if (labelMm && (label.width !== Math.round(labelMm[0] * pxPerMm) || label.height !== Math.round(labelMm[1] * pxPerMm)))
      throw new Error('Invalid reviewed label canvas')
    if (label.width > 16384 || label.height > 16384 || label.width * label.height > 12_000_000)
      throw new Error('Reviewed label exceeds renderer pixel limits')
    const position = layout.positions[cell]!
    ctx!.drawImage(label, Math.round(position.xMm * pxPerMm), Math.round(position.yMm * pxPerMm))
    index++
  }
  if (index !== count) throw new Error('Reviewed sheet canvas count changed during composition')
  if (sheet) {
    drawCutGuides()
    blobs.push(await canvasToPngBlob(sheet))
  }
  return blobs
}

/** Multi-label sheets as one PDF - page size = the carrier sheet. */
export async function exportPdfBatchSheet(
  doc: TemplateDocument,
  rows: Array<Record<string, string>>,
  options: RenderOptions = {},
): Promise<Blob> {
  const layout = computeSheetLayout(doc.page.widthMm, doc.page.heightMm)
  const [{ PDFDocument }, blobs] = await Promise.all([
    import('pdf-lib'),
    renderSheetBlobs(doc, rows, layout, options),
  ])

  const pdf = await PDFDocument.create()
  pdf.setTitle(doc.name)
  pdf.setCreator('Pro Print Designer')

  const widthPt = layout.sheet.widthMm * PT_PER_MM
  const heightPt = layout.sheet.heightMm * PT_PER_MM
  for (const blob of blobs) {
    const image = await pdf.embedPng(await blob.arrayBuffer())
    const page = pdf.addPage([widthPt, heightPt])
    page.drawImage(image, { x: 0, y: 0, width: widthPt, height: heightPt })
  }

  const bytes = await pdf.save()
  return new Blob([bytes as unknown as BlobPart], { type: 'application/pdf' })
}

/** Export the already-composed, frozen PNG pages without resolving template data. */
export async function exportReviewedSheetPdf(pages: Blob[], widthMm: number, heightMm: number, name = 'Reviewed label sheet', isCurrent: () => boolean = () => true): Promise<Blob> {
  if (!pages.length || pages.length > 2 || ![widthMm, heightMm].every(Number.isFinite) || widthMm <= 0 || heightMm <= 0)
    throw new Error('Reviewed Letter PDF requires one or two valid pages')
  const { PDFDocument } = await import('pdf-lib')
  const pdf = await PDFDocument.create()
  pdf.setTitle(name)
  pdf.setCreator('PrintDesignPro')
  // Avoid IEEE-754 residue such as 215.9 mm becoming 612.0000000000001 pt.
  const widthPt = Math.round(widthMm * PT_PER_MM * 1_000_000) / 1_000_000
  const heightPt = Math.round(heightMm * PT_PER_MM * 1_000_000) / 1_000_000
  for (const blob of pages) {
    const image = await pdf.embedPng(await blob.arrayBuffer())
    const page = pdf.addPage([widthPt, heightPt])
    page.drawImage(image, { x: 0, y: 0, width: widthPt, height: heightPt })
  }
  if (!isCurrent()) throw new Error('The current label review changed before PDF export completed.')
  return new Blob([await pdf.save() as unknown as BlobPart], { type: 'application/pdf' })
}

/** Print frozen reviewed page images at exact physical dimensions. Dialog events never confirm physical output. */
export function printReviewedSheetPages(pages: Blob[], widthMm: number, heightMm: number, isCurrent: () => boolean = () => true): Promise<void> {
  return printReviewedPageBlobs(pages, { name: 'Reviewed label sheet', widthMm, heightMm }, isCurrent)
}
