#!/bin/bash
echo "Starting FastAPI Backend..."
# The backend code is in ../backend, but requirements.txt is in the root of the repo
cd ../
pip install -r requirements.txt || true
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "Starting Next.js Frontend..."
cd ../towneye-ai
npm run dev -- -H 0.0.0.0 &
FRONTEND_PID=$!

echo "Both servers running! Press Ctrl+C to stop."
wait
