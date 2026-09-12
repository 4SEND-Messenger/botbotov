from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGODB_URI, DB_NAME, now

client = AsyncIOMotorClient(MONGODB_URI)
db = client[DB_NAME]
homework = db["homework"]
chat_history = db["chat_history"]

SCHOOL_YEAR_START = datetime(2026, 9, 1)


def get_school_week(dt):
    d = dt.date()
    first_monday = SCHOOL_YEAR_START.date() - timedelta(days=SCHOOL_YEAR_START.weekday())
    delta = d - first_monday
    return delta.days // 7 + 1


async def add_hw(subject: str, date_str: str, task: str, added_by: int):
    dt = datetime.strptime(date_str, "%d.%m.%Y")
    week_number = get_school_week(dt)
    date_dt = datetime.combine(dt.date(), datetime.min.time())
    filter_doc = {"subject": subject.strip(), "date": date_dt}
    update_doc = {
        "$set": {
            "task": task.strip(),
            "week_number": week_number,
            "added_by": added_by,
            "created_at": datetime.now(),
        }
    }
    result = await homework.update_one(filter_doc, update_doc, upsert=True)
    if result.upserted_id:
        return str(result.upserted_id)
    existing = await homework.find_one(filter_doc)
    return str(existing["_id"])


async def get_hw_week(week_number: int = None):
    if week_number is None:
        week_number = get_school_week(now())
    cursor = homework.find(
        {"week_number": week_number}).sort("date", 1)
    return await cursor.to_list(length=100)


async def get_hw_day(date_str: str):
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    cursor = homework.find({"date": datetime.combine(dt.date(), datetime.min.time())})
    return await cursor.to_list(length=50)


async def get_subjects(week_number: int = None):
    if week_number is None:
        week_number = get_school_week(now())
    return await homework.distinct("subject", {"week_number": week_number})


async def delete_hw(hw_id: str):
    from bson import ObjectId
    result = await homework.delete_one({"_id": ObjectId(hw_id)})
    return result.deleted_count > 0


async def delete_hw_by_subject(subject: str, week_number: int = None):
    if week_number is None:
        week_number = get_school_week(now())
    result = await homework.delete_many(
        {"subject": subject, "week_number": week_number}
    )
    return result.deleted_count


reminders = db["reminders"]


async def add_reminder(text: str, interval_minutes: int, chat_id: int):
    doc = {
        "text": text,
        "interval_minutes": interval_minutes,
        "chat_id": chat_id,
        "active": True,
        "created_at": datetime.now(),
        "last_sent": None,
    }
    result = await reminders.insert_one(doc)
    return str(result.inserted_id)


async def list_reminders():
    cursor = reminders.find({"active": True})
    return await cursor.to_list(length=100)


async def delete_reminder(reminder_id: str):
    from bson import ObjectId
    result = await reminders.delete_one({"_id": ObjectId(reminder_id)})
    return result.deleted_count > 0


async def get_due_reminders():
    current = now()
    cursor = reminders.find({
        "active": True,
        "$or": [
            {"last_sent": None},
            {"last_sent": {"$lte": current - timedelta(minutes=1)}},
        ]
    })
    return await cursor.to_list(length=100)


async def mark_reminder_sent(reminder_id: str):
    from bson import ObjectId
    await reminders.update_one(
        {"_id": ObjectId(reminder_id)},
        {"$set": {"last_sent": now()}}
    )
    cursor = homework.find().sort("date", 1)
    docs = await cursor.to_list(length=1000)
    seen = {}
    to_delete = []
    for doc in docs:
        key = (doc["subject"], doc["date"])
        if key in seen:
            to_delete.append(doc["_id"])
        else:
            seen[key] = doc["_id"]
    if to_delete:
        from bson import ObjectId
        await homework.delete_many({"_id": {"$in": to_delete}})
    return len(to_delete)


async def save_chat_message(chat_id, user_id, role, text):
    doc = {
        "chat_id": chat_id,
        "user_id": user_id,
        "role": role,
        "text": text,
        "timestamp": datetime.now()
    }
    await chat_history.insert_one(doc)


async def get_chat_history(chat_id, limit=20):
    cursor = chat_history.find(
        {"chat_id": chat_id}
    ).sort("timestamp", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    docs.reverse()
    return docs
