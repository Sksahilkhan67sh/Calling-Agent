import { formatRelative } from '../src/lib/format'
import { safeNext } from '../src/lib/safeRedirect'
import { MAX_UPLOAD_BYTES, validateContactFile } from '../src/lib/upload'

describe('safeNext', () => {
  test.each([
    ['/campaigns/abc?tab=contacts', '/campaigns/abc?tab=contacts'],
    ['/', '/'],
    ['/campaigns#x', '/campaigns#x'],
  ])('keeps same-origin path %s', (input, expected) => expect(safeNext(input)).toBe(expected))

  test.each([
    null,
    '',
    'campaigns',
    '//evil.com',
    '/\\evil.com',
    'https://evil.com',
    'javascript:alert(1)',
    '/ok\nLocation: x',
    '/login',
    '/login?next=/campaigns',
  ])('falls back for %s', (input) => expect(safeNext(input)).toBe('/campaigns'))
})

describe('validateContactFile', () => {
  const file = (name: string, size: number) => new File([new Uint8Array(size)], name)

  test('accepts csv and xlsx up to the limit, any case', () => {
    expect(validateContactFile(file('a.csv', 10))).toBeNull()
    expect(validateContactFile(file('A.XLSX', MAX_UPLOAD_BYTES))).toBeNull()
  })

  test('rejects wrong type, empty and oversized files', () => {
    expect(validateContactFile(file('a.txt', 10))).toMatch(/csv and .xlsx/)
    expect(validateContactFile(file('a.csv', 0))).toMatch(/empty/)
    expect(validateContactFile(file('a.csv', MAX_UPLOAD_BYTES + 1))).toMatch(/10 MB/)
  })
})

test('formatRelative picks a sensible unit', () => {
  const now = Date.parse('2026-10-24T10:00:00Z')
  expect(formatRelative('2026-10-24T09:55:00Z', now)).toBe('5 minutes ago')
  expect(formatRelative('2026-10-22T10:00:00Z', now)).toBe('2 days ago')
})
