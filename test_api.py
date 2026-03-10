import requests
import time
import subprocess

# Start server
server = subprocess.Popen(["python3", "api_server.py"])
time.sleep(2)

base = "http://localhost:5000/api/session"
sid = "test4"

try:
    print("start:", requests.post(f"{base}/start", json={"session_id": sid}).json()['power']['right']['sph'])
    print("respond (pinhole):", requests.post(f"{base}/{sid}/respond", json={"intent": "Able to read with pinhole"}).json()['power']['right']['sph'])
    
    print("before sync:", requests.get(f"{base}/{sid}/status").json()['current_power']['right']['sph'])
    
    res = requests.post(f"{base}/{sid}/sync-power", json={"right": {"sph": -1.25, "cyl": 0.0, "axis": 180}})
    print("sync-power:", res.json())
    
    print("after sync:", requests.get(f"{base}/{sid}/status").json()['current_power']['right']['sph'])
    
    res = requests.post(f"{base}/{sid}/respond", json={"intent": "Blurry"})
    print("respond (blurry):", res.json()['power']['right']['sph'])

finally:
    server.terminate()
