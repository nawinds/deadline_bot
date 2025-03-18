import logging
import os
import requests
import asyncio
from aiogram import Bot
import datetime as dt
import locale
from time import sleep
import urllib.parse
import aiohttp

# Modify the links and data below:
DEADLINES_URL = "https://m3104.nawinds.dev/DEADLINES.json"
ADD_DEADLINE_LINK = "https://m3104.nawinds.dev/deadlines-editing-instructions/"
BOT_NAME = "Дединсайдер M3104"
BOT_USERNAME = "m3104_deadliner_bot"

# Environment variables that should be available:
TOKEN = os.getenv("TOKEN")
MAIN_GROUP_ID = int(os.getenv("MAIN_GROUP_ID"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(TOKEN)

NUMBER_EMOJIS = ['0.', '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']

async def get_current_time() -> str:
    current_time = dt.datetime.now()
    current_time_hour = current_time.hour if current_time.hour >= 10 else "0" + str(current_time.hour)
    current_time_minute = current_time.minute if current_time.minute >= 10 else "0" + str(current_time.minute)
    return f"{current_time_hour}:{current_time_minute}"

async def get_dt_obj_from_string(time: str) -> dt.datetime:
    time = time.replace('GMT+3', '+0300')
    locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
    return dt.datetime.strptime(time, "%d %b %Y %H:%M:%S %z")

async def generate_link(event_name: str, event_time: str) -> str:
    dt_obj = await get_dt_obj_from_string(event_time)
    formatted_time = dt_obj.strftime("%Y%m%d T%H%M%S%z")
    description = f"Дедлайн добавлен ботом {BOT_NAME} (https://t.me/{BOT_USERNAME})"
    link = f"https://calendar.google.com/calendar/u/0/r/eventedit?" \
           f"text={urllib.parse.quote(event_name)}&" \
           f"dates={formatted_time}/{formatted_time}&details={urllib.parse.quote(description)}&" \
           f"color=6"
    return link

async def get_human_timedelta(time: str) -> str:
    dt_obj = await get_dt_obj_from_string(time)
    dt_now = dt.datetime.now(dt_obj.tzinfo)  # Ensure timezones are consistent
    delta = dt_obj - dt_now

    total_seconds = int(delta.total_seconds())
    days = total_seconds // (24 * 3600)
    hours = (total_seconds % (24 * 3600)) // 3600
    minutes = (total_seconds % 3600) // 60

    if days >= 5:
        return f"{days} дней"
    elif days >= 2:
        return f"{days} дня"
    elif days == 1:
        return f"1 день {hours}ч {minutes}м"
    else:
        return f"{hours}ч {minutes}м"

async def get_human_time(time: str) -> str:
    dt_obj = await get_dt_obj_from_string(time)
    locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
    formatted_date = dt_obj.strftime("%a, %d %B в %H:%M")
    return formatted_date

async def timestamp_func(a: dict) -> float:
    time = a["time"].replace('GMT+3', '+0300')
    locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
    a_timestamp = dt.datetime.strptime(time, "%d %b %Y %H:%M:%S %z").timestamp()
    return a_timestamp  # 29 Oct 2024 23:59:59 GMT+3

async def relevant_filter_func(d: dict) -> bool:
    dt_obj = await get_dt_obj_from_string(d["time"])
    if dt_obj < dt.datetime.now(dt_obj.tzinfo):
        return False
    return True

async def deadlines_filter_func(d: dict) -> bool:
    if "[тест]" in d["name"].lower():
        return False
    return True

async def get_message_text() -> str:
    try:
        response = requests.get(DEADLINES_URL).json()
    except Exception as e:
        logger.error(f"Failed to fetch deadlines: {e}")
        return ""
    deadlines = response["deadlines"]

    tests = list(filter(lambda t: not await deadlines_filter_func(t) and await relevant_filter_func(t), deadlines))
    deadlines = list(filter(lambda d: await deadlines_filter_func(d) and await relevant_filter_func(d), deadlines))

    text = f"🔥️️ <b>Дедлайны</b> (<i>Обновлено в {await get_current_time()} 🔄</i>):\n\n"
    tests = sorted(tests, key=lambda x: await timestamp_func(x))
    deadlines = sorted(deadlines, key=lambda x: await timestamp_func(x))

    if len(deadlines) == 0:
        text += "Дедлайнов нет)\n\n"

    for i in range(len(deadlines)):
        no = i + 1
        if no < 11:
            no = NUMBER_EMOJIS[no] + " "
        else:
            no += ". "
        text += str(no) + "<b>"

        if deadlines[i].get("url"):
            text += f"<a href='{deadlines[i]['url']}'>{deadlines[i]['name']}</a>"
        else:
            text += deadlines[i]["name"]

        text += "</b> — "
        text += await get_human_timedelta(deadlines[i]["time"])
        text += f"\n(<a href='{await generate_link(deadlines[i]['name'], deadlines[i]['time'])}'>"
        text += await get_human_time(deadlines[i]["time"]) + "</a>)\n\n"

    if len(tests) > 0:
        text += f"\n🧑‍💻 <b>Тесты</b>:\n\n"

        for i in range(len(tests)):
            test_name = tests[i]["name"].replace("[Тест] ", "").replace("[тест]", "")
            no = i + 1
            if no < 11:
                no = NUMBER_EMOJIS[no] + " "
            else:
                no += ". "
            text += str(no) + "<b>" + test_name
            text += "</b> — "
            text += await get_human_timedelta(tests[i]["time"])
            text += f"\n(<a href='{await generate_link(test_name, tests[i]['time'])}'>"
            text += await get_human_time(tests[i]["time"]) + "</a>)\n\n"

    text += f"\n🆕 <a href='{ADD_DEADLINE_LINK}'>" \
            f"Добавить дедлайн/тест</a>"
    return text

async def send_deadlines(chat_id: int) -> None:
    retries = 3
    for attempt in range(retries):
        try:
            text = await get_message_text()
            msg = await bot.send_message(chat_id, text, parse_mode="HTML", disable_web_page_preview=True)
            started_updating = dt.datetime.now()
            while dt.datetime.now() - started_updating < dt.timedelta(days=1):
                await asyncio.sleep(60)
                new_text = await get_message_text()
                if text != new_text and new_text != "":
                    await msg.edit_text(new_text, parse_mode="HTML", disable_web_page_preview=True)
                    text = new_text
            await msg.delete()
            break
        except aiohttp.ClientConnectorError as e:
            logger.error(f"Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            else:
                raise

async def main():
    try:
        await send_deadlines(MAIN_GROUP_ID)
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        await bot.session.close()

if __name__ == '__main__':
    asyncio.run(main())