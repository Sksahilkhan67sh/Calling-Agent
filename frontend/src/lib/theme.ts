import { useEffect, useState } from 'react'

export type Theme = 'light' | 'dark' | 'system'

// The only browser storage in the app, and it holds nothing but this non-sensitive choice.
const KEY = 'theme'

export function getTheme(): Theme {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

export function applyTheme(theme: Theme) {
  const dark =
    theme === 'dark' || (theme === 'system' && matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.classList.toggle('dark', dark)
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(getTheme)

  useEffect(() => {
    applyTheme(theme)
    if (theme !== 'system') return
    const mq = matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => applyTheme('system')
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [theme])

  const setTheme = (next: Theme) => {
    try {
      if (next === 'system') localStorage.removeItem(KEY)
      else localStorage.setItem(KEY, next)
    } catch {
      // Storage blocked: the choice still applies for this page view.
    }
    setThemeState(next)
  }

  return { theme, setTheme }
}
