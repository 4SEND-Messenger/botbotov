import asyncio
import logging
import re
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

import database as db
import schedule
from config import BOT_TOKEN, ADMIN_ID, WEEKDAYS, WEEKDAY_ORDER, now, format_date

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def get_today():
    return now().date()


def get_start_of_week():
    today = get_today()
    return today - timedelta(days=today.weekday())


DAY_INDEX_TO_RU = {0: "Понедельник", 1: "Вторник", 2: "Среда", 3: "Четверг", 4: "Пятница", 5: "Суббота"}


def get_day_name(dt):
    return DAY_INDEX_TO_RU.get(dt.weekday(), "Неизвестно")


def sort_hw_by_schedule(hw_list, day_offset):
    order = schedule.WEEK_SCHEDULE.get(day_offset, [])
    order_map = {}
    idx = 0
    for subj in order:
        if subj not in order_map:
            order_map[subj] = idx
            idx += 1
    return sorted(hw_list, key=lambda x: order_map.get(x["subject"], 999))


def format_date_ru(d):
    return d.strftime("%d.%m.%Y")


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Помогу с д/з на неделю.\n\n"
        "Команды:\n"
        "/hw — д/з на всю неделю\n"
        "/hw_day — д/з на конкретный день\n"
        "/schedule — расписание на неделю\n"
        "/help — помощь по командам"
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "Команды:\n"
        "/hw — д/з на всю неделю\n"
        "/hw_day — д/з на конкретный день\n"
        "/schedule — Расписание на неделю"
    )


@router.message(Command("hw"))
async def cmd_hw(message: Message):
    args = message.text.split(maxsplit=1)

    if len(args) > 1:
        arg = args[1].strip().lower()

        if arg in WEEKDAYS:
            days_offset = WEEKDAY_ORDER.index(arg)
            start_of_week = get_start_of_week()
            target_date = start_of_week + timedelta(days=days_offset)
            hw_list = await db.get_hw_day(target_date.isoformat())

            if not hw_list:
                await message.answer(f"Нет д/з на {WEEKDAYS[arg]}")
                return

            hw_list = sort_hw_by_schedule(hw_list, days_offset)
            text = f"📅 {WEEKDAYS[arg]} ({format_date_ru(target_date)}):\n\n"
            for hw in hw_list:
                if hw["task"] == "—":
                    text += f"📖 {hw['subject']}: Домашнее задание отсутствует\n"
                else:
                    text += f"📖 {hw['subject']}: {hw['task']}\n"
            await message.answer(text)
            return

        if arg.isdigit():
            hw_list = await db.get_hw_week(int(arg))

            if not hw_list:
                await message.answer(f"Нет д/з за {arg} неделю")
                return

            text = f"📚 Домашнее задание на неделю ({arg}):\n\n"
            current_date = None
            current_hw = []
            day_idx = None
            for hw in hw_list:
                hw_date = hw["date"]
                if hw_date != current_date:
                    if current_hw:
                        current_hw = sort_hw_by_schedule(current_hw, day_idx)
                        for h in current_hw:
                            if h["task"] == "—":
                                text += f"  📖 {h['subject']}: Домашнее задание отсутствует\n"
                            else:
                                text += f"  📖 {h['subject']}: {h['task']}\n"
                    current_date = hw_date
                    day_idx = hw_date.weekday()
                    current_hw = []
                    text += f"\n📅 {get_day_name(hw_date)} ({format_date_ru(hw_date)}):\n"
                current_hw.append(hw)
            if current_hw:
                current_hw = sort_hw_by_schedule(current_hw, day_idx)
                for h in current_hw:
                    if h["task"] == "—":
                        text += f"  📖 {h['subject']}: Домашнее задание отсутствует\n"
                    else:
                        text += f"  📖 {h['subject']}: {h['task']}\n"
            await message.answer(text)
            return

    week_number = db.get_school_week(now())
    hw_list = await db.get_hw_week(week_number)

    if not hw_list:
        await message.answer("На этой неделе нет д/з")
        return

    text = f"📚 Домашнее задание на неделю ({week_number}):\n\n"
    current_date = None
    current_hw = []
    day_idx = None
    for hw in hw_list:
        hw_date = hw["date"]
        if hw_date != current_date:
            if current_hw:
                current_hw = sort_hw_by_schedule(current_hw, day_idx)
                for h in current_hw:
                    if h["task"] == "—":
                        text += f"  📖 {h['subject']}: Домашнее задание отсутствует\n"
                    else:
                        text += f"  📖 {h['subject']}: {h['task']}\n"
            current_date = hw_date
            day_idx = hw_date.weekday()
            current_hw = []
            text += f"\n📅 {get_day_name(hw_date)} ({format_date_ru(hw_date)}):\n"
        current_hw.append(hw)
    if current_hw:
        current_hw = sort_hw_by_schedule(current_hw, day_idx)
        for h in current_hw:
            if h["task"] == "—":
                text += f"  📖 {h['subject']}: Домашнее задание отсутствует\n"
            else:
                text += f"  📖 {h['subject']}: {h['task']}\n"
    await message.answer(text)


