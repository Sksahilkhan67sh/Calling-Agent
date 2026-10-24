const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

// Route params are validated before they reach a URL or a request.
export const isUuid = (value: string | null | undefined): value is string =>
  typeof value === 'string' && UUID.test(value)
