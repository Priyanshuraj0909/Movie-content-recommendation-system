# Architecture

```mermaid
flowchart LR
  subgraph Prepare[Offline preparation]
    ML[GroupLens MovieLens]
    DL[Download and checksum validation]
    SPLIT[Validated metadata and per-user chronological splits]
    TFIDF[Content TF-IDF model]
    MF[Bias baseline and matrix factorization]
    BLEND[Validation-tuned hybrid evaluation]
    ML --> DL --> SPLIT
    SPLIT --> TFIDF
    SPLIT --> MF
    TFIDF --> BLEND
    MF --> BLEND
  end
  subgraph Demo[Local demo runtime]
    UI[Streamlit CineMatch]
    API[FastAPI routes and schemas]
    RATINGS[(SQLite local ratings)]
    MODELS[(Local model artifacts)]
    MOVIES[(Processed movie metadata)]
    UI -->|HTTP| API
    API --> RATINGS
    API --> MODELS
    API --> MOVIES
  end
  SPLIT --> MOVIES
  TFIDF --> MODELS
  MF --> MODELS
  subgraph Hosted[Vercel Services deployment]
    WEB[Static CineMatch web UI]
    VAPI[FastAPI Python service]
    DB[(Neon PostgreSQL ratings)]
    WEB -->|/api requests| VAPI
    VAPI --> DB
    VAPI --> MODELS
    VAPI --> MOVIES
  end
```

## Request path

The local Streamlit UI calls the FastAPI service through `frontend/api_client.py`.
The hosted browser UI in `frontend/web/` uses the same `/api/*` routes on the
Vercel deployment. Local runs use SQLite; hosted runs use PostgreSQL through
`DATABASE_URL`.
FastAPI validates inputs and serializes responses with Pydantic schemas. Search
reads the processed movie metadata; similarity and personalized rankings use
the fitted artifacts. Locally submitted ratings live in SQLite and contribute
to the user's content profile. The API blends that profile with the trained
collaborative scores and excludes rated items.

The workflow deliberately separates training from serving. The evaluation
script tunes its blend with validation data and then evaluates the chosen
weight on the untouched test split. API recommendations do not read validation
or test files.
