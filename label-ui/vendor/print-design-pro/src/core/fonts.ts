// Local-only fonts for the isolated CACI-Create editor build.
// Upstream commit eb118cc05b169c554066d823c44dc179aa3b96bb loads Google Fonts;
// this narrow patch removes runtime network access and never substitutes a missing face.
export interface DocumentFont { family: string, stack: string }

export const DOCUMENT_FONTS: DocumentFont[] = [
  { family: 'DejaVu Sans', stack: '"DejaVu Sans", sans-serif' },
]

export function fontStack(family: string, fallback: string): string {
  if (!family) return '"DejaVu Sans", sans-serif'
  return DOCUMENT_FONTS.find(font => font.family === family)?.stack ?? fallback
}

export async function ensureFontLoaded(family: string): Promise<void> {
  // The upstream empty-family sentinel means the default face. Pin that face
  // to the same bundled font used by the renderer so it never means OS fallback.
  if (!family) family = 'DejaVu Sans'
  if (!DOCUMENT_FONTS.some(font => font.family === family))
    throw new Error(`Unsupported document font: ${family || '(empty)'}`)
  if (family !== 'DejaVu Sans' || typeof document === 'undefined') return
  const faces = await document.fonts.load('400 16px "DejaVu Sans"')
  if (!faces.length || !document.fonts.check('400 16px "DejaVu Sans"'))
    throw new Error('Bundled DejaVu Sans font failed to load')
}

export async function ensureDocumentFonts(families: Iterable<string>): Promise<void> {
  const requested = [...new Set([...families].map(family => family || 'DejaVu Sans'))]
  await Promise.all(requested.map(ensureFontLoaded))
}
