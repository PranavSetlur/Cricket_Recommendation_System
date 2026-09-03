import { useEffect, useRef, useState } from 'react'
import ArticleCard from './ArticleCard'
import { searchArticles, getRecommendations } from './api'
import './App.css'

export default function App() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [selected, setSelected] = useState(null)
  const [recommendations, setRecommendations] = useState([])
  const [recLoading, setRecLoading] = useState(false)
  const [error, setError] = useState(null)
  const debounceRef = useRef(null)

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!query.trim()) {
      setResults([])
      return
    }
    setSearching(true)
    debounceRef.current = setTimeout(() => {
      searchArticles(query)
        .then((data) => setResults(data.articles))
        .catch((err) => setError(err.message))
        .finally(() => setSearching(false))
    }, 300)
    return () => clearTimeout(debounceRef.current)
  }, [query])

  function handleSelect(article) {
    setSelected(article)
    setRecommendations([])
    setRecLoading(true)
    setError(null)
    getRecommendations(article.id)
      .then((data) => setRecommendations(data.recommendations))
      .catch((err) => setError(err.message))
      .finally(() => setRecLoading(false))
  }

  return (
    <div className="page">
      <header className="page__header">
        <h1>Cricket Article Recommender</h1>
        <p>Find a cricket article you like, get more like it.</p>
      </header>

      <div className="search">
        <input
          type="text"
          placeholder="Search articles by title or summary..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
      </div>

      {error && <p className="error">{error}</p>}

      <div className="layout">
        <section className="column">
          <h2>{query.trim() ? 'Results' : 'Search for an article to get started'}</h2>
          {searching && <p className="muted">Searching...</p>}
          <div className="card-list">
            {results.map((article) => (
              <ArticleCard
                key={article.id}
                article={article}
                onSelect={handleSelect}
                selected={selected?.id === article.id}
              />
            ))}
          </div>
        </section>

        {selected && (
          <section className="column">
            <h2>More like &ldquo;{selected.title}&rdquo;</h2>
            {recLoading && <p className="muted">Finding similar articles...</p>}
            <div className="card-list">
              {!recLoading && recommendations.length === 0 && (
                <p className="muted">No recommendations found.</p>
              )}
              {recommendations.map((article) => (
                <ArticleCard key={article.id} article={article} onSelect={handleSelect} />
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}
