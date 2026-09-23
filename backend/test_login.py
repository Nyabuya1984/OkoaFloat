import requests

url_reg = "http://127.0.0.1:5000/api/user/register"
payload_reg = {
    "phone_number": "0799999999",
    "password": "Password123!",
    "name": "Test User",
    "age": 25,
    "gender": "Male",
    "county": "Nairobi",
    "town": "Nairobi"
}
res = requests.post(url_reg, json=payload_reg)
print("Reg:", res.status_code, res.text)

url = "http://127.0.0.1:5000/api/user/login"
payload = {
    "phone_number": "0799999999",
    "password": "Password123!"
}
res = requests.post(url, json=payload)
print("Login:", res.status_code, res.text)
