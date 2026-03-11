#!/bin/bash
kill $(lsof -t -i:5000) 2>/dev/null
python3 api_server.py > /dev/null 2>&1 &
API_PID=$!
sleep 1

# Start session
curl -s -X POST http://localhost:5000/api/session/start -H "Content-Type: application/json" -d '{"session_id": "dev"}' > /dev/null

# Submit 'Able to read with pinhole'
curl -s -X POST http://localhost:5000/api/session/dev/respond -H "Content-Type: application/json" -d '{"intent": "Able to read with pinhole"}' > /dev/null

# Get state before
echo "Before sync:"
curl -s http://localhost:5000/api/session/dev/status

# Sync power
curl -s -X POST http://localhost:5000/api/session/dev/sync-power -H "Content-Type: application/json" -d '{"right": {"sph": -1.25, "cyl": 0.0, "axis": 180}}'

# Get state after
echo -e "\nAfter sync:"
curl -s http://localhost:5000/api/session/dev/status

# Respond blurry
echo -e "\nBlurry response:"
curl -s -X POST http://localhost:5000/api/session/dev/respond -H "Content-Type: application/json" -d '{"intent": "Blurry"}'

kill $API_PID
