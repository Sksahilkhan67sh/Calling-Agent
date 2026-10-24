import '@testing-library/jest-dom/vitest'
import { toHaveNoViolations } from 'jest-axe'
import { afterEach, expect } from 'vitest'

expect.extend(toHaveNoViolations)

// jsdom has no matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }),
})

afterEach(() => {
  localStorage.clear()
  document.documentElement.classList.remove('dark')
})
