// In local dev, '/api' is proxied to Flask by vite.config.js. In production
// (Vercel/Netlify), set VITE_API_BASE to the deployed API's full origin,
// e.g. https://your-space.hf.space — there's no dev proxy in a static build.
const BASE = `${import.meta.env.VITE_API_BASE || ''}/api`

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
