import sys
import os

# Add the backend directory to sys.path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from app import create_app
from app.extensions import db
from app.models.user import User
from werkzeug.security import generate_password_hash
from datetime import datetime

dummy_users = [
    {
        "phone_number": "0711223344",
        "full_name": "Kamau Njoroge",
        "gender": "Male",
        "age": 29,
        "county_name": "Kiambu",
        "town_name": "Kiambu",
        "ethnicity": "Kikuyu",
        "education_level": "Graduate",
        "profession": "Software Engineer",
        "marital_status": "Single",
        "religion": "Christian",
        "self_description": "I love coding, hiking, and exploring new coffee shops around Kiambu and Nairobi. Looking for someone driven and fun!",
        "latitude": -1.1714,
        "longitude": 36.8356
    },
    {
        "phone_number": "0722334455",
        "full_name": "Omondi Odhiambo",
        "gender": "Male",
        "age": 32,
        "county_name": "Kisumu",
        "town_name": "Kisumu",
        "ethnicity": "Luo",
        "education_level": "Masters",
        "profession": "High School Teacher",
        "marital_status": "Single",
        "religion": "Christian",
        "self_description": "Easy-going teacher from the lakeside. Enjoying ohangla music, reading, and watching football on weekends.",
        "latitude": -0.0917,
        "longitude": 34.7680
    },
    {
        "phone_number": "0733445566",
        "full_name": "Kiprono Bett",
        "gender": "Male",
        "age": 28,
        "county_name": "Uasin Gishu",
        "town_name": "Eldoret",
        "ethnicity": "Kalenjin",
        "education_level": "Diploma",
        "profession": "Agribusiness Entrepreneur",
        "marital_status": "Single",
        "religion": "Christian",
        "self_description": "Passionate about farming and athletics. I'm a hardworking guy looking for a partner to build a solid future with.",
        "latitude": 0.5143,
        "longitude": 35.2698
    },
    {
        "phone_number": "0744556677",
        "full_name": "Mutua Musyoka",
        "gender": "Male",
        "age": 35,
        "county_name": "Machakos",
        "town_name": "Machakos",
        "ethnicity": "Kamba",
        "education_level": "Graduate",
        "profession": "Business Owner",
        "marital_status": "Divorced",
        "religion": "Christian",
        "self_description": "Entrepreneur running a logistics business in Machakos. Looking for a mature woman who understands the value of hard work and family.",
        "latitude": -1.5177,
        "longitude": 37.2634
    },
    {
        "phone_number": "0755667788",
        "full_name": "Hassan Ali",
        "gender": "Male",
        "age": 30,
        "county_name": "Garissa",
        "town_name": "Garissa",
        "ethnicity": "Somali",
        "education_level": "Graduate",
        "profession": "NGO Coordinator",
        "marital_status": "Single",
        "religion": "Muslim",
        "self_description": "I work with an NGO in Garissa. I value faith, family, and community service. Looking for a God-fearing partner.",
        "latitude": -0.4532,
        "longitude": 39.6461
    },
    {
        "phone_number": "0766778899",
        "full_name": "Wanjiku Mwangi",
        "gender": "Female",
        "age": 26,
        "county_name": "Nyeri",
        "town_name": "Nyeri",
        "ethnicity": "Kikuyu",
        "education_level": "Graduate",
        "profession": "Nurse",
        "marital_status": "Single",
        "religion": "Christian",
        "self_description": "Caring and compassionate nurse working in Nyeri. I love cooking and spending time with my family on weekends.",
        "latitude": -0.4167,
        "longitude": 36.9500
    },
    {
        "phone_number": "0777889900",
        "full_name": "Akinyi Ochieng",
        "gender": "Female",
        "age": 28,
        "county_name": "Siaya",
        "town_name": "Siaya",
        "ethnicity": "Luo",
        "education_level": "Graduate",
        "profession": "Journalist",
        "marital_status": "Single",
        "religion": "Christian",
        "self_description": "Outgoing and adventurous! Always on the move hunting for the next big story. Let's explore the world together.",
        "latitude": 0.0607,
        "longitude": 34.2881
    },
    {
        "phone_number": "0788990011",
        "full_name": "Chebet Koech",
        "gender": "Female",
        "age": 25,
        "county_name": "Kericho",
        "town_name": "Kericho",
        "ethnicity": "Kalenjin",
        "education_level": "Graduate",
        "profession": "Accountant",
        "marital_status": "Single",
        "religion": "Christian",
        "self_description": "Quiet but fun-loving once you get to know me. I enjoy tea farming, nature walks, and a good novel.",
        "latitude": -0.3692,
        "longitude": 35.2863
    },
    {
        "phone_number": "0799001122",
        "full_name": "Nduku Mutisya",
        "gender": "Female",
        "age": 31,
        "county_name": "Kitui",
        "town_name": "Kitui",
        "ethnicity": "Kamba",
        "education_level": "Masters",
        "profession": "HR Manager",
        "marital_status": "Single",
        "religion": "Christian",
        "self_description": "Strong, independent woman looking for a meaningful connection. Let's build a beautiful life together.",
        "latitude": -1.3683,
        "longitude": 38.0106
    },
    {
        "phone_number": "0700112233",
        "full_name": "Halima Omar",
        "gender": "Female",
        "age": 27,
        "county_name": "Mombasa",
        "town_name": "Mombasa",
        "ethnicity": "Swahili",
        "education_level": "Diploma",
        "profession": "Hotel Manager",
        "marital_status": "Single",
        "religion": "Muslim",
        "self_description": "Hospitality is my passion! Living by the beach in Mombasa, I love sunset walks, Swahili biryani, and peaceful weekends.",
        "latitude": -4.0435,
        "longitude": 39.6682
    }
]

app = create_app()

with app.app_context():
    print("Starting to insert dummy users...")
    
    added_count = 0
    for u_data in dummy_users:
        existing_user = User.query.filter_by(phone_number=u_data["phone_number"]).first()
        if not existing_user:
            new_user = User(
                phone_number=u_data["phone_number"],
                password_hash=generate_password_hash("password123"),
                full_name=u_data["full_name"],
                gender=u_data["gender"],
                age=u_data["age"],
                county_name=u_data["county_name"],
                town_name=u_data["town_name"],
                ethnicity=u_data["ethnicity"],
                education_level=u_data["education_level"],
                profession=u_data["profession"],
                marital_status=u_data["marital_status"],
                religion=u_data["religion"],
                self_description=u_data["self_description"],
                latitude=u_data["latitude"],
                longitude=u_data["longitude"],
                last_location_update=datetime.utcnow(),
                registration_stage='complete',
                registration_complete=True,
                is_active=True
            )
            db.session.add(new_user)
            added_count += 1
        else:
            print(f"User {u_data['phone_number']} already exists. Skipping.")
            
    try:
        db.session.commit()
        print(f"Successfully inserted {added_count} dummy users into the database!")
    except Exception as e:
        db.session.rollback()
        print(f"Error inserting dummy users: {e}")
