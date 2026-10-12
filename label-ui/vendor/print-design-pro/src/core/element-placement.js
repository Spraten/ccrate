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
  const occupied = existing.filter(other => other.visible !== false).map(bounds)
  if (!occupied.length)
    return fitted

  const minWidth = fitted.type === 'text' ? Math.min(fitted.widthMm, 8) : Math.min(fitted.widthMm, 5)
  const minHeight = fitted.type === 'text'
    ? Math.min(fitted.heightMm, fitted.fontSizePt * 25.4 / 72 * 1.2)
    : Math.min(fitted.heightMm, 5)
  if (fitted.type === 'text') {
    for (let height = fitted.heightMm; height >= minHeight; height -= 1) for (let width = fitted.widthMm; width >= minWidth; width -= 1) {
      const spot = findSpot(width, height, page, occupied)
      if (spot)
        return { ...fitted, ...spot, widthMm: width, heightMm: height }
    }
  } else {
    const minScale = Math.min(minWidth / fitted.widthMm, minHeight / fitted.heightMm)
    for (let scale = 1; scale >= minScale; scale -= 0.05) {
      const width = Number((fitted.widthMm * scale).toFixed(3))
      const height = Number((fitted.heightMm * scale).toFixed(3))
      const spot = findSpot(width, height, page, occupied)
      if (spot)
        return { ...fitted, ...spot, widthMm: width, heightMm: height }
    }
  }
  return fitted
}

function bounds(element) {
  const radians = (element.rotation || 0) * Math.PI / 180
  const width = Math.abs(element.widthMm * Math.cos(radians)) + Math.abs(element.heightMm * Math.sin(radians))
  const height = Math.abs(element.widthMm * Math.sin(radians)) + Math.abs(element.heightMm * Math.cos(radians))
  return { left: element.xMm - (width - element.widthMm) / 2, top: element.yMm - (height - element.heightMm) / 2, right: element.xMm + (width + element.widthMm) / 2, bottom: element.yMm + (height + element.heightMm) / 2 }
}

function findSpot(width, height, page, occupied) {
  const xs = new Set([0, page.widthMm - width])
  const ys = new Set([0, page.heightMm - height])
  for (const box of occupied) {
    xs.add(box.right); xs.add(box.left - width)
    ys.add(box.bottom); ys.add(box.top - height)
  }
  let best = null, bestDistance = Infinity
  for (const xMm of xs) for (const yMm of ys) {
    if (xMm < 0 || yMm < 0 || xMm + width > page.widthMm || yMm + height > page.heightMm)
      continue
    const candidate = { left: xMm, top: yMm, right: xMm + width, bottom: yMm + height }
    if (occupied.some(box => candidate.left < box.right && candidate.right > box.left && candidate.top < box.bottom && candidate.bottom > box.top))
      continue
    const distance = Math.hypot(xMm + width / 2 - page.widthMm / 2, yMm + height / 2 - page.heightMm / 2)
    if (distance < bestDistance) { best = { xMm, yMm }; bestDistance = distance }
  }
  return best
}
