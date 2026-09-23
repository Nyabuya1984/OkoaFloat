

STARTING FRONTEND SERVER

Step 1: Start the React Frontend
bash

# In a new terminal, navigate to frontend
cd dating-app/frontend

# Start the React development server
npm start

The React app will open automatically at http://localhost:3000.
2. Test the Application

    Open your browser at http://localhost:3000

    Enter a phone number (e.g., 0721143188)

    Click "Activate Service" - This sends the PENZI command
==========================================================================================================
==========================================================================================================

BACKEND

Method 1: 

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install all required packages
pip install -r requirements.txt

# Make sure you're in the directory containing run.py
python run.py
# or
python3 run.py


Method 2: Using Flask command

# Set the Flask application
export FLASK_APP=app.py  # On macOS/Linux
# or
set FLASK_APP=app.py     # On Windows

# Set debug mode (optional)
export FLASK_DEBUG=1     # On macOS/Linux
# or
set FLASK_DEBUG=1        # On Windows

# Run the server
flask run


Method 3: With custom host and port
bash

# Run on all network interfaces (accessible from other devices)
python app.py --host=0.0.0.0 --port=5000

# Or set environment variables
export HOST=0.0.0.0
export PORT=5000
python app.py

8. Verify the Server is Running
Test with your browser:

Open your browser and go to:

    http://localhost:5000/ - Root endpoint with API information

    http://localhost:5000/health - Health check

Test with curl (command line):
bash

# Health check
curl http://localhost:5000/health

# Root endpoint
curl http://localhost:5000/

# Test the matches endpoint
curl "http://localhost:5000/api/user/0721143188/matches?age_range=25-30&town=Nairobi"

Test with Postman:

    Open Postman

    Create a new request:

        Method: GET

        URL: http://localhost:5000/api/user/0721143188/matches?age_range=25-30&town=Nairobi

    Click Send

You should get a JSON response with matches.
9. Expected Output

When you start the server, you should see something like:
text

2026-07-29 10:30:00,123 - __main__ - INFO - Starting Dating Service API on http://0.0.0.0:5000
2026-07-29 10:30:00,123 - __main__ - INFO - Debug mode: True
2026-07-29 10:30:00,123 - __main__ - INFO - Health check: http://localhost:5000/health
2026-07-29 10:30:00,123 - __main__ - INFO - API root: http://localhost:5000/api/user/
 * Serving Flask app 'app.py'
 * Debug mode: on
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
 * Running on http://192.168.1.100:5000
 * Press CTRL+C to quit

10. Troubleshooting Common Issues
Port already in use:
bash

# On Windows - find and kill process using port 5000
netstat -ano | findstr :5000
taskkill /PID <PID> /F

# On macOS/Linux - find and kill process using port 5000
lsof -i :5000
kill -9 <PID>

Module not found errors:
bash

# Make sure you have all dependencies installed
pip install Flask Flask-CORS python-dotenv

# Or reinstall from requirements
pip install -r requirements.txt

Permission denied (Linux/macOS):
bash

# Try using a different port (e.g., 5001)
python app.py --port=5001

11. Quick Test Script

Create a test_api.py file to test your API:
python

"""
Quick API test script
Run this to verify your API is working
"""

import requests
import json

BASE_URL = "http://localhost:5000"

def test_health():
    """Test the health endpoint"""
    response = requests.get(f"{BASE_URL}/health")
    print(f"Health: {response.json()}")

def test_root():
    """Test the root endpoint"""
    response = requests.get(f"{BASE_URL}/")
    print(f"Root: {response.json()}")

def test_matches():
    """Test the matches endpoint"""
    url = f"{BASE_URL}/api/user/0721143188/matches?age_range=25-30&town=Nairobi"
    response = requests.get(url)
    print(f"Matches: {json.dumps(response.json(), indent=2)}")

def test_users():
    """Test the debug users endpoint"""
    response = requests.get(f"{BASE_URL}/api/user/debug/users")
    print(f"Users: {json.dumps(response.json(), indent=2)}")

if __name__ == "__main__":
    print("Testing Dating API...")
    test_health()
    test_root()
    test_matches()
    test_users()

Run it with:
bash

python test_api.py

12. Running in Production

For production, consider using a WSGI server like Gunicorn:
bash

# Install Gunicorn
pip install gunicorn

# Run with Gunicorn
gunicorn --bind 0.0.0.0:5000 app:app

Or use Waitress (Windows-friendly):
bash

# Install Waitress
pip install waitress

# Run with Waitress
waitress-serve --port=5000 app:app

13. Important Notes

    The user.py file must be in the same directory as app.py

    Port 5000 is the default - ensure nothing else is using it

    CORS is enabled, so you can test from any frontend

    Debug mode is enabled by default - disable in production

    The API uses mock data - replace with real database in production

Your Flask backend is now ready to serve the dating API! 🚀
