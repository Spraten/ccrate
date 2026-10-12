import type { QrElement } from '../../core/schema/elements'

// Render QR modules as integer device-pixel cells with an explicit four-cell
// white quiet zone. Any geometry that cannot meet that contract fails closed.
export async function paintQr(ctx: CanvasRenderingContext2D, element: QrElement, pxPerMm: number): Promise<void> {
  if (!element.content) throw new Error('QR content is required')
  if (Math.abs(element.widthMm - element.heightMm) > 1e-7) throw new Error('QR geometry must be square')
  if (Math.abs(element.rotation % 90) > 1e-8) throw new Error('QR rotation must be a multiple of 90 degrees')
  const matrix = ctx.getTransform()
  if (Math.abs(Math.hypot(matrix.a, matrix.b) - pxPerMm) > 1e-5 || Math.abs(Math.hypot(matrix.c, matrix.d) - pxPerMm) > 1e-5
    || Math.abs(matrix.a * matrix.c + matrix.b * matrix.d) > 1e-5)
    throw new Error('QR must use the label device-pixel grid')

  const { default: QRCode } = await import('qrcode')
  const qr = QRCode.create(element.content, { errorCorrectionLevel: element.ecLevel })
  const modules = qr.modules.size
  const totalModules = modules + 8
  const sideMm = Math.min(element.widthMm, element.heightMm)
  const sidePx = Math.floor(sideMm * pxPerMm + 1e-8)
  const modulePx = Math.floor(sidePx / totalModules)
  if (modulePx < 4) throw new Error('QR needs at least four dots per module plus a four-module quiet zone')
  const rasterSidePx = totalModules * modulePx

  const renderedSideMm = rasterSidePx / pxPerMm
  const leftMm = (element.widthMm - renderedSideMm) / 2
  const topMm = (element.heightMm - renderedSideMm) / 2
  const origin = matrix.transformPoint(new DOMPoint(leftMm, topMm))
  const snappedX = Math.round(origin.x), snappedY = Math.round(origin.y)
  // A <=0.5 px origin snap absorbs the upstream editor's 0.1 mm drag grid
  // without changing stored positions or making most Letter placements fail.
  const inverse = matrix.inverse()
  const snappedLocal = inverse.transformPoint(new DOMPoint(snappedX, snappedY))
  const drawX = snappedLocal.x, drawY = snappedLocal.y
  const corners = [
    matrix.transformPoint(new DOMPoint(0, 0)),
    matrix.transformPoint(new DOMPoint(element.widthMm, 0)),
    matrix.transformPoint(new DOMPoint(0, element.heightMm)),
    matrix.transformPoint(new DOMPoint(element.widthMm, element.heightMm)),
  ]
  const minX = Math.min(...corners.map(point => point.x)), maxX = Math.max(...corners.map(point => point.x))
  const minY = Math.min(...corners.map(point => point.y)), maxY = Math.max(...corners.map(point => point.y))
  const rasterRight = drawX + rasterSidePx / pxPerMm
  const rasterBottom = drawY + rasterSidePx / pxPerMm
  const rasterCorners = [
    matrix.transformPoint(new DOMPoint(drawX, drawY)),
    matrix.transformPoint(new DOMPoint(rasterRight, drawY)),
    matrix.transformPoint(new DOMPoint(drawX, rasterBottom)),
    matrix.transformPoint(new DOMPoint(rasterRight, rasterBottom)),
  ]
  const qrMinX = Math.min(...rasterCorners.map(point => point.x)), qrMaxX = Math.max(...rasterCorners.map(point => point.x))
  const qrMinY = Math.min(...rasterCorners.map(point => point.y)), qrMaxY = Math.max(...rasterCorners.map(point => point.y))
  if (Math.abs(origin.x - snappedX) > .500001 || Math.abs(origin.y - snappedY) > .500001
    || qrMinX < minX - 1e-8 || qrMinY < minY - 1e-8
    || qrMaxX > maxX + 1e-8 || qrMaxY > maxY + 1e-8)
    throw new Error('Snapped QR and its quiet zone must fit inside the element')

  const raster = document.createElement('canvas')
  raster.width = totalModules * modulePx
  raster.height = raster.width
  const rasterCtx = raster.getContext('2d')
  if (!rasterCtx) throw new Error('QR canvas context unavailable')
  rasterCtx.fillStyle = element.backgroundColor
  rasterCtx.fillRect(0, 0, raster.width, raster.height)
  rasterCtx.fillStyle = element.color
  for (let y = 0; y < modules; y++) {
    for (let x = 0; x < modules; x++) {
      if (qr.modules.get(y, x))
        rasterCtx.fillRect((x + 4) * modulePx, (y + 4) * modulePx, modulePx, modulePx)
    }
  }
  ctx.drawImage(raster, drawX, drawY, raster.width / pxPerMm, raster.height / pxPerMm)
}
