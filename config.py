import os
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DB_NAME", "homework_bot")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_API_KEY_TWO = os.getenv("GEMINI_API_KEY_TWO", "")
GEMINI_API_KEY_THREE = os.getenv("GEMINI_API_KEY_THREE", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
AI_SYSTEM_PROMPT = os.getenv("AI_SYSTEM_PROMPT", "Ты бот Bot Botov в школьном чате. Общаешься как друг: коротко, по делу, без однотипности. Правила: всегда пиши с маленькой буквы. Мат и сленг только когда уместно, не ради мата. Не повторяйся - каждый ответ должен быть разным. Короткие ответы, 1-2 предложения. Если просят дз/расписание - вызывай функцию. Если болтают - ответь как живой человек.")
TZ = ZoneInfo("Europe/Minsk")
WEEKDAYS = {
    "пн": "Понедельник",
    "вт": "Вторник",
    "ср": "Среда",
    "чт": "Четверг",
    "пт": "Пятница",
    "сб": "Суббота",
}
WEEKDAY_ORDER = ["пн", "вт", "ср", "чт", "пт", "сб"]


def now():
    return datetime.now(TZ)


def format_date(d):
    return d.strftime("%d.%m.%Y")
