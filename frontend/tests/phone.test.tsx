import { act, fireEvent, render, screen } from '@testing-library/react'
import { PhoneCell } from '../src/components/PhoneCell'
import { strings } from '../src/lib/strings'

const PHONE = '+919876547678'

beforeEach(() => vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] }))
afterEach(() => vi.useRealTimers())

test('shows only the masked number until revealed, and the full number is not in the DOM before that', () => {
  const { container } = render(<PhoneCell phone={PHONE} />)
  expect(screen.getByTestId('phone')).toHaveTextContent('+91•••••7678')
  expect(container.innerHTML).not.toContain('9876547678')
  // The button label never contains the number either
  expect(screen.getByRole('button', { name: strings.phone.reveal })).toHaveAttribute(
    'aria-pressed',
    'false',
  )
})

test('reveal shows the full number; it re-masks after 30 seconds, not before', () => {
  render(<PhoneCell phone={PHONE} />)
  fireEvent.click(screen.getByRole('button', { name: strings.phone.reveal }))
  expect(screen.getByTestId('phone')).toHaveTextContent(PHONE)
  act(() => void vi.advanceTimersByTime(29_000))
  expect(screen.getByTestId('phone')).toHaveTextContent(PHONE)
  act(() => void vi.advanceTimersByTime(1_500))
  expect(screen.getByTestId('phone')).toHaveTextContent('+91•••••7678')
  expect(screen.getByRole('button', { name: strings.phone.reveal })).toBeInTheDocument()
})

test('the button hides the number again straight away', () => {
  render(<PhoneCell phone={PHONE} />)
  fireEvent.click(screen.getByRole('button', { name: strings.phone.reveal }))
  fireEvent.click(screen.getByRole('button', { name: strings.phone.hide }))
  expect(screen.getByTestId('phone')).toHaveTextContent('+91•••••7678')
})

test('hiding the tab re-masks the number', () => {
  render(<PhoneCell phone={PHONE} />)
  fireEvent.click(screen.getByRole('button', { name: strings.phone.reveal }))
  const spy = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
  act(() => void document.dispatchEvent(new Event('visibilitychange')))
  expect(screen.getByTestId('phone')).toHaveTextContent('+91•••••7678')
  spy.mockRestore()
})

test('a second reveal restarts the 30 second window', () => {
  render(<PhoneCell phone={PHONE} />)
  const toggle = () => fireEvent.click(screen.getByRole('button', { pressed: undefined }))
  toggle() // reveal
  act(() => void vi.advanceTimersByTime(20_000))
  toggle() // hide
  toggle() // reveal again
  act(() => void vi.advanceTimersByTime(20_000))
  expect(screen.getByTestId('phone')).toHaveTextContent(PHONE)
  act(() => void vi.advanceTimersByTime(11_000))
  expect(screen.getByTestId('phone')).toHaveTextContent('+91•••••7678')
})
