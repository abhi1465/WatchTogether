from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = PROJECT_ROOT / "artifacts" / "collaborative_svd.npz"
MOVIES_PATH = (
    PROJECT_ROOT / "data" / "raw" / "ml-latest-small" / "movies.csv"
)


def explain_recommendations(recommended_ids, members, top_n=3):
    """
    Explain each person's raw collaborative score.

    The existing model computes:
        user_vector = sum(favourite_vectors) / sqrt(number_of_favourites)
        score = candidate_vector @ user_vector

    Each favourite's contribution is therefore:
        candidate_vector @ favourite_vector / sqrt(number_of_favourites)

    These contributions explain individual raw scores, not the final
    group score, which also uses relative ranks and the balance setting.
    """
    recommended_ids = [int(value) for value in recommended_ids]

    if not recommended_ids:
        return []

    with np.load(MODEL_PATH, allow_pickle=False) as saved:
        movie_ids = saved["movie_ids"]
        factors = saved["movie_factors"]

    column_lookup = {
        int(movie_id): index
        for index, movie_id in enumerate(movie_ids)
    }

    movies = pd.read_csv(MOVIES_PATH)
    titles = movies.set_index("movieId")["title"].to_dict()

    candidate_columns = [
        column_lookup[movie_id]
        for movie_id in recommended_ids
    ]
    candidate_vectors = factors[candidate_columns]

    explanations = [[] for _ in recommended_ids]

    for name, selected in members.items():
        liked_ids = sorted(set(int(value) for value in selected))

        if not liked_ids:
            raise ValueError(
                f"{name} needs at least one favourite for an explanation."
            )

        columns = [column_lookup[movie_id] for movie_id in liked_ids]
        liked_vectors = factors[columns]

        contributions = (
            candidate_vectors @ liked_vectors.T
        ) / np.sqrt(len(liked_ids))

        for row_index, row in enumerate(contributions):
            order = np.lexsort(
                (np.asarray(liked_ids), -row)
            )

            positive_columns = [
                int(index)
                for index in order
                if row[index] > 0
            ][:top_n]

            supporters = [
                {
                    "movieId": liked_ids[index],
                    "title": titles.get(
                        liked_ids[index],
                        f"Movie {liked_ids[index]}",
                    ),
                    "contribution": float(row[index]),
                }
                for index in positive_columns
            ]

            explanations[row_index].append({
                "member": name,
                "raw_score": float(row.sum()),
                "top_supporters": supporters,
                "selected_count": len(liked_ids),
            })

    return explanations