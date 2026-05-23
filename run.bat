@echo off
echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Starting API server...
echo Open http://localhost:5068 in your browser
echo Swagger docs at http://localhost:5068/docs
echo.
uvicorn main:app --host 0.0.0.0 --port 5068 --reload
