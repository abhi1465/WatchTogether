import csv
import os
from functools import lru_cache
from pathlib import Path

import httpx
from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LINKS_PATH = (
    PROJECT_ROOT / "data" / "raw" / "ml-latest-small" / "links.csv"
)
ENV_PATH = PROJECT_ROOT / ".env"


class MetadataError(Exception):
    """An error that can safely be shown without exposing credentials."""

    def __init__(self, message, status_code=503):
        super().__init__(message)
        self.status_code = status_code


# Reuse HTTPS connections instead of creating a client for every movie.
# Use IPv4, which worked in the earlier connection checks.
# Retry connection errors/timeouts once; keep TLS verification enabled.
transport = httpx.HTTPTransport(
    local_address="0.0.0.0",
    verify=True,
    retries=1,
    limits=httpx.Limits(
        max_connections=6,
        max_keepalive_connections=3,
        keepalive_expiry=30.0,
    ),
)

client = httpx.Client(
    transport=transport,
    timeout=httpx.Timeout(
        connect=4.0,
        read=6.0,
        write=4.0,
        pool=4.0,
    ),
    trust_env=False,
)


@lru_cache(maxsize=1)
def movie_links():
    mapping = {}

    try:
        with LINKS_PATH.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)

            if not {"movieId", "tmdbId"}.issubset(
                reader.fieldnames or []
            ):
                raise MetadataError(
                    "links.csv is missing required columns."
                )

            for row in reader:
                movie_id = int(row["movieId"])
                tmdb_id = row["tmdbId"].strip()

                mapping[movie_id] = (
                    int(tmdb_id) if tmdb_id else None
                )

    except (OSError, ValueError, KeyError) as error:
        raise MetadataError(
            "Could not read the MovieLens links.csv file."
        ) from error

    return mapping


def read_token():
    config = dotenv_values(ENV_PATH, encoding="utf-8-sig")

    token = (
        os.environ.get("TMDB_READ_ACCESS_TOKEN")
        or config.get("TMDB_READ_ACCESS_TOKEN")
        or ""
    ).strip()

    if not token or token.startswith("PASTE_"):
        raise MetadataError("TMDB credentials are not configured.")

    return token


def request_tmdb(path):
    token = read_token()

    try:
        response = client.get(
            f"https://api.themoviedb.org/3/{path}",
            params={"language": "en-US"},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
        )

        response.raise_for_status()
        data = response.json()

    except httpx.HTTPStatusError as error:
        status = error.response.status_code

        if status == 404:
            raise MetadataError(
                "Movie details are unavailable on TMDB.", 404
            ) from error

        if status in {401, 403}:
            raise MetadataError(
                "TMDB authentication or access was refused."
            ) from error

        if status == 429:
            raise MetadataError(
                "TMDB is temporarily rate-limiting requests. Try again later."
            ) from error

        raise MetadataError(
            "TMDB is temporarily unavailable."
        ) from error

    except httpx.TimeoutException as error:
        raise MetadataError(
            "TMDB took too long to respond. Try again."
        ) from error

    except httpx.RequestError as error:
        raise MetadataError(
            "Could not connect to TMDB. Try again."
        ) from error

    except (ValueError, UnicodeError) as error:
        raise MetadataError(
            "Could not process the TMDB request or response."
        ) from error

    if not isinstance(data, dict):
        raise MetadataError("TMDB returned an unexpected response.")

    return data


@lru_cache(maxsize=2048)
def get_movie_metadata(movie_id):
    """Cache successful lookups until eviction or server restart."""
    links = movie_links()

    if movie_id not in links:
        raise MetadataError("Unknown MovieLens movie ID.", 404)

    tmdb_id = links[movie_id]

    if tmdb_id is None:
        raise MetadataError(
            "This movie has no TMDB ID in the dataset.", 404
        )

    movie = request_tmdb(f"movie/{tmdb_id}")

    if not movie.get("title"):
        raise MetadataError(
            "TMDB returned incomplete movie details."
        )

    poster_path = movie.get("poster_path")
    poster_url = None

    if isinstance(poster_path, str) and poster_path.startswith("/"):
        poster_url = (
            f"https://image.tmdb.org/t/p/w500{poster_path}"
        )

    return {
        "movieId": movie_id,
        "tmdb_id": tmdb_id,
        "title": movie["title"],
        "overview": movie.get("overview") or "",
        "release_date": movie.get("release_date") or None,
        "runtime": movie.get("runtime") or None,
        "poster_url": poster_url,
        "tmdb_url": f"https://www.themoviedb.org/movie/{tmdb_id}",
        "source": "TMDB",
    }