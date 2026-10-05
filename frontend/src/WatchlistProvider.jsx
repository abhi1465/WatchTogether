import { useEffect, useState } from "react";
import { WatchlistContext } from "./useWatchlist";
import MovieCard from "./MovieCard";
import PosterWall from "./PosterWall";
import "./watchlist.css";

const STORAGE_KEY = "watchtogether.watchlist.v1";
const MAX_MOVIES = 100;

function loadWatchlist() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));

    if (!Array.isArray(saved)) return [];

    const uniqueMovies = new Map();

    for (const movie of saved) {
      if (
        movie &&
        Number.isInteger(movie.movieId) &&
        movie.movieId > 0 &&
        typeof movie.title === "string"
      ) {
        uniqueMovies.set(movie.movieId, {
          movieId: movie.movieId,
          title: movie.title,
          genres: typeof movie.genres === "string" ? movie.genres : "",
        });
      }
    }

    return [...uniqueMovies.values()].slice(0, MAX_MOVIES);
  } catch {
    return [];
  }
}

export default function WatchlistProvider({ children }) {
  const [watchlist, setWatchlist] = useState(loadWatchlist);
  const [view, setView] = useState("discover");
  const [message, setMessage] = useState("");
  const [saveError, setSaveError] = useState("");

  const showingWatchlist = view === "watchlist";

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(watchlist));
      setSaveError("");
    } catch {
      setSaveError(
        "Browser storage is unavailable. Watchlist changes may not survive a refresh."
      );
    }
  }, [watchlist]);

  useEffect(() => {
    if (!message) return;

    const timer = setTimeout(() => {
      setMessage("");
    }, 4000);

    return () => clearTimeout(timer);
  }, [message]);

  function isSaved(movieId) {
    return watchlist.some((movie) => movie.movieId === movieId);
  }

  function toggleMovie(movie) {
    if (isSaved(movie.movieId)) {
      setWatchlist((current) =>
        current.filter((item) => item.movieId !== movie.movieId)
      );
      setMessage(`Removed ${movie.title} from your watchlist.`);
      return;
    }

    if (watchlist.length >= MAX_MOVIES) {
      setMessage(
        "Your watchlist is full. Remove a film before adding another."
      );
      return;
    }

    const savedMovie = {
      movieId: movie.movieId,
      title: movie.title,
      genres: typeof movie.genres === "string" ? movie.genres : "",
    };

    setWatchlist((current) => {
      if (
        current.length >= MAX_MOVIES ||
        current.some((item) => item.movieId === movie.movieId)
      ) {
        return current;
      }

      return [savedMovie, ...current];
    });

    setMessage(`Saved ${movie.title} to your watchlist.`);
  }

  function changeView(nextView) {
    setView(nextView);
    setMessage("");
    window.scrollTo({ top: 0, behavior: "instant" });
  }

  return (
    <WatchlistContext.Provider value={{ isSaved, toggleMovie }}>
      <div className="watchlist-navigation-bar">
        <nav
          className="watchlist-navigation"
          aria-label="Main navigation"
        >
          <button
            type="button"
            className={`watchlist-nav-button ${
              !showingWatchlist ? "is-active" : ""
            }`}
            aria-current={!showingWatchlist ? "page" : undefined}
            onClick={() => changeView("discover")}
          >
            Discover
          </button>

          <button
            type="button"
            className={`watchlist-nav-button ${
              showingWatchlist ? "is-active" : ""
            }`}
            aria-current={showingWatchlist ? "page" : undefined}
            onClick={() => changeView("watchlist")}
          >
            Watchlist
            <span className="watchlist-nav-count">
              {watchlist.length}
            </span>
          </button>
        </nav>

        <span className="watchlist-navigation-note">
          YOUR NEXT MOVIE NIGHT
        </span>
      </div>

      {/* Keep Discover mounted so its selections and results stay intact. */}
      <div hidden={showingWatchlist}>
        {children}
      </div>

      {showingWatchlist && (
        <main className="watchlist-page">
          <header className="watchlist-page-header cinematic-hero">
            <PosterWall />
            <div className="hero-content">
              <p className="eyebrow">SAVED FOR ANOTHER NIGHT</p>
              <h1>Your watchlist.</h1>
              <p className="watchlist-page-description">
                The films that caught your eye, ready whenever you are.
              </p>
  
              <div className="watchlist-page-toolbar">
                <span className="watchlist-page-count">
                  {watchlist.length}{" "}
                  {watchlist.length === 1 ? "film" : "films"} saved
                  <span> · Maximum {MAX_MOVIES}</span>
                </span>
  
                <button
                  type="button"
                  className="watchlist-discover-button"
                  onClick={() => changeView("discover")}
                >
                  Discover more films ↗
                </button>
              </div>
            </div>
          </header>

          {watchlist.length === 0 ? (
            <section className="watchlist-empty">
              <span aria-hidden="true">W</span>
              <h2>A good film is worth saving.</h2>
              <p>
                Head to Discover, generate recommendations, and click
                “Add to watchlist” on a film you want to see.
              </p>
              <button
                type="button"
                onClick={() => changeView("discover")}
              >
                Find your next film
              </button>
            </section>
          ) : (
            <section aria-label="Saved films">
              <div className="poster-grid">
                {watchlist.map((movie) => (
                  <MovieCard
                    key={movie.movieId}
                    movie={movie}
                    isGroup={false}
                    members={[]}
                    showRanking={false}
                  />
                ))}
              </div>
            </section>
          )}

          <p className="watchlist-bottom-note">
            Saved in this browser on this device. Saving a film does
            not change your taste profile or mark it as watched.
          </p>

          <section
            className="tmdb-credits"
            aria-labelledby="watchlist-credits-heading"
          >
            <h2 id="watchlist-credits-heading">Credits</h2>
            <a
              href="https://www.themoviedb.org/"
              target="_blank"
              rel="noopener noreferrer"
            >
              <img
                className="tmdb-logo"
                src="/tmdb-logo.svg"
                alt="The Movie Database (TMDB)"
              />
            </a>
            <p>
              This product uses the TMDB API but is not endorsed or
              certified by TMDB.
            </p>
            <p>
              Movie posters and descriptions: TMDB. Recommendation
              training data: GroupLens MovieLens.
            </p>
          </section>
        </main>
      )}

      <div className="watchlist-notifications">
        {saveError && (
          <p className="watchlist-feedback is-error" role="status">
            {saveError}
          </p>
        )}

        {message && (
          <p className="watchlist-feedback" role="status">
            {message}
          </p>
        )}
      </div>
    </WatchlistContext.Provider>
  );
}
