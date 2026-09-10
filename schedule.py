from datetime import datetime, timedelta

SCHOOL_YEAR_START = datetime(2026, 9, 1)


def get_school_week(dt):
    delta = dt.date() - SCHOOL_YEAR_START.date()
    return delta.days // 7 + 1


WEEK_SCHEDULE = {
    0: [
        "Бел. лит.",
        "Бел. яз.",
        "Химия",
        "Геометрия",
        "Ист. Бел.",
    ],
    1: [
        "Физ-ра",
        "Физика",
        "Англ. яз.",
        "Алгебра",
        "Черчение",
        "УПК",
        "УПК",
    ],
    2: [
        "Ист. Бел.",
        "Алгебра",
        "Русск. яз.",
        "Русск. лит.",
        "Биология",
        "Обществоведение",
    ],
    3: [
        "География",
        "Химия",
        "Физ-ра",
        "Англ. яз.",
        "Биология",
        "УПК",
        "УПК",
    ],
    4: [
        "Бел. лит.",
        "Русск. яз.",
        "Бассейн",
        "Информатика",
        "Геометрия",
        "Физика",
    ],
    5: [
        "УПК",
        "УПК",
    ],
}


async def fill_week_schedule(db_module, added_by: int):
    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday())
    week_number = get_school_week(datetime.now())
    count = 0

    for day_offset, subjects in WEEK_SCHEDULE.items():
        target_date = datetime.combine(start_of_week + timedelta(days=day_offset), datetime.min.time())
        for subject in subjects:
            existing = await db_module.homework.find_one({
                "subject": subject,
                "date": target_date,
            })
            if not existing:
                await db_module.homework.insert_one({
                    "subject": subject,
                    "date": target_date,
                    "week_number": week_number,
                    "task": "—",
                    "added_by": added_by,
                    "created_at": datetime.now(),
                })
                count += 1

    return count
