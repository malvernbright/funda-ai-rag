#!/bin/bash
echo "🛑 Stopping Funda AI Services..."

if [ -f "backend.pid" ]; then
    kill $(cat backend.pid)
    rm backend.pid
    echo "Backend stopped."
fi

if [ -f "frontend.pid" ]; then
    kill $(cat frontend.pid)
    rm frontend.pid
    echo "Frontend stopped."
fi

echo "✅ All local services shut down successfully."