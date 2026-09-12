import asyncio
import io
import logging
import re
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from aiogram.types import BufferedInputFile

import database as db
import schedule
import image_gen
from config import BOT_TOKEN, ADMIN_ID, WEEKDAYS, WEEKDAY_ORDER, now, format_date

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
bot_username = ""


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def get_today():
    return now().date()


def get_display_date():
    dt = now()
    if dt.weekday() == 4 and dt.hour >= 14:
        return dt.date() + timedelta(days=3)
    if dt.weekday() > 4:
        return dt.date() + timedelta(days=(7 - dt.weekday()))
    return dt.date()


def is_next_week():
    dt = now()
    return (dt.weekday() == 4 and dt.hour >= 14) or dt.weekday() > 4


def get_week_title(week_number):
    if is_next_week():
        return f"📚 Д/з на следующую неделю ({week_number})"
    return f"📚 Д/з на текущую неделю ({week_number})"


def get_display_datetime():
    d = get_display_date()
    return datetime(d.year, d.month, d.day)


def get_start_of_week():
    d = get_display_date()
    return d - timedelta(days=d.weekday())


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
        "Основные команды:\n"
        "/menu - интерактивное меню\n"
        "/schedule — расписание на неделю\n"
        "/next - д/з на ближайший учебный день\n\n"
        "Дополнительные команды:\n"
        "/hw — д/з на всю неделю\n"
        "/hw_day — д/з на конкретный день\n"
        "/hw_week — д/з на конкретную неделю\n\n"
        "Нашли баг или есть предложение по улучшению? - @onlymlrd"
    )


MAIN_MENU = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📚 Д/з на неделю", callback_data="menu_hw")],
    [InlineKeyboardButton(text="📅 Д/з на день", callback_data="menu_days")],
    [InlineKeyboardButton(text="📆 Расписание", callback_data="menu_schedule")],
    [InlineKeyboardButton(text="⏳ Каникулы", callback_data="menu_countdown")],
])

DAYS_MENU = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="Пн", callback_data="day_0"),
        InlineKeyboardButton(text="Вт", callback_data="day_1"),
        InlineKeyboardButton(text="Ср", callback_data="day_2"),
    ],
    [
        InlineKeyboardButton(text="Чт", callback_data="day_3"),
        InlineKeyboardButton(text="Пт", callback_data="day_4"),
        InlineKeyboardButton(text="Сб", callback_data="day_5"),
    ],
    [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")],
])

BACK_MENU = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")],
])


def build_hw_text(hw_list, title):
    if not hw_list:
        return f"{title}\n\nД/з нет"
    text = f"{title}\n\n"
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
    return text


def build_day_hw_text(hw_list, day_offset):
    if not hw_list:
        return "Д/з нет"
    hw_list = sort_hw_by_schedule(hw_list, day_offset)
    text = ""
    for hw in hw_list:
        if hw["task"] == "—":
            text += f"📖 {hw['subject']}: Домашнее задание отсутствует\n"
        else:
            text += f"📖 {hw['subject']}: {hw['task']}\n"
    return text


def build_hw_by_day(hw_list):
    hw_by_day = {}
    current_date = None
    current_hw = []
    day_idx = None
    for hw in hw_list:
        hw_date = hw["date"]
        if hw_date != current_date:
            if current_hw:
                current_hw = sort_hw_by_schedule(current_hw, day_idx)
                day_key = f"{get_day_name(current_date)} {format_date_ru(current_date)}"
                hw_by_day[day_key] = current_hw
            current_date = hw_date
            day_idx = hw_date.weekday()
            current_hw = []
        current_hw.append(hw)
    if current_hw:
        current_hw = sort_hw_by_schedule(current_hw, day_idx)
        day_key = f"{get_day_name(current_date)} {format_date_ru(current_date)}"
        hw_by_day[day_key] = current_hw
    return hw_by_day


