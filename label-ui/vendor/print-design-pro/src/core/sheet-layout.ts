// N-up sheet layout (round 21): tile many labels onto one carrier sheet
// (e.g. A4 sticker paper) instead of one page per label. Pure mm math -
// unit-testable, consumed by the sheet composer in render/.

export interface SheetSize {
  widthMm: number
  heightMm: number
}

export interface SheetLayoutOptions {
  marginMm?: number
  gapMm?: number
  orientation?: 'portrait' | 'auto'
}

export interface SheetLayout {
  /** Carrier sheet in the chosen orientation. */
  sheet: SheetSize
  orientation: 'portrait' | 'landscape'
  columns: number
  rowsPerSheet: number
  /** columns x rowsPerSheet - 0 means the label does not fit at all. */
  perSheet: number
  /** Top-left positions (mm) for each cell, row-major. */
  positions: Array<{ xMm: number, yMm: number }>
}

export const SHEET_A4: SheetSize = { widthMm: 210, heightMm: 297 }
/** Printer-safe border around the tiled area. */
export const SHEET_MARGIN_MM = 5
/** Cutting gap between labels. */
export const SHEET_GAP_MM = 2

function layoutFor(labelW: number, labelH: number, sheet: SheetSize, orientation: 'portrait' | 'landscape', margin: number, gap: number): SheetLayout {
  const usableW = sheet.widthMm - margin * 2
  const usableH = sheet.heightMm - margin * 2
  const columns = labelW <= usableW
    ? Math.floor((usableW + gap) / (labelW + gap))
    : 0
  const rowsPerSheet = labelH <= usableH
    ? Math.floor((usableH + gap) / (labelH + gap))
    : 0

  const positions: Array<{ xMm: number, yMm: number }> = []
  for (let row = 0; row < rowsPerSheet; row++) {
    for (let column = 0; column < columns; column++) {
      positions.push({
        xMm: margin + column * (labelW + gap),
        yMm: margin + row * (labelH + gap),
      })
    }
  }
  return { sheet, orientation, columns, rowsPerSheet, perSheet: columns * rowsPerSheet, positions }
}

/**
 * Best A4 tiling for a label: tries both orientations and keeps the one
 * that fits more labels per sheet. `perSheet === 0` = label too large.
 */
export function computeSheetLayout(labelWidthMm: number, labelHeightMm: number, sheet: SheetSize = SHEET_A4, options: SheetLayoutOptions = {}): SheetLayout {
  const margin = options.marginMm ?? SHEET_MARGIN_MM
  const gap = options.gapMm ?? SHEET_GAP_MM
  const orientation = options.orientation ?? 'auto'
  if (![labelWidthMm, labelHeightMm, sheet.widthMm, sheet.heightMm, margin, gap].every(Number.isFinite)
    || labelWidthMm <= 0 || labelHeightMm <= 0 || sheet.widthMm <= 0 || sheet.heightMm <= 0 || margin < 0 || gap < 0)
    throw new Error('Sheet dimensions, margin and gap must be finite and valid')
  const portrait = layoutFor(labelWidthMm, labelHeightMm, sheet, 'portrait', margin, gap)
  if (orientation === 'portrait') return portrait
  const landscape = layoutFor(
    labelWidthMm,
    labelHeightMm,
    { widthMm: sheet.heightMm, heightMm: sheet.widthMm },
    'landscape', margin, gap,
  )
  return landscape.perSheet > portrait.perSheet ? landscape : portrait
}
