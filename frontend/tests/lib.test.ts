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

describe('uuid, transitions and durations', () => {
  test('isUuid accepts only canonical UUIDs', async () => {
    const { isUuid } = await import('../src/lib/uuid')
    expect(isUuid('6f1c2b1e-6f3a-4c55-8f55-0d6d0d6d0d6d')).toBe(true)
    for (const bad of ['', 'abc', '../etc', '6f1c2b1e-6f3a-4c55-8f55-0d6d0d6d0d6d/x', undefined])
      expect(isUuid(bad)).toBe(false)
  })

  test('statusAction names paused->active a resume, draft->active an activate', async () => {
    const { statusAction, NEXT_STATUSES } = await import('../src/lib/transitions')
    expect(statusAction('paused', 'active')).toBe('resume')
    expect(statusAction('draft', 'active')).toBe('activate')
    expect(statusAction('active', 'completed')).toBe('complete')
    expect(NEXT_STATUSES.completed).toEqual([])
  })

  test('formatDuration reads seconds as minutes', async () => {
    const { formatDuration } = await import('../src/lib/format')
    expect(formatDuration(30)).toBe('30 s')
    expect(formatDuration(600)).toBe('10 min')
    expect(formatDuration(90)).toBe('1 min 30 s')
    expect(formatDuration(0)).toBe('0 s')
    expect(formatDuration(-1)).toBe('')
  })
})
