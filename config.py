import os
from datetime import datetime
from zoneinfo import ZoneInfo

BOT_TOKEN = os.getenv("BOT_TOKEN", "8839585652:AAEs3Ap7uz7ITQxqkKyr9yFH6OF2YoVz9As")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8741454987"))
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://jokerbrawl756_db_user:kCHTa7N5wia2@ac-yywggra-shard-00-00.myf3ckd.mongodb.net:27017,ac-yywggra-shard-00-01.myf3ckd.mongodb.net:27017,ac-yywggra-shard-00-02.myf3ckd.mongodb.net:27017/?tls=true&tlsAllowInvalidCertificates=true&authSource=admin&retryWrites=true&w=majority")
DB_NAME = os.getenv("DB_NAME", "homework_bot")
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