async def send_hw_photo(target, hw_list, title):
    if not hw_list:
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(f"{title}\n\nД/з нет", reply_markup=BACK_MENU)
            await target.answer()
        else:
            await target.answer(f"{title}\n\nД/з нет")
        return

    hw_by_day = build_hw_by_day(hw_list)
    text = build_hw_text(hw_list, title)
    img = image_gen.generate_hw_image(hw_by_day, title)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    photo = BufferedInputFile(buf.getvalue(), filename="hw.png")

    if isinstance(target, CallbackQuery):
        await target.message.delete()
        await target.message.answer_photo(photo=photo, caption=text, reply_markup=BACK_MENU)
        await target.answer()
    else:
        await target.answer_photo(photo=photo, caption=text)


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer("📋 Меню:", reply_markup=MAIN_MENU)


@router.callback_query(F.data == "menu_main")
async def callback_menu_main(callback: CallbackQuery):
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer("📋 Меню:", reply_markup=MAIN_MENU)
    else:
        await callback.message.edit_text("📋 Меню:", reply_markup=MAIN_MENU)
    await callback.answer()


@router.callback_query(F.data == "menu_hw")
async def callback_menu_hw(callback: CallbackQuery):
    week_number = db.get_school_week(get_display_datetime())
    hw_list = await db.get_hw_week(week_number)
    await send_hw_photo(callback, hw_list, get_week_title(week_number))


@router.callback_query(F.data == "menu_days")
async def callback_menu_days(callback: CallbackQuery):
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer("📅 Выбери день:", reply_markup=DAYS_MENU)
    else:
        await callback.message.edit_text("📅 Выбери день:", reply_markup=DAYS_MENU)
    await callback.answer()


@router.callback_query(F.data.startswith("day_"))
async def callback_day(callback: CallbackQuery):
    day_offset = int(callback.data.split("_")[1])
    day_name = WEEKDAYS[WEEKDAY_ORDER[day_offset]]
    start_of_week = get_start_of_week()
    target_date = start_of_week + timedelta(days=day_offset)
    hw_list = await db.get_hw_day(target_date.isoformat())
    title = f"📅 {day_name} ({format_date_ru(target_date)})"

    if not hw_list:
        await callback.message.edit_text(f"{title}\n\nД/з нет", reply_markup=DAYS_MENU)
        await callback.answer()
        return

    hw_list = sort_hw_by_schedule(hw_list, day_offset)
    hw_by_day = {title: hw_list}
    text = f"{title}\n\n"
    for hw in hw_list:
        if hw["task"] == "—":
            text += f"📖 {hw['subject']}: Домашнее задание отсутствует\n"
        else:
            text += f"📖 {hw['subject']}: {hw['task']}\n"

    img = image_gen.generate_hw_image(hw_by_day, title)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    photo = BufferedInputFile(buf.getvalue(), filename="hw.png")

    await callback.message.delete()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к дням", callback_data="menu_days")],
    ])
    await callback.message.answer_photo(photo=photo, caption=text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "menu_schedule")
async def callback_menu_schedule(callback: CallbackQuery):
    start_of_week = get_start_of_week()
    text = "📅 Расписание на неделю:\n\n"
    for day_offset, day_name in enumerate(WEEKDAY_ORDER):
        target_date = start_of_week + timedelta(days=day_offset)
        subjects = schedule.WEEK_SCHEDULE.get(day_offset, [])
        text += f"📆 {WEEKDAYS[day_name]} ({format_date_ru(target_date)}):\n"
        for i, subj in enumerate(subjects, 1):
            text += f"  {i}. {subj}\n"
        text += "\n"
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=BACK_MENU)
    else:
        await callback.message.edit_text(text, reply_markup=BACK_MENU)
    await callback.answer()