@router.message(Command("hw_day"))
async def cmd_hw_day(message: Message):
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer("Использование: /hw_day пн\nДни: пн, вт, ср, чт, пт, сб")
        return

    day_arg = args[1].strip().lower()

    if day_arg in WEEKDAYS:
        days_offset = WEEKDAY_ORDER.index(day_arg)
        start_of_week = get_start_of_week()
        target_date = start_of_week + timedelta(days=days_offset)
    else:
        days_offset = None
        try:
            target_date = datetime.strptime(day_arg, "%d.%m.%Y").date()
        except ValueError:
            await message.answer("Неверный формат. Используй: пн, вт, ср, чт, пт, сб или ДД.ММ.ГГГГ")
            return

    hw_list = await db.get_hw_day(target_date.isoformat())

    if not hw_list:
        await message.answer(f"Нет д/з на {format_date_ru(target_date)}")
        return

    if days_offset is not None:
        hw_list = sort_hw_by_schedule(hw_list, days_offset)

    text = f"📅 {get_day_name(target_date)} ({format_date_ru(target_date)}):\n\n"
    for hw in hw_list:
        if hw["task"] == "—":
            text += f"📖 {hw['subject']}: Домашнее задание отсутствует\n"
        else:
            text += f"📖 {hw['subject']}: {hw['task']}\n"
    await message.answer(text)


@router.message(Command("subjects"))
async def cmd_subjects(message: Message):
    week_number = db.get_school_week(now())
    subjects = await db.get_subjects(week_number)

    if not subjects:
        await message.answer("На этой неделе нет предметов с д/з")
        return

    text = f"📚 Предметы за {week_number} неделю:\n\n"
    for i, subj in enumerate(subjects, 1):
        text += f"{i}. {subj}\n"
    await message.answer(text)


