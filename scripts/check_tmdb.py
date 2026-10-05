from pathlib import Path

import httpx
from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"


def main():
    if not ENV_PATH.is_file():
        print("ERROR: Cannot find E:\\WatchTogether\\.env")
        print("Check that the filename is .env, not .env.txt.")
        return 1

    config = dotenv_values(ENV_PATH, encoding="utf-8-sig")
    token = (config.get("TMDB_READ_ACCESS_TOKEN") or "").strip()

    if not token or token.startswith("PASTE_"):
        print("ERROR: TMDB_READ_ACCESS_TOKEN is missing or a placeholder.")
        print("Update .env with your read access token and save.")
        return 1

    # Use IPv4 for this client only. TLS verification stays enabled.
    transport = httpx.HTTPTransport(
        local_address="0.0.0.0",
        verify=True,
        retries=1,
    )

    try:
        with httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(15.0, connect=10.0),
            trust_env=False,
        ) as client:
            response = client.get(
                "https://api.themoviedb.org/3/movie/550",
                params={"language": "en-US"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
            )

            response.raise_for_status()
            movie = response.json()

    except httpx.HTTPStatusError as error:
        status = error.response.status_code

        messages = {
            401: "Authentication failed. Check your API Read Access Token.",
            403: "Access was refused.",
            404: "The requested movie endpoint was not found.",
            429: "Too many requests. Wait briefly and try again.",
        }

        print(f"ERROR: HTTP {status}")
        print(messages.get(status, "TMDB returned an unexpected HTTP status."))
        return 1

    except httpx.TimeoutException:
        print("ERROR: The IPv4 request timed out.")
        print("Try running this script once more.")
        return 1

    except httpx.RequestError as error:
        # Redact the token if it ever appears in an exception message.
        detail = str(error).replace(token, "[REDACTED]")
        print(f"ERROR: {type(error).__name__}")
        print(f"Details: {detail}")
        return 1

    except (ValueError, UnicodeError):
        print("ERROR: Invalid token formatting or an unreadable response.")
        print("Check that the token is copied as one complete line.")
        return 1

    if not isinstance(movie, dict) or not movie.get("title"):
        print("ERROR: TMDB returned an unexpected response.")
        return 1

    print("WATCHTOGETHER — TMDB CONNECTION")
    print("Connection: successful")
    print("Network: IPv4")
    print(f"Movie: {movie['title']}")
    print(f"Release date: {movie.get('release_date') or 'Unavailable'}")
    print(f"Poster available: {'Yes' if movie.get('poster_path') else 'No'}")
    print("Token: kept private")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())