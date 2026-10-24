import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { RouterProvider, createMemoryRouter } from 'react-router-dom'
import { routes } from '../src/router'
import { strings } from '../src/lib/strings'

function renderAt(path: string, extra: typeof routes = routes) {
  return render(<RouterProvider router={createMemoryRouter(extra, { initialEntries: [path] })} />)
}

test('unknown route renders the 404 page inside the shell', async () => {
  const { container } = renderAt('/nope')
  expect(screen.getByRole('heading', { name: strings.notFound.title })).toBeInTheDocument()
  expect(screen.getByRole('navigation', { name: strings.nav.label })).toBeInTheDocument()
  expect(await axe(container)).toHaveNoViolations()
})

test('forbidden route renders the 403 page', async () => {
  const { container } = renderAt('/forbidden')
  expect(screen.getByRole('heading', { name: strings.forbidden.title })).toBeInTheDocument()
  expect(await axe(container)).toHaveNoViolations()
})

test('a crashing route shows the generic error page and no error details', () => {
  const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
  const Boom = () => {
    throw new Error('+10000000000 secret transcript')
  }
  renderAt('/boom', [{ ...routes[0]!, children: [{ path: 'boom', element: <Boom /> }] }])
  expect(screen.getByRole('heading', { name: strings.error.title })).toBeInTheDocument()
  expect(document.body).not.toHaveTextContent('secret transcript')
  spy.mockRestore()
})

test('mobile menu button toggles aria-expanded', async () => {
  renderAt('/nope')
  const button = screen.getByRole('button', { name: strings.nav.open })
  expect(button).toHaveAttribute('aria-expanded', 'false')
  await userEvent.click(button)
  expect(screen.getByRole('button', { name: strings.nav.close })).toHaveAttribute(
    'aria-expanded',
    'true',
  )
})

test('offline banner appears and disappears with connectivity', () => {
  renderAt('/nope')
  expect(screen.queryByText(strings.offline)).not.toBeInTheDocument()
  const set = (v: boolean) => vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(v)
  set(false)
  act(() => window.dispatchEvent(new Event('offline')))
  expect(screen.getByRole('status')).toHaveTextContent(strings.offline)
  set(true)
  act(() => window.dispatchEvent(new Event('online')))
  expect(screen.queryByText(strings.offline)).not.toBeInTheDocument()
})

test('theme menu switches the theme', async () => {
  renderAt('/nope')
  await userEvent.click(screen.getByRole('button', { name: new RegExp(strings.theme.label) }))
  await userEvent.click(await screen.findByRole('menuitemradio', { name: strings.theme.dark }))
  expect(document.documentElement).toHaveClass('dark')
  expect(localStorage.getItem('theme')).toBe('dark')
})
