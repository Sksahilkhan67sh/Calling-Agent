// E.164 country calling codes are 1, 2 or 3 digits, decided by the leading digits.
const ONE = /^[17]/
const TWO = /^(2[07]|3[0-469]|4[0134-9]|5[1-8]|6[0-6]|8[1246]|9[0-58])/

// "+919876547678" -> "+91•••••7678". Anything that is not a plausible E.164 number is fully masked,
// so a malformed value can never leak through.
export function maskPhone(phone: string): string {
  const digits = phone.replace(/^\+/, '')
  if (!/^\d{8,15}$/.test(digits)) return '••••••••'
  const cc = ONE.test(digits) ? 1 : TWO.test(digits) ? 2 : 3
  return `+${digits.slice(0, cc)}•••••${digits.slice(-4)}`
}
