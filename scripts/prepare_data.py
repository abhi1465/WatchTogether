from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "ml-latest-small"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"


def main():
    ratings = pd.read_csv(RAW_DIR / "ratings.csv")
    ratings = ratings.sort_values(
        ["timestamp", "userId", "movieId"]
    ).reset_index(drop=True)

    # Keep ratings with the same timestamp in the same split.
    train_cutoff = ratings.iloc[int(len(ratings) * 0.80) - 1]["timestamp"]
    validation_cutoff = ratings.iloc[int(len(ratings) * 0.90) - 1]["timestamp"]

    train = ratings.loc[ratings["timestamp"] <= train_cutoff].copy()

    validation = ratings.loc[
        (ratings["timestamp"] > train_cutoff)
        & (ratings["timestamp"] <= validation_cutoff)
    ].copy()

    test = ratings.loc[
        ratings["timestamp"] > validation_cutoff
    ].copy()

    # Verify that no rows were lost and time boundaries are respected.
    assert min(len(train), len(validation), len(test)) > 0
    assert len(train) + len(validation) + len(test) == len(ratings)
    assert train["timestamp"].max() < validation["timestamp"].min()
    assert validation["timestamp"].max() < test["timestamp"].min()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    splits = {
        "train": train,
        "validation": validation,
        "test": test,
    }

    print("CHRONOLOGICAL DATA SPLITS")

    for name, frame in splits.items():
        frame.to_csv(OUTPUT_DIR / f"{name}.csv", index=False)

        dates = pd.to_datetime(frame["timestamp"], unit="s", utc=True)

        print(f"\n{name.upper()}")
        print(f"Ratings: {len(frame):,} ({len(frame) / len(ratings):.1%})")
        print(f"Users: {frame['userId'].nunique():,}")
        print(f"Movies: {frame['movieId'].nunique():,}")
        print(f"Dates: {dates.min().date()} to {dates.max().date()}")

    # Diagnose cold-start cases without removing them.
    known_users = set(train["userId"])
    known_movies = set(train["movieId"])

    print("\nVALIDATION COLD-START CHECK")
    print(
        "Users absent from training:",
        validation.loc[
            ~validation["userId"].isin(known_users), "userId"
        ].nunique(),
    )
    print(
        "Movies absent from training:",
        validation.loc[
            ~validation["movieId"].isin(known_movies), "movieId"
        ].nunique(),
    )

    print("\nSaved splits to data/processed")


if __name__ == "__main__":
    main()