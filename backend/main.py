import json
import logging
from typing import Annotated, Literal, get_args

import numpy as np
from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, StringConstraints

from backend.explanations import explain_recommendations
from backend.tmdb import MetadataError, get_movie_metadata
from scripts.recommend import (
    ARTIFACT_DIR,
    recommend_from_likes,
    search_movies,
)
from scripts.recommend_group import recommend_group


logger = logging.getLogger(__name__)

app = FastAPI(
    title="WatchTogether API",
    description="Personal and group movie recommendations.",
    version="0.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


Genre = Literal[
    "Action",
    "Adventure",
    "Animation",
    "Children",
    "Comedy",
    "Crime",
    "Documentary",
    "Drama",
    "Fantasy",
    "Film-Noir",
    "Horror",
    "IMAX",
    "Musical",
    "Mystery",
    "Romance",
    "Sci-Fi",
    "Thriller",
    "War",
    "Western",
]

MovieId = Annotated[int, Field(strict=True, gt=0)]

MemberName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=40,
    ),
]


class PersonalRequest(BaseModel):
    liked_ids: list[MovieId] = Field(min_length=1, max_length=100)
    top_k: int = Field(default=10, ge=1, le=50)
    genre: Genre | None = None


class Member(BaseModel):
    name: MemberName
    liked_ids: list[MovieId] = Field(min_length=1, max_length=100)


class GroupRequest(BaseModel):
    members: list[Member] = Field(min_length=2, max_length=10)
    balance: float = Field(default=0.5, ge=0, le=1)
    top_k: int = Field(default=10, ge=1, le=50)
    genre: Genre | None = None


def run_recommender(function, *args, **kwargs):
    try:
        frame = function(*args, **kwargs)
        return json.loads(frame.to_json(orient="records"))

    except OSError as error:
        logger.exception("Could not read recommendation data.")
        raise HTTPException(
            status_code=503,
            detail="Required data or model files could not be read.",
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


def ranked_recommendations(
    function,
    *args,
    top_k,
    genre,
    explanation_members,
    **kwargs,
):
    candidate_limit = top_k

    if genre is not None:
        with np.load(
            ARTIFACT_DIR / "collaborative_svd.npz",
            allow_pickle=False,
        ) as saved:
            candidate_limit = len(saved["movie_ids"])

    frame = function(
        *args,
        top_k=candidate_limit,
        **kwargs,
    )

    if genre is not None:
        matches = frame["genres"].fillna("").map(
            lambda value: genre in value.split("|")
        )
        frame = frame.loc[matches]

    frame = frame.head(top_k).reset_index(drop=True).copy()

    # Explain only the final shortlist.
    # This does not change any recommendation scores or ordering.
    if not frame.empty:
        frame["explanations"] = explain_recommendations(
            frame["movieId"].tolist(),
            explanation_members,
        )

    return frame


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "WatchTogether API",
    }


@app.get("/api/genres")
def available_genres():
    return {"genres": list(get_args(Genre))}


@app.get("/api/movies")
def find_movies(
    q: Annotated[str, Query(min_length=1, max_length=100)],
):
    query = q.strip()

    if not query:
        raise HTTPException(
            status_code=400,
            detail="Enter a movie title to search.",
        )

    results = run_recommender(search_movies, query)

    return {
        "results": results,
        "count": len(results),
    }


@app.get("/api/movies/{movie_id}/metadata")
def movie_metadata(
    movie_id: Annotated[int, Path(gt=0)],
):
    try:
        return get_movie_metadata(movie_id)

    except MetadataError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail=str(error),
        ) from error


@app.post("/api/recommendations/personal")
def personal_recommendations(request: PersonalRequest):
    results = run_recommender(
        ranked_recommendations,
        recommend_from_likes,
        request.liked_ids,
        top_k=request.top_k,
        genre=request.genre,
        explanation_members={"You": request.liked_ids},
    )

    return {
        "results": results,
        "count": len(results),
        "genre": request.genre,
        "score_type": "ranking_score_not_probability",
    }


@app.post("/api/recommendations/group")
def group_recommendations(request: GroupRequest):
    names = [member.name.casefold() for member in request.members]

    if len(set(names)) != len(names):
        raise HTTPException(
            status_code=400,
            detail="Each group member must have a different name.",
        )

    members = {
        member.name: member.liked_ids
        for member in request.members
    }

    results = run_recommender(
        ranked_recommendations,
        recommend_group,
        members,
        balance=request.balance,
        top_k=request.top_k,
        genre=request.genre,
        explanation_members=members,
    )

    return {
        "results": results,
        "count": len(results),
        "balance": request.balance,
        "genre": request.genre,
        "score_type": "relative_rank_not_probability",
    }