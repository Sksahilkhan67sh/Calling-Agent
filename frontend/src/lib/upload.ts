import { strings } from './strings'

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024

// Obviously fake numbers (they are not valid), so a sample can never dial a real person.
// A data: URL needs no object-URL cleanup.
export const SAMPLE_CSV_HREF = `data:text/csv;charset=utf-8,${encodeURIComponent('phone_number\n+10000000000\n+10000000001\n')}`

// Client-side checks are for fast feedback only; the server is the real validator.
export function validateContactFile(file: File): string | null {
  if (!/\.(csv|xlsx)$/i.test(file.name)) return strings.createCampaign.fileType
  if (file.size === 0) return strings.createCampaign.fileEmpty
  if (file.size > MAX_UPLOAD_BYTES) return strings.createCampaign.fileSize
  return null
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}
