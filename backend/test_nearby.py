import requests

url = "http://127.0.0.1:5000/api/user/0721143189/nearby"
try:
    response = requests.get(url)
    print(response.status_code)
    print(response.json())
except Exception as e:
    print("Error:", e)
