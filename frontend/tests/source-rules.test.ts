import { readFileSync, readdirSync } from 'node:fs'
import { join, relative } from 'node:path'

const SRC = join(__dirname, '..', 'src')
const files = readdirSync(SRC, { recursive: true, encoding: 'utf8' })
  .filter((f) => /\.(ts|tsx)$/.test(f))
  .map((f) => ({
    name: relative(SRC, join(SRC, f)).replaceAll('\\', '/'),
    text: readFileSync(join(SRC, f), 'utf8'),
  }))

const offenders = (pattern: RegExp, allowed: string[] = []) =>
  files.filter((f) => pattern.test(f.text) && !allowed.includes(f.name)).map((f) => f.name)

test('source files exist', () => expect(files.length).toBeGreaterThan(5))

test('no raw HTML injection or dynamic code execution', () => {
  expect(offenders(/dangerouslySetInnerHTML|\.innerHTML|\.outerHTML|insertAdjacentHTML/)).toEqual(
    [],
  )
  expect(offenders(/\beval\s*\(|new Function\s*\(/)).toEqual([])
})

test('browser storage is only used by the theme module', () => {
  expect(offenders(/localStorage/, ['lib/theme.ts'])).toEqual([])
  expect(offenders(/sessionStorage|indexedDB/)).toEqual([])
})
