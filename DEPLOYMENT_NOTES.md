# WatchTogether deployment preparation

Copy backend/main.py and frontend/src/api.js over the matching files in
E:\WatchTogether. Add requirements.txt at the project root.
Keep a backup of your current working files. No model or dataset is included.

## Configuration when hosting

- Frontend build environment: VITE_API_BASE_URL=https://YOUR-BACKEND-HOST
  (origin only; do not append /api). Rebuild after changing this variable.
- Backend environment: CORS_ORIGINS=https://YOUR-FRONTEND-HOST
  (comma-separated exact origins for multiple websites).
- Backend secret: TMDB_READ_ACCESS_TOKEN, using your existing token.
  Never put that token in a VITE_ variable or in Git.
- With no new environment variables, local development still uses ports 5173
  and 8000. CORS_ORIGINS is read from the process environment, not a .env file.

## Runtime files required on the backend

- artifacts/collaborative_svd.npz
- data/raw/ml-latest-small/movies.csv
- data/raw/ml-latest-small/links.csv

Keep these paths relative to the project root. Leave .gitignore unchanged
until model size and dataset packaging are checked. Training ratings, splits,
and evaluation outputs are not needed by the inspected inference code.

## Commands for the eventual host

Install from the repository root: python -m pip install -r requirements.txt
Start from the repository root (Linux host shell):
python -m uvicorn backend.main:app --host 0.0.0.0 --port "$PORT"
Frontend build from frontend/: npm ci followed by npm run build
Frontend output directory: frontend/dist

The health URL is /api/health. It checks the API is running, but does not check
that the model, CSVs, or TMDB credentials work. Also test movie search,
personal recommendations, group recommendations, and poster metadata.

## Validation status

Python syntax and JavaScript syntax were checked. API URL construction and
CORS environment parsing were checked. Full backend inference and frontend
build could not be run here: the model/data, installed backend dependencies,
and complete frontend project were not provided. Dependency ranges above
are provisional until installation and smoke testing in the target environment.

References:
https://vite.dev/guide/env-and-mode
https://fastapi.tiangolo.com/tutorial/cors/
