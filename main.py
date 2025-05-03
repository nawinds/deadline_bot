import datetime
import logging
import os
import requests
import asyncio
from aiogram import Bot
import datetime as dt
import locale
import urllib.parse
from typing import Optional

# Modify the links and data below:
DEADLINES_URL = "https://m3102.nawinds.dev/DEADLINES.json"
ADD_DEADLINE_LINK = "https://m3102.nawinds.dev/deadlines-editing-instructions/"
BOT_NAME = "Дединсайдер"
BOT_USERNAME = "m3104_deadliner_bot"

# Environment variables that should be available:
TOKEN = os.getenv("TOKEN")
MAIN_GROUP_ID = int(os.getenv("MAIN_GROUP_ID"))

logging.basicConfig(level=logging.INFO)

bot = Bot(TOKEN)

NUMBER_EMOJIS = ['0.', '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']

async def get_current_time() -> str:
    current_time = dt.datetime.now()
    current_time_hour = current_time.hour if current_time.hour >= 10 else "0" + str(current_time.hour)
    current_time_minute = current_time.minute if current_time.minute >= 10 else "0" + str(current_time.minute)
    return f"{current_time_hour}:{current_time_minute}"

def get_dt_obj_from_string(time: str) -> Optional[dt.datetime]:
    time = time.replace('GMT+3', '+0300')
    locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
    try:
        dt_obj = dt.datetime.strptime(time, "%d %b %Y %H:%M:%S %z")
        return dt_obj
    except ValueError:
        return None

async def generate_link(event_name: str, event_time: str) -> str:
    dt_obj = get_dt_obj_from_string(event_time)
    if dt_obj:
        formatted_time = dt_obj.strftime("%Y%m%d T%H%M%S%z")
        description = f"Дедлайн добавлен ботом {BOT_NAME} (https://t.me/{BOT_USERNAME})"
        link = f"https://calendar.google.com/calendar/u/0/r/eventedit?" \
               f"text={urllib.parse.quote(event_name)}&" \
               f"dates={formatted_time}/{formatted_time}&details={urllib.parse.quote(description)}&" \
               f"color=6"

        return link
    return ""


async def get_human_timedelta(time: str) -> str:
    dt_obj = get_dt_obj_from_string(time)
    if dt_obj:
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
    return ""


async def get_human_time(time: str) -> str:
    dt_obj = get_dt_obj_from_string(time)
    if dt_obj:
        locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
        formatted_date = dt_obj.strftime("%a, %d %B в %H:%M")
        return formatted_date
    return ""


def timestamp_func(a: dict) -> float:
    time = a["time"].replace('GMT+3', '+0300')
    locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
    a_timestamp = dt.datetime.strptime(time, "%d %b %Y %H:%M:%S %z").timestamp()
    return a_timestamp  # 29 Oct 2024 23:59:59 GMT+3

def relevant_filter_func(d: dict) -> bool:
    dt_obj = get_dt_obj_from_string(d["time"])
    if dt_obj < dt.datetime.now(dt_obj.tzinfo):
        return False
    return True

def deadlines_filter_func(d: dict) -> bool:
    if "[тест]" in d["name"].lower():
        return False
    return True

async def get_message_text() -> str:
    try:
        response = requests.get(DEADLINES_URL).json()
    except Exception as e:
        print(f"{datetime.datetime.now()} Failed to fetch deadlines: {e}")
        return ""
    deadlines = response["deadlines"]

    tests = list(filter(lambda t: not deadlines_filter_func(t) and relevant_filter_func(t), deadlines))
    deadlines = list(filter(lambda d: deadlines_filter_func(d) and relevant_filter_func(d), deadlines))

    text = f"🔥️️ <b>Дедлайны</b> (<i>Обновлено в {await get_current_time()} 🔄</i>):\n\n"
    tests = sorted(tests, key=lambda x: timestamp_func(x))
    deadlines = sorted(deadlines, key=lambda x: timestamp_func(x))

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

        # human_timedelta = await get_human_timedelta(deadlines[i]["time"])
        link = await generate_link(deadlines[i]['name'], deadlines[i]['time'])
        human_time = await get_human_time(deadlines[i]["time"])

        if human_time:
            text += f"</b>\n(<a href='{link}'>"
            text += human_time + "</a>)\n\n"
        else:
            text += "</b> — " + deadlines[i]["time"] + "\n\n"

    if len(tests) > 0:
        text += f"\n🧑‍💻 <b>Тесты</b>:\n\n"

        for i in range(len(tests)):
            test_name = tests[i]["name"].replace("[Тест] ", "").replace("[тест]", "")
            test_url = tests[i].get("url")
            no = i + 1
            if no < 11:
                no = NUMBER_EMOJIS[no] + " "
            else:
                no += ". "

            text += str(no) + "<b>"

            if test_url:
                text += f"<a href='{test_url}'>{test_name}</a>"
            else:
                text += test_name

            text += "</b>"

            text += f"\n(<a href='{await generate_link(test_name, tests[i]['time'])}'>"
            text += await get_human_time(tests[i]["time"]) + "</a>)\n\n"

            text += f"\n🆕 <a href='{ADD_DEADLINE_LINK}'>" \
            f"Добавить дедлайн/тест</a>"
    return text

async def send_deadlines(chat_id: int) -> None:
    text = await get_message_text()
    msg = await bot.send_message(chat_id, text, parse_mode="HTML", disable_web_page_preview=True)
    started_updating = dt.datetime.now()
    print(datetime.datetime.now(), "Message sent. Msg id:", msg.message_id)

    while dt.datetime.now() - started_updating < dt.timedelta(days=1):
        await asyncio.sleep(60)
        try:
            new_text = await get_message_text()
            if text != new_text and new_text != "":
                await msg.edit_text(new_text, parse_mode="HTML", disable_web_page_preview=True)
                text = new_text
                print(datetime.datetime.now(), "Message updated. Msg id:", msg.message_id)
            else:
                print(datetime.datetime.now(), "Message update skipped. Msg id:", msg.message_id)

        except Exception as e:
            logging.warning(datetime.datetime.now(),f"{datetime.datetime.now()} Error updating message: {e}")
            continue
    await msg.delete()


async def main():
    await send_deadlines(MAIN_GROUP_ID)
    await bot.session.close()


if __name__ == '__main__':
    asyncio.run(main())
