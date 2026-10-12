import { TEXT_LINE_HEIGHT } from '../render/text-layout.ts'

export function fitElementToPage(element, page, existing = []) {
  const scale = Math.min(1, page.widthMm / element.widthMm, page.heightMm / element.heightMm)
  const widthMm = Number((element.widthMm * scale).toFixed(3))
  const heightMm = Number((element.heightMm * scale).toFixed(3))
  const fitted = {
    ...element,
    xMm: Number((element.xMm + (element.widthMm - widthMm) / 2).toFixed(3)),
    yMm: Number((element.yMm + (element.heightMm - heightMm) / 2).toFixed(3)),
    widthMm,
    heightMm,
  }
  const occupied = existing.filter(other => other.visible !== false).map(other => paddedBounds(other))
  if (!occupied.length)
    return fitted
  // Dense labels should remain responsive. Leave the item centered and let
  // the host explain any overlap instead of doing a cubic grid search.
  if (occupied.length > 32)
    return fitted

  const minWidth = fitted.type === 'text'
    ? Math.min(fitted.widthMm, 8)
    : fitted.type === 'qr'
      ? Math.min(fitted.widthMm, 18.5)
      : Math.min(fitted.widthMm, 5)
  const minHeight = fitted.type === 'text'
    ? Math.min(fitted.heightMm, Math.ceil(fitted.fontSizePt * 25.4 / 72 * TEXT_LINE_HEIGHT * 1000) / 1000)
    : fitted.type === 'qr'
      ? Math.min(fitted.heightMm, 18.5)
      : Math.min(fitted.heightMm, 5)
  const scales = [1, 0.9, 0.8, 0.7, 0.6, 0.5, 0.475, 0.4, 0.3, 0.2, 0.1]
  if (fitted.type === 'text') {
    for (const scale of scales) {
      const height = Math.max(minHeight, Number((fitted.heightMm * scale).toFixed(3)))
      const width = Math.max(minWidth, Number((fitted.widthMm * scale).toFixed(3)))
      const spot = findSpot(width, height, page, occupied, fitted.strokeWidthMm || 0)
      if (spot)
        return { ...fitted, ...spot, widthMm: width, heightMm: height }
    }
  } else {
    const minScale = Math.min(minWidth / fitted.widthMm, minHeight / fitted.heightMm)
    for (const scale of [...scales, minScale]) {
      if (scale < minScale) continue
      const width = Number((fitted.widthMm * scale).toFixed(3))
      const height = Number((fitted.heightMm * scale).toFixed(3))
      const spot = findSpot(width, height, page, occupied, fitted.strokeWidthMm || 0)
      if (spot)
        return { ...fitted, ...spot, widthMm: width, heightMm: height }
    }
  }
  return fitted
}

export function overlapsExisting(element, existing = []) {
  const box = paddedBounds(element)
  return existing.some(other => other.visible !== false && intersects(box, paddedBounds(other)))
}

function bounds(element) {
  const radians = (element.rotation || 0) * Math.PI / 180
  const width = Math.abs(element.widthMm * Math.cos(radians)) + Math.abs(element.heightMm * Math.sin(radians))
  const height = Math.abs(element.widthMm * Math.sin(radians)) + Math.abs(element.heightMm * Math.cos(radians))
  return { left: element.xMm - (width - element.widthMm) / 2, top: element.yMm - (height - element.heightMm) / 2, right: element.xMm + (width + element.widthMm) / 2, bottom: element.yMm + (height + element.heightMm) / 2 }
}

function paddedBounds(element) {
  const box = bounds(element)
  const pad = element.strokeWidthMm || 0
  return { left: box.left - pad, top: box.top - pad, right: box.right + pad, bottom: box.bottom + pad }
}

function findSpot(width, height, page, occupied, padding = 0) {
  const xs = new Set([0, page.widthMm - width])
  const ys = new Set([0, page.heightMm - height])
  for (const box of occupied) {
    xs.add(box.right); xs.add(box.left - width)
    ys.add(box.bottom); ys.add(box.top - height)
  }
  const candidates = []
  for (const xMm of xs) for (const yMm of ys) {
    if (xMm < 0 || yMm < 0 || xMm + width > page.widthMm || yMm + height > page.heightMm)
      continue
    const candidate = { left: xMm - padding, top: yMm - padding, right: xMm + width + padding, bottom: yMm + height + padding }
    const distance = Math.hypot(xMm + width / 2 - page.widthMm / 2, yMm + height / 2 - page.heightMm / 2)
    candidates.push({ xMm, yMm, distance, box: candidate })
  }
  candidates.sort((a, b) => a.distance - b.distance)
  for (const candidate of candidates.slice(0, 2048)) {
    if (!occupied.some(box => intersects(candidate.box, box)))
      return { xMm: candidate.xMm, yMm: candidate.yMm }
  }
  return null
}

function intersects(a, b) {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top
}
