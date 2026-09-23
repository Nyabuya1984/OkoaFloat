import pytest
from app import create_app
from app.extensions import db


@pytest.fixture
def client():
    app = create_app('testing')
    app.config['TESTING'] = True

    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def test_sms_registration_and_match_flow(client):
    # activation
    response = client.post('/api/user/sms', json={'phone_number': '0712345678', 'message': 'PENZI'})
    assert response.status_code == 200
    assert 'Welcome to our dating service' in response.get_json()['message']

    # registration
    response = client.post('/api/user/sms', json={'phone_number': '0712345678', 'message': 'start#Jamal Jalang\'o#29#Male#Mombasa#Bamburi'})
    assert response.status_code == 201
    assert 'profile has been created successfully' in response.get_json()['message']

    # details completion
    response = client.post('/api/user/sms', json={'phone_number': '0712345678', 'message': 'details#graduate#accountant#divorced#muslim#somali'})
    assert response.status_code == 200
    assert 'last stage of registration' in response.get_json()['message']

    # self description
    response = client.post('/api/user/sms', json={'phone_number': '0712345678', 'message': 'MYSELF tall, dark and handsome'})
    assert response.status_code == 200
    assert 'registered for dating' in response.get_json()['message']

    # matching request
    response = client.post('/api/user/sms', json={'phone_number': '0712345678', 'message': 'match#26-30#Nairobi'})
    assert response.status_code == 200
    assert 'We have' in response.get_json()['message']


def test_details_not_provides_endpoint_uses_initial_details_message(client):
    register_response = client.post('/api/user/register', json={
        'phone_number': '0712345678',
        'name': 'Jane Doe',
        'age': 25,
        'gender': 'female',
        'county': 'Nairobi',
        'town': 'Kibera'
    })
    assert register_response.status_code == 201

    response = client.post('/api/user/details_not_provides', json={
        'phone_number': '0712345678',
        'education_level': 'NULL',
        'profession': 'NULL',
        'marital_status': 'NULL',
        'religion': 'NULL',
        'ethnicity': 'NULL'
    })

    assert response.status_code == 200
    assert 'initial details' in response.get_json()['message']


def test_next_matches_endpoint_returns_follow_up_batch(client):
    client.post('/api/user/register', json={
        'phone_number': '0712345678',
        'name': 'Jane Doe',
        'age': 25,
        'gender': 'female',
        'county': 'Nairobi',
        'town': 'Kibera'
    })
    client.post('/api/user/0712345678/complete-profile', json={
        'education_level': 'graduate',
        'profession': 'teacher',
        'marital_status': 'single',
        'religion': 'christian',
        'ethnicity': 'kikuyu'
    })
    client.post('/api/user/0712345678/self-description', json={'description': 'friendly and kind'})

    client.post('/api/user/register', json={
        'phone_number': '0712345679',
        'name': 'John Maina',
        'age': 27,
        'gender': 'male',
        'county': 'Nairobi',
        'town': 'Kibera'
    })
    client.post('/api/user/0712345679/complete-profile', json={
        'education_level': 'graduate',
        'profession': 'engineer',
        'marital_status': 'single',
        'religion': 'christian',
        'ethnicity': 'kikuyu'
    })
    client.post('/api/user/0712345679/self-description', json={'description': 'easy going'})

    search_response = client.get('/api/user/0712345678/matches?age_range=26-30&town=Nairobi')
    assert search_response.status_code == 200

    next_response = client.get('/api/user/0712345678/matches/next')
    assert next_response.status_code == 200
    assert 'Send NEXT' in next_response.get_json()['message'] or 'aged' in next_response.get_json()['message']
