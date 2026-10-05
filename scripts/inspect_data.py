from pathlib import Path

import pandas as pd

# Resolve paths relative to this file, rather than the terminal location.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "raw" / "ml-latest-small"


def main():
    movies = pd.read_csv(DATA_DIR / "movies.csv")
    ratings = pd.read_csv(DATA_DIR / "ratings.csv")

    print("WATCHTOGETHER — DATA OVERVIEW")
    print(f"Movies: {len(movies):,}")
    print(f"Ratings: {len(ratings):,}")
    print(f"Users: {ratings['userId'].nunique():,}")
    print(
        f"Rating range: "
        f"{ratings['rating'].min()}–{ratings['rating'].max()}"
    )

    print("\nFIRST FIVE MOVIES")
    print(movies.head().to_string(index=False))

    print("\nFIRST FIVE RATINGS")
    print(ratings.head().to_string(index=False))

    print("\nMISSING VALUES")
    print("Movies:", movies.isna().sum().to_dict())
    print("Ratings:", ratings.isna().sum().to_dict())

    duplicates = ratings.duplicated(subset=["userId", "movieId"]).sum()
    unknown_movies = (~ratings["movieId"].isin(movies["movieId"])).sum()

    print(f"\nDuplicate user/movie pairs: {duplicates}")
    print(f"Ratings referencing unknown movies: {unknown_movies}")


if __name__ == "__main__":
    main()