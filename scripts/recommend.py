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


def recommend_from_likes(liked_ids, top_k=10):
    """Recommend using positive movie selections from a new user."""
    if not liked_ids:
        raise ValueError("Choose at least one movie.")
    if top_k < 1:
        raise ValueError("top_k must be positive.")

    with np.load(
        ARTIFACT_DIR / "collaborative_svd.npz",
        allow_pickle=False,
    ) as saved:
        movie_ids = saved["movie_ids"]
        movie_factors = saved["movie_factors"]

    movie_to_column = {
        int(movie_id): column
        for column, movie_id in enumerate(movie_ids)
    }

    liked_ids = sorted(set(int(value) for value in liked_ids))

    unsupported = [
        movie_id
        for movie_id in liked_ids
        if movie_id not in movie_to_column
    ]
    if unsupported:
        raise ValueError(
            f"Movies absent from the training catalogue: {unsupported}. "
            "Choose movies marked usable in the search results."
        )

    columns = [movie_to_column[movie_id] for movie_id in liked_ids]

    # Some training movies had no positive interactions.
    supported_vectors = [
        movie_factors[column]
        for column in columns
        if np.linalg.norm(movie_factors[column]) > 1e-8
    ]

    if len(supported_vectors) != len(columns):
        raise ValueError(
            "A selected movie has no learned positive signal. "
            "Choose movies marked usable in the search results."
        )

    # Same L2 normalisation used for positive training histories.
    user_vector = (
        np.sum(supported_vectors, axis=0)
        / np.sqrt(len(columns))
    )

    scores = movie_factors @ user_vector

    # Do not recommend the favourites the user already selected.
    eligible = np.flatnonzero(~np.isin(movie_ids, liked_ids))

    order = np.lexsort(
        (movie_ids[eligible], -scores[eligible])
    )
    best = eligible[order[:top_k]]

    movies = pd.read_csv(MOVIES_PATH)

    return pd.DataFrame({
        "movieId": movie_ids[best],
        "model_score": scores[best],
    }).merge(
        movies,
        on="movieId",
        how="left",
        validate="one_to_one",
    )


def search_movies(query):
    movies = pd.read_csv(MOVIES_PATH)

    with np.load(
        ARTIFACT_DIR / "collaborative_svd.npz",
        allow_pickle=False,
    ) as saved:
        usable = set(
            saved["movie_ids"][
                np.linalg.norm(saved["movie_factors"], axis=1) > 1e-8
            ].tolist()
        )

    matches = movies.loc[
        movies["title"].str.contains(
            query, case=False, regex=False, na=False
        )
    ].copy()

    matches["usable"] = matches["movieId"].isin(usable)

    return matches[["movieId", "title", "usable"]].head(30)


def main():
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--search", type=str)
    action.add_argument("--likes", type=int, nargs="+")
    args = parser.parse_args()

    if args.search is not None:
        matches = search_movies(args.search)
        print(
            matches.to_string(index=False)
            if not matches.empty
            else "No matching titles. Try a shorter search."
        )
        return

    try:
        recommendations = recommend_from_likes(args.likes)
    except ValueError as error:
        parser.error(str(error))

    print("\nRECOMMENDATIONS FROM YOUR FAVOURITES")
    print(
        recommendations[
            ["movieId", "title", "genres", "model_score"]
        ].round(4).to_string(index=False)
    )


if __name__ == "__main__":
    main()