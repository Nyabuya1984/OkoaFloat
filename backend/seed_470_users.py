import sys
import os
import random
from datetime import datetime

# Add the backend directory to sys.path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from app import create_app
from app.extensions import db
from app.models.user import User
from werkzeug.security import generate_password_hash

counties_info = [
    {"county": "Mombasa", "town": "Mombasa", "lat": -4.0435, "lon": 39.6682, "region": "coast"},
    {"county": "Kwale", "town": "Kwale", "lat": -4.1736, "lon": 39.4521, "region": "coast"},
    {"county": "Kilifi", "town": "Kilifi", "lat": -3.6305, "lon": 39.8499, "region": "coast"},
    {"county": "Tana River", "town": "Hola", "lat": -1.5000, "lon": 40.0333, "region": "coast"},
    {"county": "Lamu", "town": "Lamu", "lat": -2.2696, "lon": 40.9006, "region": "coast"},
    {"county": "Taita-Taveta", "town": "Mwatate", "lat": -3.5047, "lon": 38.3778, "region": "coast"},
    
    {"county": "Garissa", "town": "Garissa", "lat": -0.4532, "lon": 39.6461, "region": "northeast"},
    {"county": "Wajir", "town": "Wajir", "lat": 1.7471, "lon": 40.0573, "region": "northeast"},
    {"county": "Mandera", "town": "Mandera", "lat": 3.9372, "lon": 41.8569, "region": "northeast"},
    
    {"county": "Marsabit", "town": "Marsabit", "lat": 2.3333, "lon": 37.9833, "region": "eastern"},
    {"county": "Isiolo", "town": "Isiolo", "lat": 0.3500, "lon": 37.5833, "region": "eastern"},
    {"county": "Meru", "town": "Meru", "lat": 0.0463, "lon": 37.6496, "region": "eastern"},
    {"county": "Tharaka-Nithi", "town": "Kathwana", "lat": -0.3000, "lon": 37.9000, "region": "eastern"},
    {"county": "Embu", "town": "Embu", "lat": -0.5333, "lon": 37.4500, "region": "eastern"},
    {"county": "Kitui", "town": "Kitui", "lat": -1.3683, "lon": 38.0106, "region": "eastern"},
    {"county": "Machakos", "town": "Machakos", "lat": -1.5177, "lon": 37.2634, "region": "eastern"},
    {"county": "Makueni", "town": "Wote", "lat": -1.7833, "lon": 37.6333, "region": "eastern"},
    
    {"county": "Nyandarua", "town": "Ol Kalou", "lat": -0.2667, "lon": 36.3833, "region": "central"},
    {"county": "Nyeri", "town": "Nyeri", "lat": -0.4167, "lon": 36.9500, "region": "central"},
    {"county": "Kirinyaga", "town": "Kerugoya", "lat": -0.4983, "lon": 37.2804, "region": "central"},
    {"county": "Murang'a", "town": "Murang'a", "lat": -0.7167, "lon": 37.1500, "region": "central"},
    {"county": "Kiambu", "town": "Kiambu", "lat": -1.1714, "lon": 36.8356, "region": "central"},
    
    {"county": "Turkana", "town": "Lodwar", "lat": 3.1167, "lon": 35.6000, "region": "rift"},
    {"county": "West Pokot", "town": "Kapenguria", "lat": 1.2333, "lon": 35.1167, "region": "rift"},
    {"county": "Samburu", "town": "Maralal", "lat": 1.1000, "lon": 36.7000, "region": "rift"},
    {"county": "Trans-Nzoia", "town": "Kitale", "lat": 1.0167, "lon": 35.0000, "region": "rift"},
    {"county": "Uasin Gishu", "town": "Eldoret", "lat": 0.5143, "lon": 35.2698, "region": "rift"},
    {"county": "Elgeyo-Marakwet", "town": "Iten", "lat": 0.6731, "lon": 35.5083, "region": "rift"},
    {"county": "Nandi", "town": "Kapsabet", "lat": 0.2000, "lon": 35.1000, "region": "rift"},
    {"county": "Baringo", "town": "Kabarnet", "lat": 0.4905, "lon": 35.7429, "region": "rift"},
    {"county": "Laikipia", "town": "Rumuruti", "lat": 0.2713, "lon": 36.5385, "region": "rift"},
    {"county": "Nakuru", "town": "Nakuru", "lat": -0.3031, "lon": 36.0800, "region": "rift"},
    {"county": "Narok", "town": "Narok", "lat": -1.0833, "lon": 35.8667, "region": "rift"},
    {"county": "Kajiado", "town": "Kajiado", "lat": -1.8500, "lon": 36.7833, "region": "rift"},
    {"county": "Kericho", "town": "Kericho", "lat": -0.3692, "lon": 35.2863, "region": "rift"},
    {"county": "Bomet", "town": "Bomet", "lat": -0.7813, "lon": 35.3416, "region": "rift"},
    
    {"county": "Kakamega", "town": "Kakamega", "lat": 0.2833, "lon": 34.7500, "region": "western"},
    {"county": "Vihiga", "town": "Vihiga", "lat": 0.0833, "lon": 34.7167, "region": "western"},
    {"county": "Bungoma", "town": "Bungoma", "lat": 0.5667, "lon": 34.5667, "region": "western"},
    {"county": "Busia", "town": "Busia", "lat": 0.4608, "lon": 34.1115, "region": "western"},
    
    {"county": "Siaya", "town": "Siaya", "lat": 0.0607, "lon": 34.2881, "region": "nyanza"},
    {"county": "Kisumu", "town": "Kisumu", "lat": -0.0917, "lon": 34.7680, "region": "nyanza"},
    {"county": "Homa Bay", "town": "Homa Bay", "lat": -0.5273, "lon": 34.4531, "region": "nyanza"},
    {"county": "Migori", "town": "Migori", "lat": -1.0667, "lon": 34.4667, "region": "nyanza"},
    {"county": "Kisii", "town": "Kisii", "lat": -0.6817, "lon": 34.7667, "region": "nyanza"},
    {"county": "Nyamira", "town": "Nyamira", "lat": -0.5667, "lon": 35.0000, "region": "nyanza"},
    
    {"county": "Nairobi", "town": "Nairobi (City)", "lat": -1.286389, "lon": 36.817223, "region": "nairobi"}
]

