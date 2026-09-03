const BASE = '/api'

async function getJSON(url) {
  const res = await fetch(url)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.error || `Request failed: ${res.status}`)
  }
  return res.json()
}

export function searchArticles(query, page = 1) {
  const params = new URLSearchParams({ search: query, page })
  return getJSON(`${BASE}/articles?${params}`)
}

export function getRecommendations(articleId, n = 8) {
  return getJSON(`${BASE}/articles/${articleId}/recommendations?n=${n}`)
}
