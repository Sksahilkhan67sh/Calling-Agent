import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { type Theme, useTheme } from '../lib/theme'
import { strings } from '../lib/strings'

const options: Theme[] = ['light', 'dark', 'system']

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-card">
        {strings.theme.label}: {strings.theme[theme]}
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          className="min-w-32 rounded-md border border-border bg-bg p-1 shadow-lg"
        >
          <DropdownMenu.RadioGroup value={theme} onValueChange={(v) => setTheme(v as Theme)}>
            {options.map((o) => (
              <DropdownMenu.RadioItem
                key={o}
                value={o}
                className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-card"
              >
                <span aria-hidden className="w-4 text-primary">
                  <DropdownMenu.ItemIndicator>✓</DropdownMenu.ItemIndicator>
                </span>
                {strings.theme[o]}
              </DropdownMenu.RadioItem>
            ))}
          </DropdownMenu.RadioGroup>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}
