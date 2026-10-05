from collections import Counter
from pathlib import Path
import sys

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Allow running this file directly from the scripts directory.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.recommend import recommend_from_likes


DATA_DIR = PROJECT_ROOT / "data" / "processed"
ARTIFACT_DIR = PROJECT_ROOT / "artifacts"
OUTPUT_DIR = ARTIFACT_DIR / "onboarding"

SEED_COUNT = 5
K = 10
POSITIVE_THRESHOLD = 4.0

METRICS = [
    "precision_at_10",
    "recall_at_10",
    "ndcg_at_10",
]


def calculate_metrics(picks, relevant):
    hits = np.asarray(
        [movie_id in relevant for movie_id in picks],
        dtype=float,
    )

    dcg = float(
        (
            hits
            / np.log2(np.arange(2, len(picks) + 2))
        ).sum()
    )

    ideal_length = min(K, len(relevant))
    ideal_dcg = float(
        (
            1 / np.log2(np.arange(2, ideal_length + 2))
        ).sum()
    )

    return {
        "precision_at_10": float(hits.sum() / K),
        "recall_at_10": float(hits.sum() / len(relevant)),
        "ndcg_at_10": dcg / ideal_dcg,
    }


def validate_picks(picks, seeds, catalogue):
    if len(picks) > K:
        raise ValueError("The recommender returned too many movies.")

    if len(set(picks)) != len(picks):
        raise ValueError("Duplicate recommendations were returned.")

    if set(picks) & set(seeds):
        raise ValueError("A selected favourite was recommended again.")

    if not set(picks).issubset(catalogue):
        raise ValueError("Recommendations contain unknown catalogue movies.")


