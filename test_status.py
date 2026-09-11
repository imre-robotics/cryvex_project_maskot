import time
import requests
import json

def test_status():
    print("Testing /api/status...")
    while True:
        try:
            res = requests.get('http://127.0.0.1:8080/api/status')
            data = res.json()
            info = json.loads(data['status'])
            print(f"State: {info['state']}, Waypoint: {info['waypoint']}")
            if info['state'] == 'waiting_at_table':
                print("SUCCESS: State became waiting_at_table!")
                break
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(1)

if __name__ == '__main__':
    test_status()
