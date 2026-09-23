import requests

url = "http://localhost:5000/api/user/login"
data = {
    "phone_number": "0721143189",
    "password": "Nyabuy@1984"
}
try:
    r = requests.post(url, json=data)
    print("Status Code:", r.status_code)
    print("Response:", r.json())
except Exception as e:
    print("Error:", e)
