/** Copy text from a click handler. Tries a synchronous fallback first so it still works when the async clipboard API is blocked. */
export async function copyText(text: string): Promise<boolean> {
  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', '')
  area.style.position = 'fixed'
  area.style.top = '0'
  area.style.left = '-9999px'
  document.body.appendChild(area)
  area.focus()
  area.select()
  area.setSelectionRange(0, area.value.length)
  let copied = false
  try {
    copied = document.execCommand('copy')
  } catch {
    copied = false
  }
  area.remove()
  if (copied) return true
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
