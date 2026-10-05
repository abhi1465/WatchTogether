import { useEffect, useState } from "react";
import { fetchMovieMetadata, getCachedMetadata } from "./movieMetadata";

// Decorative artwork, not recommendations or a reflection of the user's taste.
// MovieLens IDs resolve through the existing backend; no API token is exposed.
const FILMS = [
  { movieId: 2571, title: "The Matrix", tone: "#25483d" },
  { movieId: 1, title: "Toy Story", tone: "#425f84" },
  { movieId: 1196, title: "The Empire Strikes Back", tone: "#48536a" },
  { movieId: 318, title: "The Shawshank Redemption", tone: "#875c3c" },
  { movieId: 296, title: "Pulp Fiction", tone: "#8a413a" },
  { movieId: 79132, title: "Inception", tone: "#386273" },
  { movieId: 260, title: "Star Wars", tone: "#76634b" },
  { movieId: 858, title: "The Godfather", tone: "#55433b" },
  { movieId: 356, title: "Forrest Gump", tone: "#6d8791" },
  { movieId: 1214, title: "Alien", tone: "#324f44" },
  { movieId: 2959, title: "Fight Club", tone: "#89586c" },
  { movieId: 4993, title: "The Fellowship of the Ring", tone: "#7a6b3f" },
];

export default function PosterWall() {
  const [posters, setPosters] = useState(() =>
    Object.fromEntries(
      FILMS.map(({ movieId }) => [movieId, getCachedMetadata(movieId)?.poster_url || ""])
    )
  );
  const [failedImages, setFailedImages] = useState({});

  useEffect(() => {
    let cancelled = false;
    // Two workers keep decoration from filling the shared metadata queue.
    // StrictMode remounts share pending requests via movieMetadata.js.
    let nextIndex = 0;
    async function worker() {
      while (!cancelled && nextIndex < FILMS.length) {
        const { movieId } = FILMS[nextIndex++];
        try {
          const metadata = await fetchMovieMetadata(movieId);
          if (!cancelled && metadata?.poster_url) {
            setPosters((current) => ({ ...current, [movieId]: metadata.poster_url }));
          }
        } catch {
          // Leave the decorative title tile in place when TMDB is unreachable.
        }
      }
    }
    void worker();
    void worker();
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="poster-wall" aria-hidden="true">
      <div className="poster-wall-grid">
        {[...FILMS, ...FILMS.slice(4), ...FILMS.slice(0, 4)].map((film, index) => (
          <div
            className="poster-wall-tile"
            key={`${film.movieId}-${index}`}
            style={{ "--tile-tone": film.tone }}
          >
            <span className="poster-wall-title">{film.title}</span>
            {posters[film.movieId] && !failedImages[film.movieId] && (
              <img
                src={posters[film.movieId]}
                alt=""
                decoding="async"
                loading="lazy"
                onError={() => setFailedImages((current) => ({ ...current, [film.movieId]: true }))}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