def main():
    print("WATCHTOGETHER — NEW-USER ONBOARDING EVALUATION")
    print(f"Selected favourites per user: {SEED_COUNT}")
    print(f"Recommendations per model: {K}")
    print("Evaluation data: validation only")
    print("Test set and website model: unchanged\n")

    train = pd.read_csv(DATA_DIR / "train.csv")
    validation = pd.read_csv(DATA_DIR / "validation.csv")

    baseline = pd.read_csv(
        ARTIFACT_DIR / "baseline_movies.csv"
    ).sort_values(
        ["baseline_score", "rating_count", "movieId"],
        ascending=[False, False, True],
    )

    with np.load(
        ARTIFACT_DIR / "collaborative_svd.npz",
        allow_pickle=False,
    ) as model:
        movie_ids = model["movie_ids"]
        user_ids = model["user_ids"]
        factors = model["movie_factors"]

        if float(model["positive_threshold"]) != POSITIVE_THRESHOLD:
            raise ValueError("Model positive threshold does not match.")

    training_users = set(train["userId"].astype(int))
    catalogue = set(int(value) for value in movie_ids)

    usable_seed_movies = set(
        int(value)
        for value in movie_ids[
            np.linalg.norm(factors, axis=1) > 1e-8
        ]
    )

    baseline_ranking = [
        int(value) for value in baseline["movieId"]
    ]

    if set(int(value) for value in user_ids) != training_users:
        raise ValueError("Model user IDs do not match the training split.")

    if catalogue != set(train["movieId"].astype(int)):
        raise ValueError("Model catalogue does not match the training split.")

    if catalogue != set(baseline_ranking):
        raise ValueError("Baseline and collaborative catalogues differ.")

    new_user_ratings = validation.loc[
        ~validation["userId"].isin(training_users)
    ]

    new_user_count = new_user_ratings["userId"].nunique()
    skipped = Counter()

    metric_rows = []
    protocol_rows = []

    recommended_catalogue = {
        "baseline": set(),
        "onboarding_svd": set(),
    }

    reachable_positive_count = 0
    all_future_positive_count = 0

    for user_id, ratings in new_user_ratings.groupby("userId"):
        ratings = ratings.sort_values(
            ["timestamp", "movieId"],
            kind="mergesort",
        )

        # The website allows favourites only when learned factors exist.
        seed_candidates = ratings.loc[
            (ratings["rating"] >= POSITIVE_THRESHOLD)
            & ratings["movieId"].isin(usable_seed_movies)
        ].drop_duplicates("movieId")

        if len(seed_candidates) < SEED_COUNT:
            skipped["fewer_than_five_usable_likes"] += 1
            continue

        selected = seed_candidates.head(SEED_COUNT)
        seeds = selected["movieId"].astype(int).tolist()
        cutoff = int(selected["timestamp"].max())

        # Ratings at the cutoff timestamp are not future evidence.
        future = ratings.loc[ratings["timestamp"] > cutoff]

        future_positives = set(
            future.loc[
                future["rating"] >= POSITIVE_THRESHOLD,
                "movieId",
            ].astype(int)
        ) - set(seeds)

        if not future_positives:
            skipped["no_strictly_later_positive_ratings"] += 1
            continue

        reachable = future_positives & catalogue

        if not reachable:
            skipped["later_positives_outside_catalogue_only"] += 1
            continue

        # Match the website: exclude selected favourites only.
        baseline_picks = [
            movie_id
            for movie_id in baseline_ranking
            if movie_id not in seeds
        ][:K]

        recommendations = recommend_from_likes(
            seeds,
            top_k=K,
        )

        personalised_picks = (
            recommendations["movieId"].astype(int).tolist()
        )

        for model_name, picks in [
            ("baseline", baseline_picks),
            ("onboarding_svd", personalised_picks),
        ]:
            validate_picks(picks, seeds, catalogue)

            metrics = calculate_metrics(picks, reachable)
            recommended_catalogue[model_name].update(picks)

            metric_rows.append({
                "userId": int(user_id),
                "model": model_name,
                **metrics,
            })

        reachable_positive_count += len(reachable)
        all_future_positive_count += len(future_positives)

        protocol_rows.append({
            "userId": int(user_id),
            "seed_movie_ids": "|".join(map(str, seeds)),
            "cutoff_timestamp": cutoff,
            "future_positive_count": len(future_positives),
            "reachable_positive_count": len(reachable),
            "baseline_picks": "|".join(map(str, baseline_picks)),
            "personalised_picks": "|".join(map(str, personalised_picks)),
        })

    print(f"New validation users considered: {new_user_count}")
    print(f"Users evaluated: {len(protocol_rows)}")

    print("\nEXCLUSIONS")
    for reason in [
        "fewer_than_five_usable_likes",
        "no_strictly_later_positive_ratings",
        "later_positives_outside_catalogue_only",
    ]:
        print(f"{reason}: {skipped[reason]}")

    if not metric_rows:
        print(
            "\nNo users qualified under this protocol. "
            "Do not interpret this as a model score of zero."
        )
        print(
            "Share this output so we can review the available "
            "chronological histories."
        )
        return

    results = pd.DataFrame(metric_rows)
    protocol = pd.DataFrame(protocol_rows)

    summary_rows = []

    for model_name in ["baseline", "onboarding_svd"]:
        subset = results.loc[results["model"] == model_name]

        summary_rows.append({
            "model": model_name,
            "users": len(subset),
            **{
                metric: float(subset[metric].mean())
                for metric in METRICS
            },
            "recommended_movies": len(
                recommended_catalogue[model_name]
            ),
            "catalogue_coverage": (
                len(recommended_catalogue[model_name])
                / len(catalogue)
            ),
        })

    summary = pd.DataFrame(summary_rows)

    print("\nONBOARDING — BASELINE VS PERSONALISED")
    print(summary.round(4).to_string(index=False))

    print("\nPAIRED NDCG@10 COMPARISON")
    paired = results.pivot(
        index="userId",
        columns="model",
        values="ndcg_at_10",
    )

    differences = (
        paired["onboarding_svd"] - paired["baseline"]
    )

    print(f"Users improved: {int((differences > 1e-10).sum())}")
    print(f"Users tied: {int((differences.abs() <= 1e-10).sum())}")
    print(f"Users worsened: {int((differences < -1e-10).sum())}")
    print(f"Mean NDCG change: {differences.mean():+.4f}")

    print("\nTARGET COVERAGE — EVALUATED USERS")
    print(
        f"Reachable future positive user/movie pairs: "
        f"{reachable_positive_count}/{all_future_positive_count} "
        f"({reachable_positive_count / all_future_positive_count:.1%})"
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results.to_csv(
        OUTPUT_DIR / "validation_per_user.csv",
        index=False,
    )
    summary.to_csv(
        OUTPUT_DIR / "validation_summary.csv",
        index=False,
    )
    protocol.to_csv(
        OUTPUT_DIR / "validation_protocol.csv",
        index=False,
    )

    print(f"\nSaved results to: {OUTPUT_DIR}")
    print(
        "\nThis simulates onboarding from historical ratings. "
        "It is not a live-user experiment or a group evaluation."
    )


if __name__ == "__main__":
    main()