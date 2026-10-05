from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize
from threadpoolctl import threadpool_limits


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "processed"
ARTIFACT_DIR = PROJECT_ROOT / "artifacts"
OUTPUT_DIR = ARTIFACT_DIR / "tuning"

COMPONENT_OPTIONS = [8, 16, 32, 64]
POSITIVE_THRESHOLD = 4.0
RANDOM_STATE = 42
K = 10

METRICS = [
    "precision_at_10",
    "recall_at_10",
    "ndcg_at_10",
]


def load_model(path):
    with np.load(path, allow_pickle=False) as saved:
        return {key: saved[key].copy() for key in saved.files}


def build_interactions(train):
    user_ids = np.sort(train["userId"].unique())
    movie_ids = np.sort(train["movieId"].unique())

    user_lookup = {
        user_id: index
        for index, user_id in enumerate(user_ids)
    }
    movie_lookup = {
        movie_id: index
        for index, movie_id in enumerate(movie_ids)
    }

    positives = train.loc[
        train["rating"] >= POSITIVE_THRESHOLD
    ]

    interactions = csr_matrix(
        (
            np.ones(len(positives), dtype=np.float32),
            (
                positives["userId"].map(user_lookup).to_numpy(),
                positives["movieId"].map(movie_lookup).to_numpy(),
            ),
        ),
        shape=(len(user_ids), len(movie_ids)),
    )

    has_positive_history = (
        np.asarray(interactions.getnnz(axis=1)).ravel() > 0
    )

    normalised = normalize(interactions, norm="l2", axis=1)

    return (
        user_ids,
        movie_ids,
        normalised,
        has_positive_history,
    )


def build_cohort(train, validation, movie_ids, baseline_ranking):
    catalogue = set(movie_ids.tolist())

    histories = (
        train.groupby("userId")["movieId"]
        .apply(set)
        .to_dict()
    )

    cohort = []

    for user_id, ratings in validation.groupby("userId"):
        seen = histories.get(user_id, set())

        relevant = set(
            ratings.loc[
                ratings["rating"] >= POSITIVE_THRESHOLD,
                "movieId",
            ]
        ) - seen

        reachable = relevant & catalogue

        if not reachable:
            continue

        eligible = np.flatnonzero(
            ~np.isin(movie_ids, list(seen))
        )

        baseline_picks = [
            movie_id
            for movie_id in baseline_ranking
            if movie_id not in seen
        ][:K]

        cohort.append({
            "userId": int(user_id),
            "group": "existing" if user_id in histories else "new",
            "reachable": reachable,
            "eligible": eligible,
            "baseline_picks": baseline_picks,
        })

    if not cohort:
        raise ValueError("No eligible validation users were found.")

    if not any(item["group"] == "existing" for item in cohort):
        raise ValueError(
            "No existing users are available for model selection."
        )

    return cohort


def evaluate(cohort, movie_ids, model=None):
    rows = []
    recommended_movies = set()

    user_lookup = (
        {
            int(user_id): index
            for index, user_id in enumerate(model["user_ids"])
        }
        if model is not None
        else {}
    )

    for item in cohort:
        user_row = user_lookup.get(item["userId"])

        use_baseline = (
            model is None
            or user_row is None
            or not bool(model["has_positive_history"][user_row])
        )

        if use_baseline:
            picks = item["baseline_picks"]
        else:
            scores = (
                model["movie_factors"]
                @ model["user_factors"][user_row]
            )

            eligible = item["eligible"]

            order = np.lexsort(
                (movie_ids[eligible], -scores[eligible])
            )

            picks = movie_ids[
                eligible[order[:K]]
            ].tolist()

        recommended_movies.update(picks)

        hits = np.asarray(
            [movie_id in item["reachable"] for movie_id in picks],
            dtype=float,
        )

        dcg = float(
            (
                hits
                / np.log2(np.arange(2, len(picks) + 2))
            ).sum()
        )

        ideal_length = min(K, len(item["reachable"]))
        ideal_dcg = float(
            (
                1 / np.log2(np.arange(2, ideal_length + 2))
            ).sum()
        )

        rows.append({
            "userId": item["userId"],
            "group": item["group"],
            "used_baseline": use_baseline,
            "precision_at_10": float(hits.sum() / K),
            "recall_at_10": float(
                hits.sum() / len(item["reachable"])
            ),
            "ndcg_at_10": dcg / ideal_dcg,
        })

    return pd.DataFrame(rows), len(recommended_movies)


def summarise(label, components, results, coverage, catalogue_size):
    summary = {
        "model": label,
        "components": components,
        "evaluated_users": len(results),
        "baseline_users": int(results["used_baseline"].sum()),
        "recommended_movies": coverage,
        "catalogue_coverage": coverage / catalogue_size,
    }

    for group in ["all", "existing", "new"]:
        subset = (
            results
            if group == "all"
            else results.loc[results["group"] == group]
        )

        summary[f"{group}_users"] = len(subset)

        for metric in METRICS:
            summary[f"{group}_{metric}"] = (
                float(subset[metric].mean())
                if not subset.empty
                else np.nan
            )

    return summary


def selection_key(summary):
    # Primary: existing-user NDCG.
    # Ties: precision, recall, then fewer components.
    return (
        summary["existing_ndcg_at_10"],
        summary["existing_precision_at_10"],
        summary["existing_recall_at_10"],
        -summary["components"],
    )


