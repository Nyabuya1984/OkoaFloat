import os
import sys

def read_backend_logs():
    log_file = "/home/wycliffe/Desktop/PENZI_2.50/backend/app.log"
    if not os.path.exists(log_file):
        # Maybe it's somewhere else? Let's check system_generated logs
        log_file = "/home/wycliffe/.gemini/antigravity/brain/9133346e-9c9f-4d37-b7d5-8a7ec5ed26ea/.system_generated/logs/overview.txt"
    
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            lines = f.readlines()
            
        # Get last 100 lines
        recent = lines[-100:]
        print("".join(recent))
    else:
        print(f"Log file not found: {log_file}")

if __name__ == "__main__":
    read_backend_logs()
