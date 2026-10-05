from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
ARTIFACT_DIR = PROJECT_ROOT / "artifacts"

N_COMPONENTS = 32
POSITIVE_THRESHOLD = 4.0
RANDOM_STATE = 42


def main():
    train = pd.read_csv(DATA_DIR / "processed" / "train.csv")
    movies = pd.read_csv(
        DATA_DIR / "raw" / "ml-latest-small" / "movies.csv"
    )

    user_ids = np.sort(train["userId"].unique())
    movie_ids = np.sort(train["movieId"].unique())

    user_to_row = {
        user_id: row for row, user_id in enumerate(user_ids)
    }
    movie_to_column = {
        movie_id: column for column, movie_id in enumerate(movie_ids)
    }

    positives = train.loc[
        train["rating"] >= POSITIVE_THRESHOLD
    ].copy()

    row_indices = positives["userId"].map(user_to_row).to_numpy()
    column_indices = (
        positives["movieId"].map(movie_to_column).to_numpy()
    )

    # A stored 1 means an observed positive interaction.
    interactions = csr_matrix(
        (
            np.ones(len(positives), dtype=np.float32),
            (row_indices, column_indices),
        ),
        shape=(len(user_ids), len(movie_ids)),
    )

    has_positive_history = (
        np.asarray(interactions.getnnz(axis=1)).ravel() > 0
    )

    # Reduce domination by users with very large rating histories.
    normalised = normalize(interactions, norm="l2", axis=1)

    model = TruncatedSVD(
        n_components=N_COMPONENTS,
        n_iter=10,
        random_state=RANDOM_STATE,
    )

    user_factors = model.fit_transform(normalised)
    movie_factors = model.components_.T

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    output_path = ARTIFACT_DIR / "collaborative_svd.npz"
    np.savez_compressed(
        output_path,
        user_ids=user_ids,
        movie_ids=movie_ids,
        user_factors=user_factors,
        movie_factors=movie_factors,
        has_positive_history=has_positive_history,
        positive_threshold=POSITIVE_THRESHOLD,
        n_components=N_COMPONENTS,
        random_state=RANDOM_STATE,
    )

    print("WATCHTOGETHER — COLLABORATIVE MODEL")
    print(f"Interaction matrix: {interactions.shape}")
    print(f"Positive interactions: {interactions.nnz:,}")
    print(f"User factors: {user_factors.shape}")
    print(f"Movie factors: {movie_factors.shape}")
    print(
        "Users requiring baseline fallback:",
        int((~has_positive_history).sum()),
    )
    print(f"Saved model: {output_path}")

    # Demonstrate recommendations for one training user.
    demo_row = int(np.flatnonzero(has_positive_history)[0])
    demo_user = int(user_ids[demo_row])

    scores = movie_factors @ user_factors[demo_row]

    seen = train.loc[
        train["userId"] == demo_user, "movieId"
    ].to_numpy()
    eligible_columns = np.flatnonzero(~np.isin(movie_ids, seen))

    # Sort by score, then movie ID for deterministic tie-breaking.
    order = np.lexsort(
        (
            movie_ids[eligible_columns],
            -scores[eligible_columns],
        )
    )
    top_columns = eligible_columns[order[:10]]

    recommendations = pd.DataFrame({
        "movieId": movie_ids[top_columns],
        "model_score": scores[top_columns],
    }).merge(
        movies,
        on="movieId",
        how="left",
        validate="one_to_one",
    )

    print(f"\nDEMO RECOMMENDATIONS — USER {demo_user}")
    print(
        recommendations[["title", "model_score"]]
        .round(4)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
    