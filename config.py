import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5130423971"))

if not BOT_TOKEN:
    print("[OGOHLANTIRISH] BOT_TOKEN .env faylida topilmadi!")

if not GEMINI_API_KEY:
    print("[OGOHLANTIRISH] GEMINI_API_KEY .env faylida topilmadi!")
