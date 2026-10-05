import argparse
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = PROJECT_ROOT / "artifacts"
MOVIES_PATH = (
    PROJECT_ROOT / "data" / "raw"
    / "ml-latest-small" / "movies.csv"
)


def recommend_group(members, balance=0.5, top_k=10):
    """
    members: {"Abhi": [2571, 260], "Friend": [1, 2]}
    balance: 0 = average preference; 1 = lowest member preference.
    """
    if len(members) < 2:
        raise ValueError("Add at least two members.")
    if not 0 <= balance <= 1:
        raise ValueError("Balance must be between 0 and 1.")
    if top_k < 1:
        raise ValueError("top_k must be positive.")

    with np.load(
        ARTIFACT_DIR / "collaborative_svd.npz",
        allow_pickle=False,
    ) as saved:
        movie_ids = saved["movie_ids"]
        factors = saved["movie_factors"]

    column_lookup = {
        int(movie_id): column
        for column, movie_id in enumerate(movie_ids)
    }

    usable = np.linalg.norm(factors, axis=1) > 1e-8
    excluded = set()
    member_vectors = []

    for name, selected in members.items():
        liked = sorted(set(int(value) for value in selected))

        if not liked:
            raise ValueError(f"{name} needs at least one favourite.")

        invalid = [
            movie_id
            for movie_id in liked
            if movie_id not in column_lookup
            or not usable[column_lookup[movie_id]]
        ]
        if invalid:
            raise ValueError(
                f"{name} selected movies without usable factors: {invalid}"
            )

        columns = [column_lookup[movie_id] for movie_id in liked]
        vector = factors[columns].sum(axis=0) / np.sqrt(len(columns))

        member_vectors.append(vector)
        excluded.update(liked)

    # Exclude favourites selected by anyone in the group.
    eligible = np.flatnonzero(
        usable & ~np.isin(movie_ids, list(excluded))
    )

    if len(eligible) < 2:
        raise ValueError("Not enough eligible movies remain.")

    raw_scores = np.stack(member_vectors) @ factors[eligible].T

    # Convert each person's scores to comparable relative ranks.
    # Tied scores receive the same average rank.
    ranks = pd.DataFrame(raw_scores).rank(
        axis=1, method="average"
    ).to_numpy()

    preferences = (ranks - 1) / (len(eligible) - 1)

    average = preferences.mean(axis=0)
    lowest = preferences.min(axis=0)

    group_scores = (
        (1 - balance) * average
        + balance * lowest
    )

    order = np.lexsort(
        (movie_ids[eligible], -group_scores)
    )[:top_k]

    result = pd.DataFrame({
        "movieId": movie_ids[eligible[order]],
        "group_score": group_scores[order],
        "average_rank": average[order],
        "lowest_rank": lowest[order],
    })

    for index, name in enumerate(members):
        result[f"rank: {name}"] = preferences[index, order]

    movies = pd.read_csv(MOVIES_PATH)

    return result.merge(
        movies,
        on="movieId",
        how="left",
        validate="one_to_one",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--member",
        action="append",
        required=True,
        help='Repeat for each person: --member "Name:1,2,6"',
    )
    parser.add_argument("--balance", type=float, default=0.5)
    args = parser.parse_args()

    members = {}

    try:
        for entry in args.member:
            name, separator, values = entry.partition(":")
            name = name.strip()

            if not separator or not name:
                raise ValueError('Use the format "Name:1,2,6".')
            if name in members:
                raise ValueError("Member names must be unique.")

            members[name] = [
                int(value.strip())
                for value in values.split(",")
                if value.strip()
            ]

        recommendations = recommend_group(
            members, balance=args.balance
        )
    except ValueError as error:
        parser.error(str(error))

    print("\nWATCHTOGETHER — GROUP PICKS")
    print("Members:", ", ".join(members))
    print(f"Balance: {args.balance}")
    print("Scores are relative ranking values, not probabilities.\n")

    for position, (_, movie) in enumerate(
        recommendations.iterrows(), start=1
    ):
        print(f"{position}. {movie['title']}")
        print(
            f"   Group score: {movie['group_score']:.3f}"
            f" | Lowest member rank: {movie['lowest_rank']:.3f}"
        )
        print(
            "   " + " | ".join(
                f"{name}: {movie[f'rank: {name}']:.3f}"
                for name in members
            )
        )


if __name__ == "__main__":
    main()