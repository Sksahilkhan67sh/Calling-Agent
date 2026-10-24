import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

// Tests opt in per case with server.use(...); unhandled requests fail the test loudly.
export const server = setupServer()

export const unauthorized = () =>
  HttpResponse.json({ detail: 'Authentication credentials were not provided.' }, { status: 401 })

export function mockMe(roles: string[] | null) {
  server.use(
    http.get('*/v1/auth/me', () =>
      roles ? HttpResponse.json({ id: 1, username: 'sahil', roles }) : unauthorized(),
    ),
  )
}

// Refresh fails whenever no test says otherwise, as for a visitor who never signed in.
export function mockNoRefresh() {
  server.use(http.post('*/v1/auth/token/refresh', unauthorized))
}
