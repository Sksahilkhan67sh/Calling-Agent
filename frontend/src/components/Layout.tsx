import { useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { strings } from '../lib/strings'
import { OfflineBanner } from './OfflineBanner'
import { Breadcrumbs } from './Breadcrumbs'
import { ThemeToggle } from './ThemeToggle'
import { ThrottleBanner } from './ThrottleBanner'
import { UserMenu } from './UserMenu'

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `block rounded-md px-3 py-2 text-sm ${isActive ? 'bg-card font-semibold text-primary' : 'hover:bg-card'}`

export function Layout() {
  const [menuOpen, setMenuOpen] = useState(false)
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-fg"
      >
        {strings.skipToContent}
      </a>
      <OfflineBanner />
      <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex items-center gap-3">
          <button
            type="button"
            className="rounded-md border border-border px-3 py-1.5 text-sm md:hidden"
            aria-expanded={menuOpen}
            aria-controls="main-nav"
            onClick={() => setMenuOpen((o) => !o)}
          >
            {menuOpen ? strings.nav.close : strings.nav.open}
          </button>
          <Link to="/" className="font-semibold">
            {strings.appName}
          </Link>
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <UserMenu />
        </div>
      </header>
      <ThrottleBanner />
      <div className="flex flex-1 flex-col md:flex-row">
        <nav
          id="main-nav"
          aria-label={strings.nav.label}
          className={`${menuOpen ? 'block' : 'hidden'} border-b border-border p-3 md:block md:w-56 md:border-r md:border-b-0`}
        >
          <NavLink to="/campaigns" className={linkClass} onClick={() => setMenuOpen(false)}>
            {strings.nav.campaigns}
          </NavLink>
        </nav>
        <main id="main" className="min-w-0 flex-1 p-4 md:p-6">
          <Breadcrumbs />
          <Outlet />
        </main>
      </div>
    </div>
  )
}
