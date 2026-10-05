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

    baseline = pd.read_csv(
        ARTIFACT_DIR / "baseline_movies.csv"
    ).sort_values(
        ["baseline_score", "rating_count", "movieId"],
        ascending=[False, False, True],
    )

    with np.load(
        ARTIFACT_DIR / "collaborative_svd.npz",
        allow_pickle=False,
    ) as saved:
        user_ids = saved["user_ids"]
        movie_ids = saved["movie_ids"]
        user_factors = saved["user_factors"]
        movie_factors = saved["movie_factors"]
        has_positive_history = saved["has_positive_history"]

    user_to_row = {
        int(user_id): row
        for row, user_id in enumerate(user_ids)
    }

    baseline_ranking = baseline["movieId"].tolist()
    catalogue = set(movie_ids.tolist())

    # Both models must recommend from the same catalogue.
    assert catalogue == set(baseline_ranking)

    histories = (
        train.groupby("userId")["movieId"]
        .apply(set)
        .to_dict()
    )

    rows = []
    recommended_movies = set()
    fallback_count = 0

    for user_id, user_ratings in validation.groupby("userId"):
        seen = histories.get(user_id, set())

        relevant = set(
            user_ratings.loc[
                user_ratings["rating"] >= POSITIVE_THRESHOLD,
                "movieId",
            ]
        ) - seen

        reachable = relevant & catalogue

        # Match the baseline evaluation's eligibility rules.
        if not reachable:
            continue

        row = user_to_row.get(int(user_id))
        use_fallback = (
            row is None or not bool(has_positive_history[row])
        )

        if use_fallback:
            fallback_count += 1
            picks = [
                movie_id
                for movie_id in baseline_ranking
                if movie_id not in seen
            ][:K]
        else:
            scores = movie_factors @ user_factors[row]

            eligible = np.flatnonzero(
                ~np.isin(movie_ids, list(seen))
            )

            order = np.lexsort(
                (movie_ids[eligible], -scores[eligible])
            )
            picks = movie_ids[eligible[order[:K]]].tolist()

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
            "used_fallback": use_fallback,
            "precision_at_10": float(hits.sum() / K),
            "recall_at_10": float(hits.sum() / len(reachable)),
            "ndcg_at_10": dcg / ideal_dcg,
        })

    results = pd.DataFrame(rows)
    previous = pd.read_csv(
        ARTIFACT_DIR / "baseline_validation.csv"
    )

    assert set(results["userId"]) == set(previous["userId"]), (
        "Evaluated users differ. Re-run the baseline evaluation."
    )

    metrics = ["precision_at_10", "recall_at_10", "ndcg_at_10"]

    print("VALIDATION — BASELINE VS COLLABORATIVE")
    print("Both use the same users and training catalogue.")

    for group in ["all", "existing", "new"]:
        current_group = (
            results if group == "all"
            else results[results["group"] == group]
        )
        baseline_group = (
            previous if group == "all"
            else previous[previous["group"] == group]
        )

        print(f"\n{group.upper()}: {len(current_group)} users")

        if current_group.empty:
            continue

        for metric in metrics:
            before = baseline_group[metric].mean()
            after = current_group[metric].mean()

            print(
                f"{metric}: "
                f"baseline={before:.4f} | "
                f"collaborative={after:.4f} | "
                f"change={after - before:+.4f}"
            )

    print(f"\nEvaluated users using fallback: {fallback_count}")
    print(
        "Catalogue coverage: "
        f"{len(recommended_movies):,}/{len(catalogue):,} "
        f"({len(recommended_movies) / len(catalogue):.2%})"
    )

    results.to_csv(
        ARTIFACT_DIR / "collaborative_validation.csv",
        index=False,
    )
    print("\nSaved: artifacts/collaborative_validation.csv")


if __name__ == "__main__":
    main()