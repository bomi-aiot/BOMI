// 실제 API 호출용 fetch 래퍼. USE_MOCK_API=false 일 때 HttpBomiService 가 사용한다.

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

export async function httpGet<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  })
  return parseJson<T>(res)
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
