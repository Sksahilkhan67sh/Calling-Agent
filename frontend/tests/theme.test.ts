import { renderHook, act } from '@testing-library/react'
import { applyTheme, getTheme, useTheme } from '../src/lib/theme'

test('defaults to system and ignores junk in storage', () => {
  expect(getTheme()).toBe('system')
  localStorage.setItem('theme', 'neon')
  expect(getTheme()).toBe('system')
})

test('applyTheme toggles the dark class', () => {
  applyTheme('dark')
  expect(document.documentElement).toHaveClass('dark')
  applyTheme('light')
  expect(document.documentElement).not.toHaveClass('dark')
})

test('setTheme persists only the theme choice and system clears it', () => {
  const { result } = renderHook(() => useTheme())
  act(() => result.current.setTheme('dark'))
  expect(localStorage.getItem('theme')).toBe('dark')
  expect(localStorage.length).toBe(1)
  expect(document.documentElement).toHaveClass('dark')
  act(() => result.current.setTheme('system'))
  expect(localStorage.getItem('theme')).toBeNull()
})
