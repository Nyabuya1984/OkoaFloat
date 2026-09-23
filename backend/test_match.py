from app import create_app
import json

app = create_app()
client = app.test_client()

with app.app_context():
    response = client.post('/api/user/match', json={
        'phone': '0721143189',  # Wycliffe Okemwa (Male)
        'ageRange': '18-50',
        'town': '',
        'county': ''
    })
    print(response.get_data(as_text=True))
