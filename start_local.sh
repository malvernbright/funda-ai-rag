#!/bin/bash
echo "🚀 Starting Funda AI Environment..."

# 1. Backend Setup
echo "Checking backend environment..."
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment and installing backend dependencies with uv..."
    uv venv
    source .venv/bin/activate
    uv pip install fastapi uvicorn python-dotenv google-genai langchain-google-genai langchain-chroma langchain-community pypdf pydantic
else
    source .venv/bin/activate
fi

# Start Backend in the background
echo "Starting FastAPI backend..."
cd backend || exit  # <-- THE FIX: Move into the first backend folder
python -m uvicorn backend.main:app --reload --port 8000 &
BACKEND_PID=$!
echo $BACKEND_PID > ../backend.pid
cd ..

# 2. Frontend Setup
echo "Checking frontend environment..."
cd frontend || exit
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies with npm..."
    npm install
fi

# Start Frontend in the background
echo "Starting React frontend..."
npm run dev &
FRONTEND_PID=$!
echo $FRONTEND_PID > ../frontend.pid
cd ..

echo "✅ Funda AI is running!"
echo "Backend: http://127.0.0.1:8000/docs"
echo "Frontend: http://localhost:5173"