names_db = {
    "coast": {
        "male": ["Juma", "Ali", "Hassan", "Omar", "Kazungu", "Masha", "Hiribae", "Said"],
        "female": ["Fatuma", "Halima", "Khadija", "Mwanajuma", "Kadzo", "Amina", "Salma"]
    },
    "northeast": {
        "male": ["Abdi", "Mohamed", "Ibrahim", "Yussuf", "Farah", "Salat", "Ali"],
        "female": ["Amina", "Hawa", "Halima", "Nimo", "Fardosa", "Khadija", "Zahra"]
    },
    "eastern": {
        "male": ["Mutua", "Musyoka", "Guyo", "Mutuma", "Gitonga", "Nyaga", "Kioko", "Wario"],
        "female": ["Syombua", "Ndambuki", "Kendi", "Makena", "Kagendo", "Wawira", "Mutheu", "Qabale"]
    },
    "central": {
        "male": ["Kamau", "Njoroge", "Mwangi", "Maina", "Njuguna", "Ndathi", "Waititu"],
        "female": ["Wanjiku", "Njeri", "Wangari", "Wambui", "Nyambura", "Muthoni", "Wairimu"]
    },
    "rift": {
        "male": ["Kiprono", "Kipchoge", "Kiprop", "Ole Ntutu", "Ekiru", "Lempurkel", "Wanjala", "Mutai"],
        "female": ["Chebet", "Jepkorir", "Chepkoech", "Naserian", "Akiru", "Nafula", "Sian"]
    },
    "western": {
        "male": ["Oparanya", "Mudavadi", "Wanyonyi", "Ojaamong", "Barasa", "Simiyu", "Wafula"],
        "female": ["Nekesa", "Khavugwi", "Nasimiyu", "Auma", "Nanjala", "Nafula"]
    },
    "nyanza": {
        "male": ["Ochieng", "Otieno", "Odhiambo", "Obado", "Nyachae", "Nyagarama", "Okelo"],
        "female": ["Akinyi", "Awino", "Achieng", "Boke", "Kwamboka", "Kerubo", "Atieno"]
    },
    "nairobi": {
        "male": ["Kamau", "Ochieng", "Kiprono", "Mutua", "Ali", "Wanjala", "Brian", "Kevin", "David"],
        "female": ["Wanjiku", "Akinyi", "Chebet", "Syombua", "Fatuma", "Nekesa", "Mercy", "Faith", "Grace"]
    }
}

