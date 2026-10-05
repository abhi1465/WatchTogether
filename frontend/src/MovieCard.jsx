import { useEffect, useState } from "react";
import { useWatchlist } from "./useWatchlist";
import {
  fetchMovieMetadata,
  getCachedMetadata,
} from "./movieMetadata";
import "./explanations.css";

function cleanTitle(title) {
  return title.replace(/\s*\(\d{4}\)\s*$/, "");
}

function releaseYear(title) {
  return title.match(/\((\d{4})\)\s*$/)?.[1] || "Year unknown";
}

export default function MovieCard({
  movie,
  index = 0,
  members = [],
  isGroup = false,
  showRanking = true,
}) {
  const { isSaved, toggleMovie } = useWatchlist();
  const saved = isSaved(movie.movieId);

  const [metadata, setMetadata] = useState(
    () => getCachedMetadata(movie.movieId)
  );

  const [loading, setLoading] = useState(
    () => !getCachedMetadata(movie.movieId)
  );

  const [error, setError] = useState("");
  const [imageFailed, setImageFailed] = useState(false);
  const [imageAttempt, setImageAttempt] = useState(0);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const cached = getCachedMetadata(movie.movieId);

    setError("");
    setImageFailed(false);
    setMetadata(cached);

    if (cached) {
      setLoading(false);
      return;
    }

    setLoading(true);

    async function loadMetadata() {
      try {
        const data = await fetchMovieMetadata(movie.movieId);

        if (!cancelled) {
          setMetadata(data);
        }
      } catch (requestError) {
        if (!cancelled) {
          setError(
            requestError.message || "Movie details could not be loaded."
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadMetadata();

    return () => {
      cancelled = true;
    };
  }, [movie.movieId, attempt]);

  const title = metadata?.title || cleanTitle(movie.title);

  const year =
    metadata?.release_date?.slice(0, 4) || releaseYear(movie.title);

  const genres =
    movie.genres && movie.genres !== "(no genres listed)"
      ? movie.genres.split("|")
      : [];

  const explanations = Array.isArray(movie.explanations)
    ? movie.explanations
    : [];

  const hasPoster = metadata?.poster_url && !imageFailed;

  function retryPoster() {
    setImageFailed(false);
    setImageAttempt((current) => current + 1);
  }

  return (
    <article className="poster-card">
      <div className="poster-card-art" aria-busy={loading}>
        {hasPoster ? (
          <img
            key={`${movie.movieId}-${imageAttempt}`}
            className="poster-image"
            src={metadata.poster_url}
            alt={`${title} poster`}
            loading="lazy"
            decoding="async"
            onError={() => setImageFailed(true)}
          />
        ) : (
          <div
            className={`poster-placeholder ${
              loading ? "poster-loading" : ""
            }`}
          >
            <span
              className="poster-placeholder-mark"
              aria-hidden="true"
            >
              W
            </span>

            <strong>{title}</strong>

            <span>
              {loading
                ? "Loading movie details…"
                : error || imageFailed
                  ? "Poster could not be loaded"
                  : "No poster available"}
            </span>
          </div>
        )}

        {showRanking && (
          <span
            className="poster-position"
            aria-label={`Recommendation ${index + 1}`}
          >
            {String(index + 1).padStart(2, "0")}
          </span>
        )}

        {saved && (
          <span className="watchlist-saved-badge">Saved</span>
        )}
      </div>

      <div className="poster-card-content">
        <div className="poster-meta">
          <span>{year}</span>
          {metadata?.runtime > 0 && (
            <span>{metadata.runtime} min</span>
          )}
        </div>

        <h3>{title}</h3>

        <div className="genre-list">
          {genres.map((genre) => (
            <span className="genre-tag" key={genre}>
              {genre}
            </span>
          ))}
        </div>

        <button
          type="button"
          className={`watchlist-save-button ${
            saved ? "is-saved" : ""
          }`}
          onClick={() => toggleMovie(movie)}
          aria-label={
            saved
              ? `Remove ${title} from watchlist`
              : `Add ${title} to watchlist`
          }
        >
          {saved ? "✓ Saved · Remove" : "+ Add to watchlist"}
        </button>

        {showRanking && explanations.length > 0 && (
          <details className="movie-explanation">
            <summary>Why this movie?</summary>

            <p className="explanation-intro">
              {isGroup
                ? "For each person, these selected favourites give the strongest positive contributions to this film’s individual model score."
                : "These selected favourites give the strongest positive contributions to this film’s model score."}
            </p>

            {explanations.map((explanation) => (
              <div
                className="explanation-member"
                key={explanation.member}
              >
                <h4>
                  {isGroup ? explanation.member : "Your favourites"}
                </h4>

                {explanation.top_supporters.length > 0 ? (
                  <ol>
                    {explanation.top_supporters.map((supporter) => (
                      <li key={supporter.movieId}>
                        {cleanTitle(supporter.title)}
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p>
                    None of these selected favourites contributes
                    positively to this film’s raw model score.
                  </p>
                )}
              </div>
            ))}

            <p className="explanation-note">
              Showing up to three positive contributors per person,
              strongest first. Other favourites also affect the score.
              These links come from learned rating patterns, not
              necessarily similar plots.
            </p>

            {isGroup && (
              <p className="explanation-note">
                The final group order also depends on everyone’s
                relative ranks and your balance setting.
              </p>
            )}
          </details>
        )}

        {metadata?.overview && (
          <details className="poster-synopsis">
            <summary>About this film</summary>
            <p>{metadata.overview}</p>
          </details>
        )}

        {error && (
          <div className="poster-error">
            <p>{error}</p>
            <button
              type="button"
              onClick={() => setAttempt((current) => current + 1)}
            >
              Retry details
            </button>
          </div>
        )}

        {imageFailed && metadata?.poster_url && (
          <div className="poster-error">
            <p>Movie details loaded, but the poster image failed.</p>
            <button type="button" onClick={retryPoster}>
              Retry poster
            </button>
          </div>
        )}

        {isGroup && (
          <details className="rank-details">
            <summary>Group breakdown</summary>
            <p>Relative ranks from 0 to 1:</p>

            {members.map((member) => {
              const rank = movie[`rank: ${member.name.trim()}`];

              return (
                <div className="rank-row" key={member.id}>
                  <span>{member.name.trim()}</span>
                  <strong>
                    {typeof rank === "number"
                      ? rank.toFixed(3)
                      : "—"}
                  </strong>
                </div>
              );
            })}
          </details>
        )}

        {metadata?.tmdb_url && (
          <a
            className="poster-source-link"
            href={metadata.tmdb_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            View on TMDB ↗
          </a>
        )}
      </div>
    </article>
  );
}