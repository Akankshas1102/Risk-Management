# Risk Assessment Dashboard

A site-incident risk-assessment dashboard with a FastAPI backend, ML models (scikit-learn, XGBoost, Prophet), PostgreSQL storage, and a React frontend (upcoming). The system ingests raw incident CSV data, trains predictive models, and exposes risk scores and trend forecasts through a REST API.

## Backend setup

```bash
cd backend
pip install -r requirements.txt
```

Copy the environment template and fill in your database credentials:

```bash
cp ../.env.example ../.env
```

Start the development server:

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`. Visit `http://localhost:8000/docs` for the auto-generated Swagger UI.

## Frontend

Frontend (React) is planned for a later phase. The `frontend/` directory is a placeholder.
