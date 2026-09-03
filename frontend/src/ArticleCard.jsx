function matchReasons(article) {
  const reasons = []
  if (article.matched_players?.length) reasons.push(...article.matched_players)
  if (article.matched_teams?.length) reasons.push(...article.matched_teams)
  if (article.same_series) reasons.push('Same tournament/series')
  return reasons
}

export default function ArticleCard({ article, onSelect, selected }) {
  const reasons = matchReasons(article)

  return (
    <div className={`card${selected ? ' card--selected' : ''}`}>
      <button className="card__title" onClick={() => onSelect(article)}>
        {article.title}
      </button>
      {article.summary && <p className="card__summary">{article.summary}</p>}
      {reasons.length > 0 && (
        <div className="card__reasons">
          {reasons.map((reason) => (
            <span key={reason} className="chip">
              {reason}
            </span>
          ))}
        </div>
      )}
      <div className="card__footer">
        <span className="card__date">{article.published_date}</span>
        <a className="card__link" href={article.url} target="_blank" rel="noreferrer">
          Read on ESPNcricinfo &rarr;
        </a>
      </div>
    </div>
  )
}
