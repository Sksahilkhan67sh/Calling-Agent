import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { useAuth } from '../auth/AuthProvider'
import { strings } from '../lib/strings'

export function UserMenu() {
  const { user, logout } = useAuth()
  if (!user) return null
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-card">
        {user.username}
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          className="min-w-48 rounded-md border border-border bg-bg p-1 shadow-lg"
        >
          <DropdownMenu.Label className="px-2 py-1.5 text-xs text-muted">
            {strings.userMenu.roles}
          </DropdownMenu.Label>
          <ul className="flex flex-wrap gap-1 px-2 pb-2">
            {user.roles.map((r) => (
              <li key={r} className="rounded-full border border-border px-2 py-0.5 text-xs">
                {r}
              </li>
            ))}
          </ul>
          <DropdownMenu.Separator className="my-1 h-px bg-border" />
          <DropdownMenu.Item
            onSelect={() => void logout()}
            className="cursor-pointer rounded px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-card"
          >
            {strings.userMenu.signOut}
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}