@router.message(Command("set_hw"))
async def cmd_set_hw(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Только админ может добавлять д/з")
        return

    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer(
            "Формат: /set_hw Предмет ДД.ММ.ГГГГ Описание\n"
            "Пример: /set_hw Математика 10.09.2026 Упр. 12 стр. 45"
        )
        return

    text = args[1].strip()
    match = re.search(r'\b(\d{2}\.\d{2}\.\d{4})\b', text)

    if not match:
        await message.answer("Не нашлась дата в формате ДД.ММ.ГГГГ")
        return

    date_str = match.group(1)
    subject = text[:match.start()].strip()
    task = text[match.end():].strip()

    if not subject:
        await message.answer("Не указан предмет")
        return

    if not task:
        await message.answer("Не указано описание")
        return

    try:
        datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        await message.answer("Неверный формат даты. Используй ДД.ММ.ГГГГ")
        return

    hw_id = await db.add_hw(subject, date_str, task, message.from_user.id)
    await message.answer(f"✅ Д/з добавлено!\n\n{subject} — {date_str}\n{task}")


@router.message(Command("del_hw"))
async def cmd_del_hw(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Только админ может удалять д/з")
        return

    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer("Формат: /del_hw Название предмета\nУдалит все д/з по предмету за эту неделю")
        return

    subject = args[1].strip()
    deleted = await db.delete_hw_by_subject(subject)

    if deleted == 0:
        await message.answer(f"Не найдено д/з по предмету '{subject}' за эту неделю")
    else:
        await message.answer(f"✅ Удалено {deleted} записей по предмету '{subject}'")


@router.message(Command("set_admin"))
async def cmd_set_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Только текущий админ может назначать новых")
        return

    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer("Формат: /set_admin USER_ID\nПолучить ID можно через /myid")
        return

    try:
        new_admin_id = int(args[1].strip())
    except ValueError:
        await message.answer("ID должен быть числом")
        return

    import os
    os.environ["ADMIN_ID"] = str(new_admin_id)
    global ADMIN_ID
    ADMIN_ID = new_admin_id
    await message.answer(f"✅ Новый админ: {new_admin_id}")


@router.message(Command("myid"))
async def cmd_myid(message: Message):
    await message.answer(f"Твой ID: {message.from_user.id}")


@router.message(Command("fill_schedule"))
async def cmd_fill_schedule(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Только админ может заполнять расписание")
        return

    count = await schedule.fill_week_schedule(db, message.from_user.id)
    await message.answer(f"✅ Расписание заполнено! Добавлено {count} предметов на неделю")


@router.message(Command("clean_duplicates"))
async def cmd_clean_duplicates(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Только админ может очищать базу")
        return

    deleted = await db.clean_duplicates()
    await message.answer(f"✅ Удалено дублей: {deleted}")


@router.message(Command("schedule"))
async def cmd_schedule(message: Message):
    start_of_week = get_start_of_week()

    text = "📅 Расписание на неделю:\n\n"

    for day_offset, day_name in enumerate(WEEKDAY_ORDER):
        target_date = start_of_week + timedelta(days=day_offset)
        subjects = schedule.WEEK_SCHEDULE.get(day_offset, [])

        text += f"📆 {WEEKDAYS[day_name]} ({format_date_ru(target_date)}):\n"
        for i, subj in enumerate(subjects, 1):
            text += f"  {i}. {subj}\n"
        text += "\n"

    await message.answer(text)


@router.message(Command("adm_help"))
async def cmd_adm_help(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Только для админа")
        return

    await message.answer(
        "Админ-команды:\n\n"
        "/set_hw Предмет ДД.ММ.ГГГГ Описание — добавить ДЗ\n"
        "/del_hw Предмет — удалить ДЗ по предмету за неделю\n"
        "/fill_schedule — заполнить расписание на неделю\n"
        "/clean_duplicates — удалить дубли из базы\n"
        "/set_admin ID — назначить нового админа\n"
        "/remind set Текст 30m — создать напоминание\n"
        "/remind list — список напоминаний\n"
        "/remind del ID — удалить напоминание\n"
        "/myid — твой Telegram ID"
    )


def parse_interval(text: str):
    text = text.strip().lower()
    if text.endswith("m"):
        return int(text[:-1])
    if text.endswith("h"):
        return int(text[:-1]) * 60
    return int(text)


@router.message(Command("remind"))
async def cmd_remind(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Только админ может управлять напоминаниями")
        return

    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer(
            "Формат:\n"
            "/remind set Текст 30m — создать (каждые 30 мин)\n"
            "/remind set Текст 2h — создать (каждые 2 часа)\n"
            "/remind list — список\n"
            "/remind del ID — удалить"
        )
        return

    parts = args[1].strip().split(maxsplit=1)
    action = parts[0].lower()

    if action == "set":
        if len(parts) < 2:
            await message.answer("Формат: /remind set Текст 30m")
            return

        inner = parts[1].strip()
        tokens = inner.rsplit(maxsplit=1)

        if len(tokens) < 2:
            await message.answer("Укажи интервал в конце: 30m, 1h, и т.д.")
            return

        text_part = tokens[0]
        interval_str = tokens[1]

        try:
            interval = parse_interval(interval_str)
        except ValueError:
            await message.answer("Неверный формат интервала. Используй: 30m, 1h, 120")
            return

        if interval < 1:
            await message.answer("Минимальный интервал — 1 минута")
            return

        reminder_id = await db.add_reminder(text_part, interval, message.chat.id)
        await message.answer(
            f"✅ Напоминание создано!\n\n"
            f"📝 {text_part}\n"
            f"⏱ Каждые {interval} мин\n"
            f"🆔 {reminder_id}"
        )

    elif action == "list":
        all_reminders = await db.list_reminders()

        if not all_reminders:
            await message.answer("Нет активных напоминаний")
            return

        text = "📋 Напоминания:\n\n"
        for r in all_reminders:
            text += f"🆔 {r['_id']}\n"
            text += f"📝 {r['text']}\n"
            text += f"⏱ Каждые {r['interval_minutes']} мин\n\n"
        await message.answer(text)

    elif action == "del":
        if len(parts) < 2:
            await message.answer("Формат: /remind del ID")
            return

        reminder_id = parts[1].strip()
        deleted = await db.delete_reminder(reminder_id)

        if deleted:
            await message.answer("✅ Напоминание удалено")
        else:
            await message.answer("Не найдено")

    else:
        await message.answer("Неизвестное действие. Используй: set, list, del")


async def reminder_loop():
    while True:
        try:
            due = await db.get_due_reminders()
            for r in due:
                try:
                    await bot.send_message(r["chat_id"], f"🔔 {r['text']}")
                    await db.mark_reminder_sent(str(r["_id"]))
                except Exception:
                    pass
        except Exception:
            pass
        await asyncio.sleep(30)


async def main():
    dp.include_router(router)
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
