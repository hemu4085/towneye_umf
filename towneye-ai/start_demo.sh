#!/bin/bash
echo "Starting FastAPI Backend..."
cd /workspace/backend
pip install -r requirements.txt || true
uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "Starting Next.js Frontend..."
cd /workspace/towneye-ai
npm run dev -- -H 0.0.0.0 &
FRONTEND_PID=$!

echo "Both servers running! Press Ctrl+C to stop."
wait
