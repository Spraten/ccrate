import { describe, expect, it } from 'vitest'
import { fitTextToBox, wrapText, type TextMeasurer } from '../text-layout'

// Monospace width model: every char is 1 unit wide - makes cases exact.
const mono: TextMeasurer = { measure: text => text.length }

describe('wrapText', () => {
  it('keeps short content on one line', () => {
    expect(wrapText('hello', 10, mono)).toEqual(['hello'])
  })

  it('preserves explicit newlines including empty lines', () => {
    expect(wrapText('a\n\nb', 10, mono)).toEqual(['a', '', 'b'])
  })

  it('treats Windows and legacy carriage-return line endings as explicit breaks', () => {
    expect(wrapText('first\r\nsecond\rthird', 10, mono)).toEqual(['first', 'second', 'third'])
  })

  it('greedy-wraps on spaces', () => {
    // "aa bb cc" with width 5: "aa bb" fits, "cc" wraps.
    expect(wrapText('aa bb cc', 5, mono)).toEqual(['aa bb ', 'cc'])
  })

  it('preserves leading spaces like whitespace-pre-wrap', () => {
    expect(wrapText('  ABC', 20, { measure: s => s.length })).toEqual(['  ABC'])
  })

  it('keeps leading spaces on the line where they wrap', () => {
    expect(wrapText(' a', 1, { measure: s => s.length })).toEqual([' ', 'a'])
  })

  it('keeps a space before a wrapped word on the previous line', () => {
    expect(wrapText('a b', 2, { measure: s => s.length })).toEqual(['a ', 'b'])
    expect(wrapText('a  b', 3, { measure: s => s.length })).toEqual(['a  ', 'b'])
    expect(wrapText('a  b', 1, { measure: s => s.length })).toEqual(['a  ', 'b'])
    expect(wrapText('a   ', 1, { measure: s => s.length })).toEqual(['a   '])
  })

  it('does not turn wrapped trailing spaces into an extra empty line', () => {
    expect(wrapText('a ', 1, { measure: s => s.length })).toEqual(['a '])
  })

  it('breaks a word wider than the box at character level', () => {
    expect(wrapText('abcdefgh', 3, mono)).toEqual(['abc', 'def', 'gh'])
  })

  it('flushes the current line before an overlong word breaks', () => {
    expect(wrapText('hi abcdefgh', 4, mono)).toEqual(['hi ', 'abcd', 'efgh'])
  })

  it('exact-fit line does not wrap', () => {
    expect(wrapText('abcde', 5, mono)).toEqual(['abcde'])
  })

  it('handles empty content', () => {
    expect(wrapText('', 5, mono)).toEqual([''])
  })

  it('keeps unicode text intact (per-character break on Vietnamese)', () => {
    const lines = wrapText('Xin chào thế giới', 8, mono)
    expect(lines).toEqual(['Xin chào ', 'thế giới'])
    expect(lines.every(line => line.trimEnd().length <= 8)).toBe(true)
  })

  it('adds a visible ellipsis when wrapped text exceeds the box height', () => {
    const fitted = fitTextToBox('Ω abcdef', 4, 1.3, 1, { measure: text => [...text].length })
    expect(fitted).toEqual({ lines: ['Ω …'], truncated: true })
  })
})
