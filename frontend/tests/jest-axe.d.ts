declare module 'jest-axe' {
  export function axe(html: Element | string): Promise<unknown>
  export const toHaveNoViolations: {
    toHaveNoViolations: (results: unknown) => { pass: boolean; message: () => string }
  }
}
