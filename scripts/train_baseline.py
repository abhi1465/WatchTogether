from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "artifacts"

PRIOR_STRENGTH = 50


def main():
    # All recommendation scores use training ratings only.
    train = pd.read_csv(DATA_DIR / "processed" / "train.csv")
    movies = pd.read_csv(
        DATA_DIR / "raw" / "ml-latest-small" / "movies.csv"
    )

    global_mean = train["rating"].mean()

    scores = (
        train.groupby("movieId")["rating"]
        .agg(rating_count="size", mean_rating="mean")
        .reset_index()
    )

    scores["baseline_score"] = (
        scores["rating_count"] * scores["mean_rating"]
        + PRIOR_STRENGTH * global_mean
    ) / (scores["rating_count"] + PRIOR_STRENGTH)

    # Keep candidates limited to movies observed in training.
    recommendations = scores.merge(
        movies,
        on="movieId",
        how="left",
        validate="one_to_one",
    )

    recommendations = recommendations.sort_values(
        ["baseline_score", "rating_count", "movieId"],
        ascending=[False, False, True],
    ).reset_index(drop=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "baseline_movies.csv"
    recommendations.to_csv(output_path, index=False)

    print("WATCHTOGETHER — BASELINE RECOMMENDER")
    print(f"Training average: {global_mean:.3f}")
    print(f"Prior strength: {PRIOR_STRENGTH}")
    print(f"Candidate movies: {len(recommendations):,}")

    columns = [
        "title",
        "rating_count",
        "mean_rating",
        "baseline_score",
    ]

    print("\nTOP 15 RECOMMENDATIONS")
    print(
        recommendations[columns]
        .head(15)
        .round(3)
        .to_string(index=False)
    )

    print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    main()