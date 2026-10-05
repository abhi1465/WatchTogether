import { useEffect, useState } from "react";
import { apiRequest } from "./api";
import { useSavedMembers } from "./useSavedMembers";
import MovieCard from "./MovieCard";
import GenreSelect from "./GenreSelect";
import PosterWall from "./PosterWall";
import "./posters.css";
import "./filters.css";

function cleanTitle(title) {
  return title.replace(/\s*\(\d{4}\)\s*$/, "");
}

function releaseYear(title) {
  return title.match(/\((\d{4})\)\s*$/)?.[1] || "Year unknown";
}

export default function App() {
  const [members, setMembers, saveError] = useSavedMembers();
  const [mode, setMode] = useState("personal");
  const [activeId, setActiveId] = useState("you");
  const [balance, setBalance] = useState(0.5);

  const [genre, setGenre] = useState("");
  const [genres, setGenres] = useState([]);
  const [genresLoading, setGenresLoading] = useState(true);
  const [genreError, setGenreError] = useState("");
  const [genreAttempt, setGenreAttempt] = useState(0);

  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState([]);
  const [searched, setSearched] = useState(false);
  const [recommendations, setRecommendations] = useState([]);
  const [searching, setSearching] = useState(false);
  const [recommending, setRecommending] = useState(false);
  const [error, setError] = useState("");

  const isGroup = mode === "group";
  const busy = searching || recommending;

  const activeMember = isGroup
    ? members.find((member) => member.id === activeId) ?? members[0]
    : members[0];

  const favourites = activeMember.favourites;
  const participants = isGroup ? members : [members[0]];
  const ready = participants.every(
    (member) => member.favourites.length > 0
  );

  useEffect(() => {
    let cancelled = false;

    async function loadGenres() {
      setGenresLoading(true);
      setGenreError("");

      try {
        const data = await apiRequest("/api/genres");

        if (
          !Array.isArray(data.genres) ||
          !data.genres.every((item) => typeof item === "string")
        ) {
          throw new Error("Unexpected genre response.");
        }

        if (!cancelled) setGenres(data.genres);
      } catch {
        if (!cancelled) {
          setGenreError(
            "Genre options could not be loaded. You can still get recommendations."
          );
        }
      } finally {
        if (!cancelled) setGenresLoading(false);
      }
    }

    loadGenres();

    return () => {
      cancelled = true;
    };
  }, [genreAttempt]);

  function clearResults() {
    setRecommendations([]);
    setError("");
  }

  function changeMode(nextMode) {
    if (busy) return;
    setMode(nextMode);
    clearResults();
  }

  function addMember() {
    if (busy || members.length >= 10) return;

    const existingNames = new Set(
      members.map((member) => member.name.trim().toLowerCase())
    );

    let number = 2;
    while (existingNames.has(`friend ${number}`)) number += 1;

    const member = {
      id: crypto.randomUUID(),
      name: `Friend ${number}`,
      favourites: [],
    };

    setMembers((current) => [...current, member]);
    setActiveId(member.id);
    clearResults();
  }

  function renameMember(name) {
    if (busy) return;

    setMembers((current) =>
      current.map((member) =>
        member.id === activeMember.id ? { ...member, name } : member
      )
    );

    clearResults();
  }

  function removeMember() {
    if (
      busy ||
      members.length <= 2 ||
      activeMember.id === members[0].id
    ) {
      return;
    }

    setMembers((current) =>
      current.filter((member) => member.id !== activeMember.id)
    );

    setActiveId(members[0].id);
    clearResults();
  }

  async function searchMovies(event) {
    event.preventDefault();
    const searchQuery = query.trim();
    if (busy || !searchQuery) return;

    setSearching(true);
    setSearched(false);
    setMatches([]);
    setError("");

    try {
      const data = await apiRequest(
        `/api/movies?q=${encodeURIComponent(searchQuery)}`
      );
      setMatches(data.results);
      setSearched(true);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSearching(false);
    }
  }

  function addFavourite(movie) {
    if (
      busy ||
      !movie.usable ||
      favourites.length >= 20 ||
      favourites.some((item) => item.movieId === movie.movieId)
    ) {
      return;
    }

    setMembers((current) =>
      current.map((member) =>
        member.id === activeMember.id
          ? { ...member, favourites: [...member.favourites, movie] }
          : member
      )
    );

    clearResults();
  }

  function removeFavourite(movieId) {
    if (busy) return;

    setMembers((current) =>
      current.map((member) =>
        member.id === activeMember.id
          ? {
              ...member,
              favourites: member.favourites.filter(
                (movie) => movie.movieId !== movieId
              ),
            }
          : member
      )
    );

    clearResults();
  }

  async function getRecommendations() {
    if (busy || !ready) return;

    const names = participants.map((member) => member.name.trim());

    if (names.some((name) => !name)) {
      setError("Please give every person a name.");
      return;
    }

    if (
      new Set(names.map((name) => name.toLowerCase())).size !== names.length
    ) {
      setError("Please use a different name for each person.");
      return;
    }

    clearResults();
    setRecommending(true);

    const sharedOptions = { top_k: 12, genre: genre || null };

    const requestBody = isGroup
      ? {
          ...sharedOptions,
          members: participants.map((member) => ({
            name: member.name.trim(),
            liked_ids: member.favourites.map((movie) => movie.movieId),
          })),
          balance,
        }
      : {
          ...sharedOptions,
          liked_ids: members[0].favourites.map((movie) => movie.movieId),
        };

    try {
      const data = await apiRequest(
        `/api/recommendations/${isGroup ? "group" : "personal"}`,
        { method: "POST", body: JSON.stringify(requestBody) }
      );

      setRecommendations(data.results);

      if (data.results.length === 0) {
        setError(
          genre
            ? `No eligible ${genre} movies remain. Try another genre or choose Any genre.`
            : "No recommendations were found. Try changing your favourites."
        );
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRecommending(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="/" aria-label="WatchTogether home">
          <span className="brand-mark" aria-hidden="true">W</span>
          <span>watchtogether</span>
        </a>
        <span className="header-note">THE MOVIE NIGHT PROJECT</span>
      </header>

      <main>
        <section className="intro cinematic-hero" aria-labelledby="hero-heading">
          <PosterWall />
          <div className="hero-content">
            <p className="eyebrow">GOOD FILMS. BETTER COMPANY.</p>
            <h1 id="hero-heading">Less scrolling.<br /><span>More cinema.</span></h1>
            <p className="intro-copy">
              Your next favourite, or a film for the whole sofa.
              Start with the movies you already love.
            </p>
  
            <div className="mode-switch" role="group" aria-label="Viewing mode">
              <button
                type="button"
                className={!isGroup ? "active" : ""}
                aria-pressed={!isGroup}
                disabled={busy}
                onClick={() => changeMode("personal")}
              >
                Just me
              </button>
              <button
                type="button"
                className={isGroup ? "active" : ""}
                aria-pressed={isGroup}
                disabled={busy}
                onClick={() => changeMode("group")}
              >
                With friends
              </button>
            </div>
            <p className="hero-caption">YOUR TASTE. YOUR PEOPLE. YOUR NEXT WATCH.</p>
          </div>
        </section>

        {isGroup && (
          <section className="group-bar" aria-label="Group members">
            <div className="group-bar-heading">
              <div>
                <p className="eyebrow">WHO&apos;S WATCHING?</p>
                <p className="muted">
                  Choose a person, then add their favourites below.
                </p>
              </div>
              <button
                type="button"
                className="secondary-button"
                onClick={addMember}
                disabled={busy || members.length >= 10}
              >
                Add person +
              </button>
            </div>

            <div className="member-list">
              {members.map((member) => {
                const selected = member.id === activeMember.id;
                return (
                  <button
                    key={member.id}
                    type="button"
                    className={`member-chip ${selected ? "active" : ""}`}
                    aria-pressed={selected}
                    disabled={busy}
                    onClick={() => setActiveId(member.id)}
                  >
                    <span className="member-avatar" aria-hidden="true">
                      {member.name.trim().charAt(0).toUpperCase() || "?"}
                    </span>
                    <span>
                      <strong>{member.name.trim() || "Unnamed"}</strong>
                      <small>
                        {member.favourites.length}{" "}
                        {member.favourites.length === 1 ? "favourite" : "favourites"}
                      </small>
                    </span>
                  </button>
                );
              })}
            </div>
          </section>
        )}

        <div className="workspace">
          <section className="panel search-panel" aria-labelledby="search-heading">
            <p className="eyebrow">01 / FIND YOUR FAVOURITES</p>
            <h2 id="search-heading">
              {isGroup
                ? `Picking for ${activeMember.name.trim() || "this person"}`
                : "What’s your kind of film?"}
            </h2>
            <p className="muted">
              Search by movie title and add films you enjoyed.
            </p>

            <form className="search-form" onSubmit={searchMovies}>
              <input
                type="search"
                aria-label="Search movies by title"
                placeholder="Try The Matrix, Toy Story, Alien..."
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                maxLength={100}
                disabled={busy}
              />
              <button type="submit" disabled={busy || !query.trim()}>
                {searching ? "Searching..." : "Search"}
              </button>
            </form>

            <div className="search-results" aria-live="polite" aria-busy={searching}>
              {!searched && !searching && (
                <div className="empty-state">
                  <p>Your next movie night starts here.</p>
                  <span>
                    Search for a favourite to begin building your taste profile.
                  </span>
                </div>
              )}

              {searching && <p className="muted">Looking for movies...</p>}

              {searched && matches.length === 0 && (
                <div className="empty-state">
                  <p>No movies found.</p>
                  <span>Try a shorter title or a different spelling.</span>
                </div>
              )}

              {matches.map((movie) => {
                const added = favourites.some(
                  (item) => item.movieId === movie.movieId
                );

                return (
                  <div className="search-result" key={movie.movieId}>
                    <div className="movie-info">
                      <h3>{cleanTitle(movie.title)}</h3>
                      <p>
                        {releaseYear(movie.title)}
                        {!movie.usable && " · Not available for this model"}
                      </p>
                    </div>
                    <button
                      type="button"
                      className="add-button"
                      disabled={
                        busy || added || !movie.usable || favourites.length >= 20
                      }
                      onClick={() => addFavourite(movie)}
                      aria-label={
                        added
                          ? `${movie.title} already added`
                          : `Add ${movie.title}`
                      }
                    >
                      {added ? "Added" : !movie.usable ? "Unavailable" : "+ Add"}
                    </button>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="panel taste-panel" aria-labelledby="taste-heading">
            <p className="eyebrow">02 / BUILD THE SHORTLIST</p>
            <div className="panel-heading">
              <h2 id="taste-heading">
                {isGroup ? "Their favourites" : "Your taste"}
              </h2>
              <span className="count-badge">{favourites.length}/20</span>
            </div>

            {isGroup && (
              <div className="member-editor">
                <label htmlFor="member-name">Name</label>
                <input
                  id="member-name"
                  type="text"
                  value={activeMember.name}
                  maxLength={40}
                  disabled={busy}
                  onChange={(event) => renameMember(event.target.value)}
                  placeholder="Enter a name"
                />
                {activeMember.id !== members[0].id && members.length > 2 && (
                  <button
                    type="button"
                    className="text-button"
                    disabled={busy}
                    onClick={removeMember}
                  >
                    Remove this person
                  </button>
                )}
              </div>
            )}

            <p className="muted">
              Pick 3–5 favourites to start. You can add up to 20.
            </p>

            <div className="favourites-list">
              {favourites.length === 0 ? (
                <div className="empty-state">
                  <p>No favourites yet.</p>
                  <span>Add movies from the search results.</span>
                </div>
              ) : (
                favourites.map((movie) => (
                  <div className="favourite-item" key={movie.movieId}>
                    <div>
                      <strong>{cleanTitle(movie.title)}</strong>
                      <small>{releaseYear(movie.title)}</small>
                    </div>
                    <button
                      type="button"
                      className="remove-button"
                      aria-label={`Remove ${movie.title}`}
                      disabled={busy}
                      onClick={() => removeFavourite(movie.movieId)}
                    >
                      ×
                    </button>
                  </div>
                ))
              )}
            </div>

            <div className="genre-control">
              <GenreSelect
                value={genre}
                genres={genres}
                loading={genresLoading}
                disabled={busy || genresLoading || genres.length === 0}
                onChange={(nextGenre) => {
                  setGenre(nextGenre);
                  clearResults();
                }}
              />

              <p className="privacy-note">
                Applies to recommendations. Your favourites can be from any genre.
              </p>

              {genreError && (
                <div className="genre-load-error" role="status">
                  {genreError}
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => setGenreAttempt((current) => current + 1)}
                  >
                    Retry
                  </button>
                </div>
              )}
            </div>

            {isGroup && (
              <div className="balance-control">
                <label htmlFor="group-balance">
                  How should we balance tastes?
                </label>
                <input
                  id="group-balance"
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={balance}
                  disabled={busy}
                  aria-valuetext={`${Math.round(
                    balance * 100
                  )}% weight on the lowest member rank`}
                  onChange={(event) => {
                    setBalance(Number(event.target.value));
                    clearResults();
                  }}
                />
                <div className="balance-labels">
                  <span>Average preference</span>
                  <span>Lowest member rank</span>
                </div>
                <p className="privacy-note">
                  Move right to give more weight to the person who ranks a
                  film lowest. This is an experimental group-ranking rule.
                </p>
              </div>
            )}

            <button
              type="button"
              className="primary-button"
              disabled={busy || !ready}
              onClick={getRecommendations}
            >
              {recommending
                ? "Finding your next watch..."
                : isGroup
                  ? "Find a film for everyone"
                  : "Find my next film"}
            </button>

            {isGroup && !ready && (
              <p className="privacy-note">
                Every person needs at least one favourite before we can
                recommend a film.
              </p>
            )}

            <p className="privacy-note">
              {isGroup
                ? "Everyone’s selected favourites are excluded from group recommendations."
                : "Your selected favourites are excluded from recommendations."}{" "}
              Names and favourites are saved in this browser on this device.
            </p>

            {saveError && (
              <p className="privacy-note" role="status">{saveError}</p>
            )}
          </section>
        </div>

        {error && (
          <div className="error-message" role="alert">{error}</div>
        )}

        <section
          className="recommendations-section"
          aria-live="polite"
          aria-busy={recommending}
        >
          {recommending && (
            <p className="muted">
              Building your shortlist from the movie catalogue...
            </p>
          )}

          {recommendations.length > 0 && (
            <>
              <div className="results-heading">
                <div>
                  <p className="eyebrow">THE NEXT WATCH</p>
                  <h2>
                    {isGroup
                      ? "Different tastes. One shortlist."
                      : "A new shortlist. Just for you."}
                  </h2>
                  {genre && (
                    <span className="results-filter-badge">{genre} picks</span>
                  )}
                </div>
                <span className="muted">
                  {recommendations.length} recommendations
                </span>
              </div>

              <div className="poster-grid">
                {recommendations.map((movie, index) => (
                  <MovieCard
                    key={movie.movieId}
                    movie={movie}
                    index={index}
                    members={participants}
                    isGroup={isGroup}
                  />
                ))}
              </div>

              <p className="results-note">
                {isGroup
                  ? "Member ranks are calculated across the full eligible catalogue before genre filtering. They are not probabilities or predicted star ratings."
                  : "Recommendations use collaborative patterns learned from MovieLens ratings. Model scores are ranking values, not probabilities or predicted star ratings."}
              </p>
            </>
          )}
        </section>

        <section className="tmdb-credits" aria-labelledby="credits-heading">
          <h2 id="credits-heading">Credits</h2>
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
            This product uses the TMDB API but is not endorsed or certified
            by TMDB.
          </p>
          <p>
            Movie posters and descriptions: TMDB. Recommendation training
            data: GroupLens MovieLens.
          </p>
        </section>
      </main>

      <footer className="site-footer">
        <span>watchtogether · The movie night project</span>
        <span>A personal machine learning portfolio project.</span>
      </footer>
    </div>
  );
}
