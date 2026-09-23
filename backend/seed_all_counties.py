import sys
import os

# Add the backend directory to sys.path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from app import create_app
from app.extensions import db
from app.models.user import User
from werkzeug.security import generate_password_hash
from datetime import datetime

counties_data = [
    {"county": "Mombasa", "town": "Mombasa", "name": "Ali Hassan", "gender": "Male", "ethnicity": "Swahili", "phone": "0701000001", "lat": -4.0435, "lon": 39.6682},
    {"county": "Kwale", "town": "Kwale", "name": "Halima Chizi", "gender": "Female", "ethnicity": "Digo", "phone": "0701000002", "lat": -4.1736, "lon": 39.4521},
    {"county": "Kilifi", "town": "Kilifi", "name": "Kazungu Kenga", "gender": "Male", "ethnicity": "Giriama", "phone": "0701000003", "lat": -3.6305, "lon": 39.8499},
    {"county": "Tana River", "town": "Hola", "name": "Mwanajuma Kase", "gender": "Female", "ethnicity": "Pokomo", "phone": "0701000004", "lat": -1.5000, "lon": 40.0333},
    {"county": "Lamu", "town": "Lamu", "name": "Omar Lali", "gender": "Male", "ethnicity": "Bajuni", "phone": "0701000005", "lat": -2.2696, "lon": 40.9006},
    {"county": "Taita-Taveta", "town": "Mwatate", "name": "Shali Mwakazi", "gender": "Female", "ethnicity": "Taita", "phone": "0701000006", "lat": -3.5047, "lon": 38.3778},
    {"county": "Garissa", "town": "Garissa", "name": "Abdi Farah", "gender": "Male", "ethnicity": "Somali", "phone": "0701000007", "lat": -0.4532, "lon": 39.6461},
    {"county": "Wajir", "town": "Wajir", "name": "Halima Salat", "gender": "Female", "ethnicity": "Somali", "phone": "0701000008", "lat": 1.7471, "lon": 40.0573},
    {"county": "Mandera", "town": "Mandera", "name": "Ibrahim Ali", "gender": "Male", "ethnicity": "Somali", "phone": "0701000009", "lat": 3.9372, "lon": 41.8569},
    {"county": "Marsabit", "town": "Marsabit", "name": "Qabale Duba", "gender": "Female", "ethnicity": "Borana", "phone": "0701000010", "lat": 2.3333, "lon": 37.9833},
    {"county": "Isiolo", "town": "Isiolo", "name": "Halakhe Dida", "gender": "Male", "ethnicity": "Borana", "phone": "0701000011", "lat": 0.3500, "lon": 37.5833},
    {"county": "Meru", "town": "Meru", "name": "Makena Kobia", "gender": "Female", "ethnicity": "Meru", "phone": "0701000012", "lat": 0.0463, "lon": 37.6496},
    {"county": "Tharaka-Nithi", "town": "Kathwana", "name": "Gitonga Njagi", "gender": "Male", "ethnicity": "Tharaka", "phone": "0701000013", "lat": -0.3000, "lon": 37.9000},
    {"county": "Embu", "town": "Embu", "name": "Wawira Njiru", "gender": "Female", "ethnicity": "Embu", "phone": "0701000014", "lat": -0.5333, "lon": 37.4500},
    {"county": "Kitui", "town": "Kitui", "name": "Musyoka Mwendwa", "gender": "Male", "ethnicity": "Kamba", "phone": "0701000015", "lat": -1.3683, "lon": 38.0106},
    {"county": "Machakos", "town": "Machakos", "name": "Mutio Ndambuki", "gender": "Female", "ethnicity": "Kamba", "phone": "0701000016", "lat": -1.5177, "lon": 37.2634},
    {"county": "Makueni", "town": "Wote", "name": "Mutua Kivutha", "gender": "Male", "ethnicity": "Kamba", "phone": "0701000017", "lat": -1.7833, "lon": 37.6333},
    {"county": "Nyandarua", "town": "Ol Kalou", "name": "Wanjiku Githinji", "gender": "Female", "ethnicity": "Kikuyu", "phone": "0701000018", "lat": -0.2667, "lon": 36.3833},
    {"county": "Nyeri", "town": "Nyeri", "name": "Maina Kagia", "gender": "Male", "ethnicity": "Kikuyu", "phone": "0701000019", "lat": -0.4167, "lon": 36.9500},
    {"county": "Kirinyaga", "town": "Kerugoya", "name": "Wambui Karua", "gender": "Female", "ethnicity": "Kikuyu", "phone": "0701000020", "lat": -0.4983, "lon": 37.2804},
    {"county": "Murang'a", "town": "Murang'a", "name": "Mwangi Kangata", "gender": "Male", "ethnicity": "Kikuyu", "phone": "0701000021", "lat": -0.7167, "lon": 37.1500},
    {"county": "Kiambu", "town": "Kiambu", "name": "Njeri Kuria", "gender": "Female", "ethnicity": "Kikuyu", "phone": "0701000022", "lat": -1.1714, "lon": 36.8356},
    {"county": "Turkana", "town": "Lodwar", "name": "Ekiru Ekal", "gender": "Male", "ethnicity": "Turkana", "phone": "0701000023", "lat": 3.1167, "lon": 35.6000},
    {"county": "West Pokot", "town": "Kapenguria", "name": "Chepochot Lonyang", "gender": "Female", "ethnicity": "Pokot", "phone": "0701000024", "lat": 1.2333, "lon": 35.1167},
    {"county": "Samburu", "town": "Maralal", "name": "Lempurkel Lesuuda", "gender": "Male", "ethnicity": "Samburu", "phone": "0701000025", "lat": 1.1000, "lon": 36.7000},
    {"county": "Trans-Nzoia", "town": "Kitale", "name": "Nafula Simiyu", "gender": "Female", "ethnicity": "Luhya", "phone": "0701000026", "lat": 1.0167, "lon": 35.0000},
    {"county": "Uasin Gishu", "town": "Eldoret", "name": "Kipchoge Keino", "gender": "Male", "ethnicity": "Kalenjin", "phone": "0701000027", "lat": 0.5143, "lon": 35.2698},
    {"county": "Elgeyo-Marakwet", "town": "Iten", "name": "Jeruto Kiptoo", "gender": "Female", "ethnicity": "Kalenjin", "phone": "0701000028", "lat": 0.6731, "lon": 35.5083},
    {"county": "Nandi", "town": "Kapsabet", "name": "Kipruto Sang", "gender": "Male", "ethnicity": "Kalenjin", "phone": "0701000029", "lat": 0.2000, "lon": 35.1000},
    {"county": "Baringo", "town": "Kabarnet", "name": "Jepkemboi Cheboi", "gender": "Female", "ethnicity": "Kalenjin", "phone": "0701000030", "lat": 0.4905, "lon": 35.7429},
    {"county": "Laikipia", "town": "Rumuruti", "name": "Nderitu Muriithi", "gender": "Male", "ethnicity": "Kikuyu", "phone": "0701000031", "lat": 0.2713, "lon": 36.5385},
    {"county": "Nakuru", "town": "Nakuru", "name": "Wanjiru Mbugua", "gender": "Female", "ethnicity": "Kikuyu", "phone": "0701000032", "lat": -0.3031, "lon": 36.0800},
    {"county": "Narok", "town": "Narok", "name": "Ole Ntutu", "gender": "Male", "ethnicity": "Maasai", "phone": "0701000033", "lat": -1.0833, "lon": 35.8667},
    {"county": "Kajiado", "town": "Kajiado", "name": "Naserian Ntimama", "gender": "Female", "ethnicity": "Maasai", "phone": "0701000034", "lat": -1.8500, "lon": 36.7833},
    {"county": "Kericho", "town": "Kericho", "name": "Kipngeno Mutai", "gender": "Male", "ethnicity": "Kalenjin", "phone": "0701000035", "lat": -0.3692, "lon": 35.2863},
    {"county": "Bomet", "town": "Bomet", "name": "Chepkoech Laboso", "gender": "Female", "ethnicity": "Kalenjin", "phone": "0701000036", "lat": -0.7813, "lon": 35.3416},
    {"county": "Kakamega", "town": "Kakamega", "name": "Oparanya Ambetsa", "gender": "Male", "ethnicity": "Luhya", "phone": "0701000037", "lat": 0.2833, "lon": 34.7500},
    {"county": "Vihiga", "town": "Vihiga", "name": "Khavugwi Kagesi", "gender": "Female", "ethnicity": "Luhya", "phone": "0701000038", "lat": 0.0833, "lon": 34.7167},
    {"county": "Bungoma", "town": "Bungoma", "name": "Wanyonyi Wangamati", "gender": "Male", "ethnicity": "Luhya", "phone": "0701000039", "lat": 0.5667, "lon": 34.5667},
    {"county": "Busia", "town": "Busia", "name": "Auma Ojwang", "gender": "Female", "ethnicity": "Luhya", "phone": "0701000040", "lat": 0.4608, "lon": 34.1115},
    {"county": "Siaya", "town": "Siaya", "name": "Ochieng Orengo", "gender": "Male", "ethnicity": "Luo", "phone": "0701000041", "lat": 0.0607, "lon": 34.2881},
    {"county": "Kisumu", "town": "Kisumu", "name": "Awino Nyong'o", "gender": "Female", "ethnicity": "Luo", "phone": "0701000042", "lat": -0.0917, "lon": 34.7680},
    {"county": "Homa Bay", "town": "Homa Bay", "name": "Odhiambo Awiti", "gender": "Male", "ethnicity": "Luo", "phone": "0701000043", "lat": -0.5273, "lon": 34.4531},
    {"county": "Migori", "town": "Migori", "name": "Boke Chacha", "gender": "Female", "ethnicity": "Kuria", "phone": "0701000044", "lat": -1.0667, "lon": 34.4667},
    {"county": "Kisii", "town": "Kisii", "name": "Nyachae Ongwae", "gender": "Male", "ethnicity": "Kisii", "phone": "0701000045", "lat": -0.6817, "lon": 34.7667},
    {"county": "Nyamira", "town": "Nyamira", "name": "Kerubo Okioma", "gender": "Female", "ethnicity": "Kisii", "phone": "0701000046", "lat": -0.5667, "lon": 35.0000},
    {"county": "Nairobi", "town": "Nairobi (City)", "name": "Omondi Kamau", "gender": "Male", "ethnicity": "Mixed", "phone": "0701000047", "lat": -1.286389, "lon": 36.817223}
]

app = create_app()

with app.app_context():
    print("Starting to insert 47 county dummy users...")
    
    added_count = 0
    for u_data in counties_data:
        existing_user = User.query.filter_by(phone_number=u_data["phone"]).first()
        if not existing_user:
            new_user = User(
                phone_number=u_data["phone"],
                password_hash=generate_password_hash("password123"),
                full_name=u_data["name"],
                gender=u_data["gender"],
                age=28 if u_data["gender"] == "Female" else 30,
                county_name=u_data["county"],
                town_name=u_data["town"],
                ethnicity=u_data["ethnicity"],
                education_level="Graduate",
                profession="Business",
                marital_status="Single",
                religion="Christian",
                self_description=f"Proud resident of {u_data['county']} county. Let's connect!",
                latitude=u_data["lat"],
                longitude=u_data["lon"],
                last_location_update=datetime.utcnow(),
                registration_stage='complete',
                registration_complete=True,
                is_active=True
            )
            db.session.add(new_user)
            added_count += 1
        else:
            print(f"User {u_data['phone']} already exists. Skipping.")
            
    try:
        db.session.commit()
        print(f"Successfully inserted {added_count} county-level users into the database!")
    except Exception as e:
        db.session.rollback()
        print(f"Error inserting users: {e}")
