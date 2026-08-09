// 실제 API 호출용 fetch 래퍼. HttpBomiService 가 모든 요청에 사용한다.

async function parseJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = ''
    try {
      detail = await res.text()
    } catch {
      detail = ''
    }
    throw new Error(`요청 실패 (${res.status})${detail ? `: ${detail}` : ''}`)
  }
  return (await res.json()) as T
}

const TRANSIENT_GET_STATUSES = new Set([502, 503, 504])
const GET_RETRY_DELAYS_MS = [300, 900]

const wait = (delayMs: number): Promise<void> =>
  new Promise((resolve) => window.setTimeout(resolve, delayMs))

export async function httpGet<T>(url: string): Promise<T> {
  for (let attempt = 0; ; attempt += 1) {
    const res = await fetch(url, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    })

    if (
      !TRANSIENT_GET_STATUSES.has(res.status) ||
      attempt >= GET_RETRY_DELAYS_MS.length
    ) {
      return parseJson<T>(res)
    }

    await wait(GET_RETRY_DELAYS_MS[attempt])
  }
}

export async function httpPost<T>(url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(body ?? {}),
  })
  return parseJson<T>(res)
}

export async function httpPut<T>(url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(body ?? {}),
  })
  return parseJson<T>(res)
}

export async function httpDelete<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
  })
  return parseJson<T>(res)
}
