import logging
import os
import requests
import asyncio
from aiogram import Bot
import datetime as dt
import locale
from time import sleep
import urllib.parse

TOKEN = os.getenv("TOKEN")
MAIN_GROUP_ID = int(os.getenv("MAIN_GROUP_ID"))

logging.basicConfig(level=logging.INFO)
bot = Bot(TOKEN)

NUMBER_EMOJIS = ['0.', '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']


def get_current_time() -> str:
    current_time = dt.datetime.now()
    current_time_hour = current_time.hour if current_time.hour >= 10 else "0" + str(current_time.hour)
    current_time_minute = current_time.minute if current_time.minute >= 10 else \
        "0" + str(current_time.minute)
    return f"{current_time_hour}:{current_time_minute}"


def get_dt_obj_from_string(time: str) -> dt.datetime:
    time = time.replace('GMT+3', '+0300')
    locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
    return dt.datetime.strptime(time, "%d %b %Y %H:%M:%S %z")


def generate_link(event_name: str, event_time: str) -> str:
    dt_obj = get_dt_obj_from_string(event_time)
    formatted_time = dt_obj.strftime("%Y%m%d T%H%M%S%z")
    description = "Дедлайн добавлен ботом Дединсайдер M3104 (https://t.me/m3104_deadliner_bot)"
    link = f"https://calendar.google.com/calendar/u/0/r/eventedit?" \
           f"text={urllib.parse.quote(event_name)}&" \
           f"dates={formatted_time}/{formatted_time}&details={urllib.parse.quote(description)}&" \
           f"color=6"
    return link


def get_human_timedelta(time: str) -> str:
    dt_obj = get_dt_obj_from_string(time)
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


def get_human_time(time: str) -> str:
    dt_obj = get_dt_obj_from_string(time)
    locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
    formatted_date = dt_obj.strftime("%a, %d %B в %H:%M")
    return formatted_date


def timestamp_func(a: dict) -> float:
    time = a["time"].replace('GMT+3', '+0300')
    locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
    a_timestamp = dt.datetime.strptime(time, "%d %b %Y %H:%M:%S %z").timestamp()
    return a_timestamp  # 29 Oct 2024 23:59:59 GMT+3


def relevant_filter_func(d: dict) -> float:
    dt_obj = get_dt_obj_from_string(d["time"])
    if dt_obj < dt.datetime.now(dt_obj.tzinfo):
        return False
    return True


def deadlines_filter_func(d: dict) -> float:
    if "[консультация]" in d["name"].lower():  # TODO: [тест]
        return False
    return True


def get_message_text() -> str:
    try:
        response = requests.get("https://m3104.nawinds.dev/api-deadlines").json()
    except Exception:
        return ""
    deadlines = response["deadlines"]

    tests = list(filter(lambda t: not deadlines_filter_func(t) and relevant_filter_func(t), deadlines))
    deadlines = list(filter(lambda d: deadlines_filter_func(d) and relevant_filter_func(d), deadlines))

    text = f"🧑‍💻 <b>Расписание экзаменов</b> (<i>Обновлено в {get_current_time()} 🔄</i>):\n\n"   # TODO: дедлайны
    tests = sorted(tests, key=timestamp_func)
    deadlines = sorted(deadlines, key=timestamp_func)

    if len(deadlines) == 0:
        text += "Дедлайнов нет)\n\n"

    for i in range(len(deadlines)):
        no = i + 1
        if no < 11:
            no = NUMBER_EMOJIS[no] + " "
        else:
            no += ". "
        text += str(no) + "<b>" + deadlines[i]["name"]
        text += "</b> — "
        text += get_human_timedelta(deadlines[i]["time"])
        text += f"\n(<a href='{generate_link(deadlines[i]['name'], deadlines[i]['time'])}'>"
        text += get_human_time(deadlines[i]["time"]) + "</a>)\n\n"

    if len(tests) > 0:
        text += f"\n👂<b>Консультации</b>:\n\n"  # TODO: тесты

        for i in range(len(tests)):
            # TODO: [тест]
            test_name = tests[i]["name"].replace("[Консультация] ", "").replace("[консультация]", "")
            no = i + 1
            if no < 11:
                no = NUMBER_EMOJIS[no] + " "
            else:
                no += ". "
            text += str(no) + "<b>" + test_name
            text += "</b> — "
            text += get_human_timedelta(tests[i]["time"])
            text += f"\n(<a href='{generate_link(test_name, tests[i]['time'])}'>"
            text += get_human_time(tests[i]["time"]) + "</a>)\n\n"

    text += f"\n🆕 <a href='https://m3104.nawinds.dev/deadlines-editing-instructions/'>" \
            f"Добавить дедлайн/тест</a>"
    return text


async def send_deadlines(chat_id: int) -> None:
    text = get_message_text()
    msg = await bot.send_message(chat_id, text, parse_mode="HTML", disable_web_page_preview=True)
    started_updating = dt.datetime.now()
    while dt.datetime.now() - started_updating < dt.timedelta(days=1):
        sleep(60)
        new_text = get_message_text()
        if text != new_text and new_text != "":
            await msg.edit_text(new_text, parse_mode="HTML", disable_web_page_preview=True)
            text = new_text
    await msg.delete()


async def main():
    await send_deadlines(MAIN_GROUP_ID)

    await bot.session.close()


if __name__ == '__main__':
    asyncio.run(main())
