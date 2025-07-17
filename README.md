# Insurance LLM Document Processing System

## Requirements
- Python 3.11+
- Docker & Docker Compose (recommended)
- PostgreSQL 15+

## Installation (Docker Recommended)

1. **Clone the repo and setup environment**
    ```
    git clone <your-repo-url>
    cd insurance-llm-system
    cp .env.example .env
    # Fill in your actual API keys and DB info in `.env`
    ```

2. **Build and launch services**
    ```
    docker-compose -f docker/docker-compose.yml up --build
    ```

3. **Run database migrations (if using Alembic)**
    ```
    docker-compose exec app alembic upgrade head
    ```

4. **Access the API**
    - Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
    - Health endpoint: [http://localhost:8000/api/v1/health/](http://localhost:8000/api/v1/health/)

## Manual (Bare Metal) Setup

1. **Install dependencies**
    ```
    pip install -r requirements/base.txt
    python -m spacy download en_core_web_sm
    ```

2. **Set up PostgreSQL**
    - Create DB: `insurance_db`
    - Update `DATABASE_URL` in `.env`

3. **Run app**
    ```
    uvicorn src.main:app --reload
    ```

## Running Tests

