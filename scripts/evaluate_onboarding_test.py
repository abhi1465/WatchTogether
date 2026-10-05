import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_onboarding import (
    calculate_metrics,
    validate_picks,
)
from scripts.recommend import recommend_from_likes


DATA_DIR = PROJECT_ROOT / "data" / "processed"
ARTIFACT_DIR = PROJECT_ROOT / "artifacts"
OUTPUT_DIR = ARTIFACT_DIR / "final_test"

MODEL_PATH = ARTIFACT_DIR / "collaborative_svd.npz"
BASELINE_PATH = ARTIFACT_DIR / "baseline_movies.csv"

SEED_COUNT = 5
K = 10
POSITIVE_THRESHOLD = 4.0
EXPECTED_COMPONENTS = 32

METRICS = [
    "precision_at_10",
    "recall_at_10",
    "ndcg_at_10",
]


def fingerprint(path):
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def main():
    completion_path = OUTPUT_DIR / "completed.json"
    manifest_path = OUTPUT_DIR / "frozen_protocol.json"

    if completion_path.exists():
        print("The final test has already completed.")
        print(f"Read the saved results in: {OUTPUT_DIR}")
        print("No results were overwritten.")
        return

    train = pd.read_csv(DATA_DIR / "train.csv")

    baseline = pd.read_csv(BASELINE_PATH).sort_values(
        ["baseline_score", "rating_count", "movieId"],
        ascending=[False, False, True],
    )

    with np.load(MODEL_PATH, allow_pickle=False) as saved:
        movie_ids = saved["movie_ids"].copy()
        user_ids = saved["user_ids"].copy()
        factors = saved["movie_factors"].copy()

        if int(saved["n_components"]) != EXPECTED_COMPONENTS:
            raise ValueError("Expected the frozen 32-component model.")

        if float(saved["positive_threshold"]) != POSITIVE_THRESHOLD:
            raise ValueError("Unexpected model positive threshold.")

    training_users = set(train["userId"].astype(int))
    catalogue = set(int(value) for value in movie_ids)

    usable_seed_movies = set(
        int(value)
        for value in movie_ids[
            np.linalg.norm(factors, axis=1) > 1e-8
        ]
    )

    baseline_ranking = baseline["movieId"].astype(int).tolist()

    if set(int(value) for value in user_ids) != training_users:
        raise ValueError("Model users do not match the training split.")

    if catalogue != set(train["movieId"].astype(int)):
        raise ValueError("Model catalogue does not match training.")

    if catalogue != set(baseline_ranking):
        raise ValueError("Baseline and collaborative catalogues differ.")

    # These helpers must retain the validation experiment's metric settings.
    from scripts import evaluate_onboarding as validation_evaluator

    if validation_evaluator.K != K:
        raise ValueError("Validation metric helper uses a different K.")

    frozen_protocol = {
        "evaluation": "held_out_onboarding",
        "components": EXPECTED_COMPONENTS,
        "seed_count": SEED_COUNT,
        "top_k": K,
        "positive_threshold": POSITIVE_THRESHOLD,
        "cohort": "test users absent from training",
        "seed_rule": "first five usable positive movies",
        "future_rule": "timestamp strictly greater than fifth seed timestamp",
        "exclusion_rule": "selected seed movies only",
        "target_rule": "future positives within training catalogue",
        "model_sha256": fingerprint(MODEL_PATH),
        "baseline_sha256": fingerprint(BASELINE_PATH),
        "train_sha256": fingerprint(DATA_DIR / "train.csv"),
        "recommender_sha256": fingerprint(
            PROJECT_ROOT / "scripts" / "recommend.py"
        ),
        "metric_helpers_sha256": fingerprint(
            PROJECT_ROOT / "scripts" / "evaluate_onboarding.py"
        ),
        "test_script_sha256": fingerprint(Path(__file__)),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Freeze before reading test ratings.
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))

        if previous["protocol"] != frozen_protocol:
            raise ValueError(
                "The frozen configuration has changed since an earlier attempt."
            )
    else:
        manifest_path.write_text(
            json.dumps(
                {
                    "created_utc": datetime.now(timezone.utc).isoformat(),
                    "protocol": frozen_protocol,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    test = pd.read_csv(DATA_DIR / "test.csv")

    # Membership only: used to disclose overlap between evaluation cohorts.
    validation_users = set(
        pd.read_csv(
            DATA_DIR / "validation.csv",
            usecols=["userId"],
        )["userId"].astype(int)
    )

    candidates = test.loc[
        ~test["userId"].isin(training_users)
    ]

    skipped = Counter()
    metric_rows = []
    protocol_rows = []

    recommended_movies = {
        "baseline": set(),
        "onboarding_svd": set(),
    }

    total_future_positives = 0
    total_reachable_positives = 0

    print("WATCHTOGETHER — FINAL ONBOARDING TEST")
    print("Frozen model: 32 components")
    print("Selected favourites: 5")
    print("Recommendations: 10")
    print("Model fitting: none\n")

    for user_id, ratings in candidates.groupby("userId"):
        ratings = ratings.sort_values(
            ["timestamp", "movieId"],
            kind="mergesort",
        )

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

        baseline_picks = [
            movie_id
            for movie_id in baseline_ranking
            if movie_id not in seeds
        ][:K]

        personalised_picks = recommend_from_likes(
            seeds,
            top_k=K,
        )["movieId"].astype(int).tolist()

        appeared_in_validation = int(user_id) in validation_users

        for model_name, picks in [
            ("baseline", baseline_picks),
            ("onboarding_svd", personalised_picks),
        ]:
            validate_picks(picks, seeds, catalogue)

            metric_rows.append({
                "userId": int(user_id),
                "model": model_name,
                "appeared_in_validation": appeared_in_validation,
                **calculate_metrics(picks, reachable),
            })

            recommended_movies[model_name].update(picks)

        total_future_positives += len(future_positives)
        total_reachable_positives += len(reachable)

        protocol_rows.append({
            "userId": int(user_id),
            "appeared_in_validation": appeared_in_validation,
            "seed_movie_ids": "|".join(map(str, seeds)),
            "cutoff_timestamp": cutoff,
            "future_positive_count": len(future_positives),
            "reachable_positive_count": len(reachable),
            "baseline_picks": "|".join(map(str, baseline_picks)),
            "personalised_picks": "|".join(map(str, personalised_picks)),
        })

    candidate_count = int(candidates["userId"].nunique())

    print(f"Test users absent from training: {candidate_count}")
    print(f"Users evaluated: {len(protocol_rows)}")

    print("\nEXCLUSIONS")
    for reason in [
        "fewer_than_five_usable_likes",
        "no_strictly_later_positive_ratings",
        "later_positives_outside_catalogue_only",
    ]:
        print(f"{reason}: {skipped[reason]}")

    completion = {
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "test_sha256": fingerprint(DATA_DIR / "test.csv"),
        "candidate_users": candidate_count,
        "evaluated_users": len(protocol_rows),
        "exclusions": dict(skipped),
    }

    if not metric_rows:
        print("\nNo users qualified. No performance estimate is available.")
        completion_path.write_text(
            json.dumps(completion, indent=2),
            encoding="utf-8",
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
            "recommended_movies": len(recommended_movies[model_name]),
            "catalogue_coverage": (
                len(recommended_movies[model_name]) / len(catalogue)
            ),
        })

    summary = pd.DataFrame(summary_rows)

    print("\nHELD-OUT TEST RESULTS")
    print(summary.round(4).to_string(index=False))

    paired = results.pivot(
        index="userId",
        columns="model",
        values="ndcg_at_10",
    )

    differences = paired["onboarding_svd"] - paired["baseline"]

    print("\nPAIRED NDCG@10")
    print(f"Users improved: {int((differences > 1e-10).sum())}")
    print(f"Users tied: {int((differences.abs() <= 1e-10).sum())}")
    print(f"Users worsened: {int((differences < -1e-10).sum())}")
    print(f"Mean change: {differences.mean():+.4f}")

    print("\nTARGET COVERAGE — EVALUATED USERS")
    print(
        f"{total_reachable_positives}/{total_future_positives} "
        f"({total_reachable_positives / total_future_positives:.1%})"
    )

    overlap = int(protocol["appeared_in_validation"].sum())

    print(
        "\nEvaluated users also appearing in validation: "
        f"{overlap}/{len(protocol)}"
    )
    print(
        "This is a chronological holdout, not a guaranteed "
        "user-disjoint holdout."
    )

    results.to_csv(OUTPUT_DIR / "per_user.csv", index=False)
    summary.to_csv(OUTPUT_DIR / "summary.csv", index=False)
    protocol.to_csv(OUTPUT_DIR / "user_protocol.csv", index=False)

    completion.update({
        "validation_overlap_users": overlap,
        "reachable_positive_pairs": total_reachable_positives,
        "future_positive_pairs": total_future_positives,
    })

    # Written last so interrupted runs can resume with the same configuration.
    completion_path.write_text(
        json.dumps(completion, indent=2),
        encoding="utf-8",
    )

    print(f"\nSaved results to: {OUTPUT_DIR}")
    print("Website model: unchanged")
    print("Final test complete. Do not use these scores for further tuning.")


if __name__ == "__main__":
    main()