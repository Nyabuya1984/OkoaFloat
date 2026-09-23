import requests

url_login = "http://127.0.0.1:5000/api/user/login"
payload = {
    "phone_number": "0799999999",
    "password": "Password123!"
}
res = requests.post(url_login, json=payload)
print("Login:", res.json())
otp = res.json()["data"]["otp"]

url_verify = "http://127.0.0.1:5000/api/user/verify-otp"
payload_verify = {
    "phone_number": "0799999999",
    "otp": otp
}
res_verify = requests.post(url_verify, json=payload_verify)
print("Verify:", res_verify.status_code, res_verify.text)