@router.callback_query(F.data == "menu_countdown")
async def callback_menu_countdown(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=VACATIONS_LABELS[k], callback_data=f"countdown_{k}")]
        for k in VACATIONS
    ] + [[InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")]])
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer("Выбери каникулы:", reply_markup=keyboard)
    else:
        await callback.message.edit_text("Выбери каникулы:", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("countdown_"))
async def callback_countdown(callback: CallbackQuery):
    key = callback.data.replace("countdown_", "")
    name, start, end = VACATIONS[key]
    today = now().date()

    if today >= start and today <= end:
        text = f"🎉 {name.capitalize()} — УЖЕ НАЧАЛИСЬ!"
    elif today > start:
        text = f"🎉 {name.capitalize()} — уже прошли"
    else:
        days_left = (start - today).days
        word = days_word(days_left)
        text = f"⏳ До {name} осталось {days_left} {word}"

    text += f"\n📅 {format_date_ru(start)} — {format_date_ru(end)}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к каникулам", callback_data="menu_countdown")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


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
            title = f"📅 {WEEKDAYS[arg]} ({format_date_ru(target_date)})"
            hw_by_day = {title: hw_list}
            text = f"{title}\n\n"
            for hw in hw_list:
                if hw["task"] == "—":
                    text += f"📖 {hw['subject']}: Домашнее задание отсутствует\n"
                else:
                    text += f"📖 {hw['subject']}: {hw['task']}\n"

            img = image_gen.generate_hw_image(hw_by_day, title)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            photo = BufferedInputFile(buf.getvalue(), filename="hw.png")
            await message.answer_photo(photo=photo, caption=text)
            return

        if arg.isdigit():
            hw_list = await db.get_hw_week(int(arg))

            if not hw_list:
                await message.answer(f"Нет д/з за {arg} неделю")
                return

            title = f"📚 Домашнее задание на неделю ({arg})"
            await send_hw_photo(message, hw_list, title)
            return

    week_number = db.get_school_week(get_display_datetime())
    hw_list = await db.get_hw_week(week_number)

    if not hw_list:
        await message.answer("На этой неделе нет д/з")
        return

    title = get_week_title(week_number)
    await send_hw_photo(message, hw_list, title)


SCHOOL_START = datetime(2026, 9, 1).date()
SCHOOL_END = datetime(2028, 5, 25).date()


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

    if not (SCHOOL_START <= target_date <= SCHOOL_END):
        await message.answer("Неверно введенная дата")
        return

    hw_list = await db.get_hw_day(target_date.isoformat())

    if not hw_list:
        await message.answer(f"Нет д/з на {format_date_ru(target_date)}")
        return

    if days_offset is not None:
        hw_list = sort_hw_by_schedule(hw_list, days_offset)

    title = f"📅 {get_day_name(target_date)} ({format_date_ru(target_date)})"
    hw_by_day = {title: hw_list}
    text = f"{title}\n\n"
    for hw in hw_list:
        if hw["task"] == "—":
            text += f"📖 {hw['subject']}: Домашнее задание отсутствует\n"
        else:
            text += f"📖 {hw['subject']}: {hw['task']}\n"

    img = image_gen.generate_hw_image(hw_by_day, title)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    photo = BufferedInputFile(buf.getvalue(), filename="hw.png")
    await message.answer_photo(photo=photo, caption=text)


@router.message(Command("hw_week"))
async def cmd_hw_week(message: Message):
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer("Использование: /hw_week 2\n(номер учебной недели)")
        return

    week_str = args[1].strip()

    if not week_str.isdigit() or int(week_str) < 1:
        await message.answer("Номер недели должен быть положительным числом")
        return

    week_number = int(week_str)
    hw_list = await db.get_hw_week(week_number)

    if not hw_list:
        await message.answer(f"Нет д/з за {week_number} неделю")
        return

    title = f"📚 Домашнее задание на неделю ({week_number})"
    await send_hw_photo(message, hw_list, title)


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


@router.message(Command("next"))
async def cmd_next(message: Message):
    current = now()
    today = current.date()

    if current.hour < 15 and today.weekday() < 5:
        target = today
    else:
        target = None
        for i in range(1, 8):
            check = today + timedelta(days=i)
            if check.weekday() < 5:
                target = check
                break

    hw_list = await db.get_hw_day(target.isoformat())
    day_name = get_day_name(target)

    text = f"📅 Ближайший учебный день: {day_name} ({format_date_ru(target)})\n\n"

    if not hw_list:
        text += "Д/з нет"
    else:
        hw_list = sort_hw_by_schedule(hw_list, target.weekday())
        for hw in hw_list:
            if hw["task"] == "—":
                text += f"📖 {hw['subject']}: Домашнее задание отсутствует\n"
            else:
                text += f"📖 {hw['subject']}: {hw['task']}\n"

    await message.answer(text)


import random as rnd

RANDOM_ANSWERS = [
    "Несомненно",
    "Разумеется",
    "Безусловно",
    "Конечно",
    "Да",
    "100%",
    "Можешь не сомневаться",
    "Тебе повезёт",
    "Звёзды говорят да",
    "Нет",
    "Не сегодня",
    "Никогда",
    "Забудь об этом",
    "Даже не думай",
    "Лучше не спрашивай",
    "Сомневаюсь",
    "Маловероятно",
    "Возможно, но не стоит надеяться",
    "Однозначно",
    "Сегодня точно нет",
    "Если повезет",
    "Не думаю",
    "Даже не надейся"
]


@router.message(F.text.regexp(r"^/random"))
async def cmd_random(message: Message):
    answer = rnd.choice(RANDOM_ANSWERS)
    await message.answer(f"🎱 {answer}")


VACATIONS = {
    "osen": ("осенних каникул", datetime(2026, 11, 1).date(), datetime(2026, 11, 8).date()),
    "zim": ("зимних каникул", datetime(2026, 12, 25).date(), datetime(2027, 1, 10).date()),
    "ves": ("весенних каникул", datetime(2027, 3, 21).date(), datetime(2027, 3, 28).date()),
    "let": ("летних каникул", datetime(2027, 6, 6).date(), datetime(2027, 8, 31).date()),
}

VACATIONS_LABELS = {
    "osen": "Осенние 🍂",
    "zim": "Зимние ❄️",
    "ves": "Весенние 🌸",
    "let": "Летние ☀️",
}


def days_word(n):
    if n % 10 == 1 and n % 100 != 11:
        return "день"
    elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "дня"
    else:
        return "дней"




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
    week_number = db.get_school_week(get_display_datetime())

    text = "📅 Расписание на неделю:\n\n"
    for day_offset, day_name in enumerate(WEEKDAY_ORDER):
        target_date = start_of_week + timedelta(days=day_offset)
        subjects = schedule.WEEK_SCHEDULE.get(day_offset, [])
        text += f"📆 {WEEKDAYS[day_name]} ({format_date_ru(target_date)}):\n"
        for i, subj in enumerate(subjects, 1):
            text += f"  {i}. {subj}\n"
        text += "\n"

    weekdays_labels = [WEEKDAYS[d] for d in WEEKDAY_ORDER]
    img = image_gen.generate_schedule_image(schedule.WEEK_SCHEDULE, week_number, weekdays_labels)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    photo = BufferedInputFile(buf.getvalue(), filename="schedule.png")
    await message.answer_photo(photo=photo, caption=text)


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


DAYS_HW_KEYWORDS = [
    "дз", "домашк", "домашн", "задани", "урок",
    "скинь", "кинь", "покаж", "напомни",
    "завтра", "сегодня",
    "понедельник", "понедельника",
    "вторник", "вторника",
    "среду", "среды",
    "четверг", "четверга",
    "пятницу", "пятницы",
    "субботу", "субботы",
    "пн", "вт", "ср", "чт", "пт", "сб",
]


def is_hw_request(text):
    t = text.lower()
    has_hw = any(w in t for w in ["дз", "домашк", "домашн", "задани", "урок"])
    has_action = any(w in t for w in ["скинь", "скиньте", "кинь", "киньте", "покаж", "покажите", "напомни", "напомните"])
    has_day = any(w in t for w in [
        "завтра", "сегодня",
        "понедельник", "понедельника",
        "вторник", "вторника",
        "среду", "среды",
        "четверг", "четверга",
        "пятницу", "пятницы",
        "субботу", "субботы",
        "пн", "вт", "ср", "чт", "пт", "сб",
    ])
    has_pzh = any(w in t for w in ["пж", "пжл", "pls", "плиз"])
    return has_hw or (has_action and has_day) or (has_action and has_pzh) or (has_hw and has_day)


@router.message(F.text)
async def ai_message_handler(message: Message):
    text = message.text.strip()
    if text.startswith("/"):
        return

    is_reply = message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.id == bot.id
    is_mention = message.text and f"@{bot_username}" in message.text
    is_group = message.chat.type in ("supergroup", "group")
    hw_request = is_hw_request(text)

    if is_group and not is_reply and not is_mention and not hw_request:
        return

    logger.info(f"AI request from {message.from_user.id} in {message.chat.id}: {text[:50]}")

    import ai_handler
    result = await ai_handler.process_message(text, message.chat.id, message.from_user.id)

    logger.info(f"AI result: {result}")

    if not result:
        return

    if "reply" in result:
        await message.answer(result["reply"])
        return

    func_name = result.get("function", "")
    args = result.get("args", {})

    if func_name == "get_hw_day":
        day = args.get("day", "пн")
        if day in WEEKDAYS:
            days_offset = WEEKDAY_ORDER.index(day)
            start_of_week = get_start_of_week()
            target_date = start_of_week + timedelta(days=days_offset)
            hw_list = await db.get_hw_day(target_date.isoformat())
            if not hw_list:
                await message.answer(f"Нет д/з на {WEEKDAYS[day]}")
            else:
                hw_list = sort_hw_by_schedule(hw_list, days_offset)
                title = f"📅 {WEEKDAYS[day]} ({format_date_ru(target_date)})"
                hw_by_day = {title: hw_list}
                text_out = f"{title}\n\n"
                for hw in hw_list:
                    if hw["task"] == "—":
                        text_out += f"📖 {hw['subject']}: Домашнее задание отсутствует\n"
                    else:
                        text_out += f"📖 {hw['subject']}: {hw['task']}\n"
                import io as _io
                img = image_gen.generate_hw_image(hw_by_day, title)
                buf = _io.BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                photo = BufferedInputFile(buf.getvalue(), filename="hw.png")
                await message.answer_photo(photo=photo, caption=text_out)

    elif func_name == "get_hw_tomorrow":
        from ai_handler import get_next_school_day
        target = get_next_school_day()
        hw_list = await db.get_hw_day(target.isoformat())
        if not hw_list:
            await message.answer(f"Нет д/з на {format_date_ru(target)}")
        else:
            day_offset = target.weekday()
            hw_list = sort_hw_by_schedule(hw_list, day_offset)
            title = f"📅 {get_day_name(target)} ({format_date_ru(target)})"
            hw_by_day = {title: hw_list}
            text_out = f"{title}\n\n"
            for hw in hw_list:
                if hw["task"] == "—":
                    text_out += f"📖 {hw['subject']}: Домашнее задание отсутствует\n"
                else:
                    text_out += f"📖 {hw['subject']}: {hw['task']}\n"
            import io as _io
            img = image_gen.generate_hw_image(hw_by_day, title)
            buf = _io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            photo = BufferedInputFile(buf.getvalue(), filename="hw.png")
            await message.answer_photo(photo=photo, caption=text_out)

    elif func_name == "get_hw_today":
        today = now().date()
        hw_list = await db.get_hw_day(today.isoformat())
        if not hw_list:
            await message.answer(f"Нет д/з на сегодня ({format_date_ru(today)})")
        else:
            day_offset = today.weekday()
            hw_list = sort_hw_by_schedule(hw_list, day_offset)
            title = f"📅 {get_day_name(today)} ({format_date_ru(today)})"
            hw_by_day = {title: hw_list}
            text_out = f"{title}\n\n"
            for hw in hw_list:
                if hw["task"] == "—":
                    text_out += f"📖 {hw['subject']}: Домашнее задание отсутствует\n"
                else:
                    text_out += f"📖 {hw['subject']}: {hw['task']}\n"
            import io as _io
            img = image_gen.generate_hw_image(hw_by_day, title)
            buf = _io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            photo = BufferedInputFile(buf.getvalue(), filename="hw.png")
            await message.answer_photo(photo=photo, caption=text_out)

    elif func_name == "get_hw_week":
        week = args.get("week", db.get_school_week(now()))
        hw_list = await db.get_hw_week(int(week))
        if not hw_list:
            await message.answer(f"Нет д/з за {week} неделю")
        else:
            title = f"📚 Д/з на неделю ({week})"
            await send_hw_photo(message, hw_list, title)

    elif func_name == "get_schedule":
        await cmd_schedule(message)

    elif func_name == "get_next":
        await cmd_next(message)

    elif func_name == "get_week_number":
        week = db.get_school_week(now())
        await message.answer(f"📅 Номер текущей учебной недели: {week}")


async def main():
    global bot_username
    me = await bot.get_me()
    bot_username = me.username
    dp.include_router(router)
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