professions = ["Software Engineer", "Teacher", "Farmer", "Business Owner", "Accountant", "Nurse", "Journalist", "HR Manager", "Logistics", "Doctor", "Architect", "Mechanic", "Sales Executive", "Chef"]

app = create_app()

with app.app_context():
    print("Starting to insert 470 dummy users (5 men, 5 women per county)...")
    
    password = generate_password_hash("password123")
    added_count = 0
    phone_counter = 710000000
    
    users_to_add = []
    
    for c in counties_info:
        region = c["region"]
        
        # 5 Men
        for i in range(5):
            phone_counter += 1
            m_first = random.choice(names_db[region]["male"])
            m_last = random.choice(names_db[region]["male"])
            while m_last == m_first:
                m_last = random.choice(names_db[region]["male"])
            
            users_to_add.append(User(
                phone_number=f"0{phone_counter}",
                password_hash=password,
                full_name=f"{m_first} {m_last}",
                gender="Male",
                age=random.randint(22, 45),
                county_name=c["county"],
                town_name=c["town"],
                ethnicity="Kenyan",
                education_level=random.choice(["Graduate", "Diploma", "Masters"]),
                profession=random.choice(professions),
                marital_status=random.choice(["Single", "Divorced", "Widowed"]),
                religion=random.choice(["Christian", "Muslim"]),
                self_description=f"Living in {c['county']}. Looking for genuine connections.",
                latitude=c["lat"] + random.uniform(-0.02, 0.02),
                longitude=c["lon"] + random.uniform(-0.02, 0.02),
                last_location_update=datetime.utcnow(),
                registration_stage='complete',
                registration_complete=True,
                is_active=True
            ))
            
        # 5 Women
        for i in range(5):
            phone_counter += 1
            f_first = random.choice(names_db[region]["female"])
            f_last = random.choice(names_db[region]["female"])
            while f_last == f_first:
                f_last = random.choice(names_db[region]["female"])
                
            users_to_add.append(User(
                phone_number=f"0{phone_counter}",
                password_hash=password,
                full_name=f"{f_first} {f_last}",
                gender="Female",
                age=random.randint(20, 40),
                county_name=c["county"],
                town_name=c["town"],
                ethnicity="Kenyan",
                education_level=random.choice(["Graduate", "Diploma", "Masters"]),
                profession=random.choice(professions),
                marital_status=random.choice(["Single", "Divorced", "Widowed"]),
                religion=random.choice(["Christian", "Muslim"]),
                self_description=f"From {c['county']}. Let's chat and see where it goes!",
                latitude=c["lat"] + random.uniform(-0.02, 0.02),
                longitude=c["lon"] + random.uniform(-0.02, 0.02),
                last_location_update=datetime.utcnow(),
                registration_stage='complete',
                registration_complete=True,
                is_active=True
            ))
            
    # Batch insert logic
    try:
        # Check existing to prevent duplicates based on phone (though we generated them sequentially)
        existing_phones = {u.phone_number for u in User.query.with_entities(User.phone_number).all()}
        new_users = [u for u in users_to_add if u.phone_number not in existing_phones]
        
        db.session.bulk_save_objects(new_users)
        db.session.commit()
        print(f"Successfully inserted {len(new_users)} county-level users into the database!")
    except Exception as e:
        db.session.rollback()
        print(f"Error inserting users: {e}")