def main():
    print("WATCHTOGETHER — VALIDATION-ONLY SVD TUNING", flush=True)
    print("The test set will not be read.")
    print("The website model will not be overwritten.\n")

    train = pd.read_csv(DATA_DIR / "train.csv")
    validation = pd.read_csv(DATA_DIR / "validation.csv")

    baseline = pd.read_csv(
        ARTIFACT_DIR / "baseline_movies.csv"
    ).sort_values(
        ["baseline_score", "rating_count", "movieId"],
        ascending=[False, False, True],
    )

    baseline_ranking = baseline["movieId"].tolist()

    (
        user_ids,
        movie_ids,
        normalised,
        has_positive_history,
    ) = build_interactions(train)

    if set(movie_ids.tolist()) != set(baseline_ranking):
        raise ValueError(
            "Baseline and training catalogues differ. "
            "Check that the artifacts use the same training split."
        )

    current_model = load_model(
        ARTIFACT_DIR / "collaborative_svd.npz"
    )

    if not np.array_equal(current_model["movie_ids"], movie_ids):
        raise ValueError("Current model movie IDs do not match training.")

    if not np.array_equal(current_model["user_ids"], user_ids):
        raise ValueError("Current model user IDs do not match training.")

    if float(current_model["positive_threshold"]) != POSITIVE_THRESHOLD:
        raise ValueError("Current model uses a different positive threshold.")

    cohort = build_cohort(
        train,
        validation,
        movie_ids,
        baseline_ranking,
    )

    existing_count = sum(
        item["group"] == "existing" for item in cohort
    )

    print(f"Interaction matrix: {normalised.shape}")
    print(f"Evaluated users: {len(cohort)}")
    print(f"Existing users: {existing_count}")
    print(f"New users: {len(cohort) - existing_count}\n")

    summaries = []
    per_user_tables = []

    def record(label, components, model):
        results, coverage = evaluate(cohort, movie_ids, model)

        summary = summarise(
            label,
            components,
            results,
            coverage,
            len(movie_ids),
        )

        summaries.append(summary)
        per_user_tables.append(results.assign(model=label))

        print(
            f"{label}: "
            f"existing NDCG@10={summary['existing_ndcg_at_10']:.4f} | "
            f"precision@10={summary['existing_precision_at_10']:.4f} | "
            f"recall@10={summary['existing_recall_at_10']:.4f}",
            flush=True,
        )

        return summary

    record("baseline", 0, None)

    current_summary = record(
        "current_saved",
        int(current_model["n_components"]),
        current_model,
    )

    best_candidate = None
    best_summary = None

    for components in COMPONENT_OPTIONS:
        if components >= min(normalised.shape):
            print(f"Skipping {components}: too large for this matrix.")
            continue

        print(
            f"\nTraining {components} components...",
            flush=True,
        )

        estimator = TruncatedSVD(
            n_components=components,
            n_iter=10,
            random_state=RANDOM_STATE,
        )

        user_factors = estimator.fit_transform(normalised)

        candidate = {
            "user_ids": user_ids,
            "movie_ids": movie_ids,
            "user_factors": user_factors,
            "movie_factors": estimator.components_.T,
            "has_positive_history": has_positive_history,
            "positive_threshold": POSITIVE_THRESHOLD,
            "n_components": components,
            "random_state": RANDOM_STATE,
        }

        summary = record(
            f"svd_{components}",
            components,
            candidate,
        )

        if (
            best_summary is None
            or selection_key(summary) > selection_key(best_summary)
        ):
            best_summary = summary
            best_candidate = candidate

    if best_candidate is None:
        raise ValueError("No valid candidate configurations were trained.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    summary_table = pd.DataFrame(summaries)
    summary_table.to_csv(
        OUTPUT_DIR / "validation_summary.csv",
        index=False,
    )

    pd.concat(per_user_tables, ignore_index=True).to_csv(
        OUTPUT_DIR / "validation_per_user.csv",
        index=False,
    )

    # Save only to the experiment directory.
    np.savez_compressed(
        OUTPUT_DIR / "best_candidate.npz",
        **best_candidate,
    )

    print("\nVALIDATION COMPARISON")

    display_columns = [
        "model",
        "existing_ndcg_at_10",
        "existing_precision_at_10",
        "existing_recall_at_10",
        "all_ndcg_at_10",
        "catalogue_coverage",
    ]

    print(
        summary_table[display_columns]
        .round(4)
        .to_string(index=False)
    )

    difference = (
        best_summary["existing_ndcg_at_10"]
        - current_summary["existing_ndcg_at_10"]
    )

    print(f"\nBest experimental candidate: {best_summary['model']}")
    print(
        "Existing-user NDCG change versus current model: "
        f"{difference:+.4f}"
    )

    if difference > 1e-8:
        print("This candidate improved the selected validation metric.")
    elif difference < -1e-8:
        print("The current model scored better on the primary metric.")
    else:
        print("There is no meaningful primary-metric improvement.")

    print(f"\nResults saved to: {OUTPUT_DIR}")
    print("Current website model: unchanged")
    print("Test set: untouched")
    print(
        "\nThese are tuning results from a small validation cohort, "
        "not final test performance."
    )


if __name__ == "__main__":
    # Keep CPU thread use modest on the laptop.
    with threadpool_limits(limits=1):
        main()