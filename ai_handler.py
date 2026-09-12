import json
import logging
import aiohttp
import database as db
from datetime import datetime, timedelta
from config import now, GEMINI_API_KEY, GEMINI_API_KEY_TWO, GEMINI_API_KEY_THREE, GROQ_API_KEY, AI_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

GEMINI_KEYS = [k for k in [GEMINI_API_KEY, GEMINI_API_KEY_TWO, GEMINI_API_KEY_THREE] if k]

GEMINI_MODELS = [
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
]

SYSTEM_PROMPT = """Ты бот Bot Botov в школьном чате. Общаешься как друг: коротко, по делу, без однотипности.

Правила:
- Всегда пиши с маленькой буквы
- Мат и сленг только когда уместно, не ради мата
- Не повторяйся - каждый ответ должен быть разным
- Короткие ответы, 1-2 предложения
- Если просят дз/расписание - вызывай функцию
- Если болтают - ответь как живой человек"""

FUNCTION_BLOCK = """
Доступные функции:
- get_hw_day(day: str) - дз на день. day: пн, вт, ср, чт, пт, сб
- get_hw_week() - дз на всю неделю
- get_hw_tomorrow() - дз на завтра
- get_hw_today() - дз на сегодня
- get_schedule() - расписание
- get_next() - ближайший учебный день
- get_week_number() - номер недели

Правила:
- "скинь дз", "дз", "кинь дз", "покажи дз", "скиньте дз", "дайте дз", "нужно дз" -> get_hw_week()
- "дз на завтра" -> get_hw_tomorrow()
- "дз на пн" -> get_hw_day("пн")
- "расписание" -> get_schedule()

Отвечай ТОЛЬКО в JSON:
{"function": "название", "args": {}}
или
{"reply": "твой ответ"}"""


def create_safety_settings():
    return [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]


async def get_available_models(api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m["name"].split("/")[-1] for m in data.get("models", [])]
                    return [m for m in GEMINI_MODELS if m in models]
    except Exception as e:
        logger.warning(f"Failed to get models for key ...{api_key[-6:]}: {e}")
    return []


async def call_gemini_model(model, api_key, messages, system_prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1000},
        "safetySettings": create_safety_settings()
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            else:
                err = await resp.text()
                logger.warning(f"Gemini {model} key ...{api_key[-6:]} status {resp.status}: {err[:200]}")
                return None


async def call_gemini(messages, system_prompt):
    if not GEMINI_KEYS:
        return None

    for api_key in GEMINI_KEYS:
        models = await get_available_models(api_key)
        if not models:
            models = GEMINI_MODELS[:1]

        for model in models:
            try:
                result = await call_gemini_model(model, api_key, messages, system_prompt)
                if result:
                    logger.info(f"Gemini OK: {model} key ...{api_key[-6:]}")
                    return result
            except Exception as e:
                logger.warning(f"Gemini {model} error: {e}")
    return None


async def call_groq(messages, system_prompt):
    if not GROQ_API_KEY:
        return None

    all_messages = [{"role": "system", "content": system_prompt}] + messages

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": all_messages,
        "temperature": 0.7,
        "max_tokens": 1000
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"Groq error: {e}")
    return None


def parse_response(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def get_next_school_day():
    today = now().date()
    if now().hour >= 15:
        start = today + timedelta(days=1)
    else:
        start = today
    for i in range(7):
        check = start + timedelta(days=i)
        if check.weekday() < 5:
            return check
    return today


async def process_message(text, chat_id, user_id):
    personality = AI_SYSTEM_PROMPT if AI_SYSTEM_PROMPT else SYSTEM_PROMPT
    system = personality + FUNCTION_BLOCK

    await db.save_chat_message(chat_id, user_id, "user", text)

    history = await db.get_chat_history(chat_id, limit=20)
    messages = []
    for h in history:
        role = "user" if h["role"] == "user" else "model"
        messages.append({"role": role, "content": h["text"]})

    if not messages or messages[-1]["content"] != text:
        messages.append({"role": "user", "content": text})

    result = None

    result = await call_gemini(messages, system)
    if result:
        parsed = parse_response(result)
        if parsed:
            await db.save_chat_message(chat_id, user_id, "model", result)
            return parsed
        await db.save_chat_message(chat_id, user_id, "model", result)
        return {"reply": result}

    result = await call_groq(messages, system)
    if result:
        parsed = parse_response(result)
        if parsed:
            await db.save_chat_message(chat_id, user_id, "model", result)
            return parsed
        await db.save_chat_message(chat_id, user_id, "model", result)
        return {"reply": result}

    return fallback_parse(text)


def fallback_parse(text):
    text = text.lower().strip()

    if any(w in text for w in ["привет", "здравствуй", "хай", "хелло", "йо", "йоу", "здарова", "салам", "дела", "как ты", "че как", "чо как"]):
        return {"reply": "Привет! Я помогу с д/з и расписанием. Спроси что нужно!"}

    if any(w in text for w in ["завтра", "на завтра"]):
        return {"function": "get_hw_tomorrow", "args": {}}

    if any(w in text for w in ["сегодня", "на сегодня"]):
        return {"function": "get_hw_today", "args": {}}

    if "расписан" in text:
        return {"function": "get_schedule", "args": {}}

    if any(w in text for w in ["неделя", "номер недели", "какая неделя"]):
        return {"function": "get_week_number", "args": {}}

    if any(w in text for w in ["следующий день", "ближайший", "когда следующий"]):
        return {"function": "get_next", "args": {}}

    days_map = {
        "понедельник": "пн", "пн": "пн", "понедельника": "пн",
        "вторник": "вт", "вт": "вт", "вторника": "вт",
        "среду": "ср", "ср": "ср", "среды": "ср",
        "четверг": "чт", "чт": "чт", "четверга": "чт",
        "пятницу": "пт", "пт": "пт", "пятницы": "пт",
        "субботу": "сб", "сб": "сб", "субботы": "сб",
    }
    for word, code in days_map.items():
        if word in text:
            return {"function": "get_hw_day", "args": {"day": code}}

    if any(w in text for w in ["дз", "домашк", "домашн", "задани", "урок", "скинь", "кинь", "покажи", "дай", "нужно"]):
        return {"function": "get_hw_week", "args": {}}

    if "спасибо" in text or "пасиб" in text or "сенкс" in text:
        return {"reply": "Пожалуйста!"}

    return {"reply": "Не понял тебя. Попробуй: дз на завтра, расписание, номер недели"}
