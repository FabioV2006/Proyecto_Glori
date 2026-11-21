export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch('/api' + path, {
    method,
    ...(method === 'GET' ? {} : {
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body ?? {}),
    }),
  })
  const result = await response.json()
  if (!response.ok) throw new Error(result.error ?? 'No se pudo completar la operación.')
  return result as T
}

export function formValues(form: HTMLFormElement) {
  return Object.fromEntries(new FormData(form))
}
