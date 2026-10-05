from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "processed"
ARTIFACT_DIR = PROJECT_ROOT / "artifacts"

K = 10
POSITIVE_THRESHOLD = 4.0


def main():
    train = pd.read_csv(DATA_DIR / "train.csv")
    validation = pd.read_csv(DATA_DIR / "validation.csv")
    baseline = pd.read_csv(ARTIFACT_DIR / "baseline_movies.csv")

    # Explicit ordering makes results reproducible.
    baseline = baseline.sort_values(
        ["baseline_score", "rating_count", "movieId"],
        ascending=[False, False, True],
    )
    ranked_movies = baseline["movieId"].tolist()
    catalogue = set(ranked_movies)

    histories = (
        train.groupby("userId")["movieId"]
        .apply(set)
        .to_dict()
    )

    rows = []
    recommended_movies = set()
    positive_count = 0
    reachable_count = 0
    skipped_no_positives = 0
    skipped_unreachable = 0

    for user_id, user_ratings in validation.groupby("userId"):
        seen = histories.get(user_id, set())

        relevant = set(
            user_ratings.loc[
                user_ratings["rating"] >= POSITIVE_THRESHOLD,
                "movieId",
            ]
        ) - seen

        if not relevant:
            skipped_no_positives += 1
            continue

        # Our current model cannot recommend movies absent from training.
        reachable = relevant & catalogue
        positive_count += len(relevant)
        reachable_count += len(reachable)

        if not reachable:
            skipped_unreachable += 1
            continue

        picks = [
            movie_id
            for movie_id in ranked_movies
            if movie_id not in seen
        ][:K]

        recommended_movies.update(picks)

        hits = np.array(
            [movie_id in reachable for movie_id in picks],
            dtype=float,
        )

        discounts = np.log2(np.arange(2, len(picks) + 2))
        dcg = float((hits / discounts).sum())

        ideal_length = min(K, len(reachable))
        ideal_dcg = float(
            (1 / np.log2(np.arange(2, ideal_length + 2))).sum()
        )

        rows.append({
            "userId": user_id,
            "group": "existing" if user_id in histories else "new",
            "precision_at_10": float(hits.sum() / K),
            "recall_at_10": float(hits.sum() / len(reachable)),
            "ndcg_at_10": dcg / ideal_dcg,
        })

    if not rows:
        raise RuntimeError("No users have reachable validation positives.")

    results = pd.DataFrame(rows)
    metrics = ["precision_at_10", "recall_at_10", "ndcg_at_10"]

    print("BASELINE — VALIDATION RESULTS")
    print("Metrics below use positives available in the training catalogue.")

    for label, frame in [
        ("ALL", results),
        ("EXISTING USERS", results[results["group"] == "existing"]),
        ("NEW USERS", results[results["group"] == "new"]),
    ]:
        print(f"\n{label}: {len(frame)} evaluated users")

        if frame.empty:
            print("No eligible users.")
            continue

        for metric in metrics:
            print(f"{metric}: {frame[metric].mean():.4f}")

    print("\nEVALUATION COVERAGE")
    print(f"Users with no validation positives: {skipped_no_positives}")
    print(f"Users with only unavailable positives: {skipped_unreachable}")
    print(
        "Positive movies reachable by the model: "
        f"{reachable_count:,}/{positive_count:,} "
        f"({reachable_count / positive_count:.1%})"
    )
    print(
        "Catalogue recommended across evaluated users: "
        f"{len(recommended_movies):,}/{len(catalogue):,} "
        f"({len(recommended_movies) / len(catalogue):.2%})"
    )

    output_path = ARTIFACT_DIR / "baseline_validation.csv"
    results.to_csv(output_path, index=False)
    print(f"\nPer-user results saved to: {output_path}")


if __name__ == "__main__":
    main()