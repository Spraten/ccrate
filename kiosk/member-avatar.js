// Deterministic local identicons; native member identity is the only seed.
export function memberAvatar(id) {
  let seed = 2166136261;
  for (const character of String(id).toLowerCase()) seed = Math.imul(seed ^ character.charCodeAt(0), 16777619);
  const hue = (seed >>> 0) % 360, cells = [];
  seed = seed || 1;
  for (let y = 0; y < 5; y++) for (let x = 0; x < 3; x++) {
    seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5;
    if ((seed & 1) || (x === 2 && y === 2)) {
      cells.push(`<rect x="${x + 1}" y="${y + 1}" width="1" height="1"/>`);
      if (x < 2) cells.push(`<rect x="${5 - x}" y="${y + 1}" width="1" height="1"/>`);
    }
  }
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 7 7" shape-rendering="crispEdges"><rect width="7" height="7" fill="hsl(${hue},25%,94%)"/><g fill="hsl(${hue},58%,38%)">${cells.join('')}</g></svg>`;
  return 'data:image/svg+xml,' + encodeURIComponent(svg);
}

// Both interfaces normalize uploads before sending their small local picture.
export async function prepareMemberAvatar(file) {
  if (!file || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) throw Error('Choose a PNG, JPEG or WebP picture.');
  if (file.size > 20000000) throw Error('Choose a picture smaller than 20 MB.');
  const picture = await createImageBitmap(file, { resizeWidth: 128, resizeHeight: 128, resizeQuality: 'high' });
  try {
    const canvas = document.createElement('canvas'); canvas.width = 128; canvas.height = 128;
    const context = canvas.getContext('2d'); context.fillStyle = '#ffffff'; context.fillRect(0, 0, 128, 128); context.drawImage(picture, 0, 0);
    return canvas.toDataURL('image/jpeg', 0.85);
  } finally { picture.close(); }
}
