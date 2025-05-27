import datetime as dt
import locale
import logging
import os
import re
import time
import urllib.parse

import requests

# Modify the links and data below:
DEADLINES_URL = "https://m3104.nawinds.dev/DEADLINES.json"
ADD_DEADLINE_LINK = "https://m3104.nawinds.dev/deadlines-editing-instructions/"
BOT_NAME = "Дединсайдер M3104"
BOT_USERNAME = "m3104_deadliner_bot"

# Environment variables that should be available:
API_URL = 'https://api.telegram.org/bot'
TOKEN = os.getenv("TOKEN")
MAIN_GROUP_ID = int(os.getenv("MAIN_GROUP_ID") or '0')
EDIT_MESSAGE_ID = int(os.getenv("EDIT_MESSAGE_ID") or '0')
ADD_CALENDAR_LINK = os.getenv("ADD_CALENDAR_LINK") != 'false'

assert TOKEN, "Missing token!"
assert MAIN_GROUP_ID, "Missing group ID!"

logging.basicConfig(level=logging.INFO)

NUMBER_EMOJIS = ['0.', '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']


class TelegramException(Exception):
    def __init__(self, *, error_code: int, description: str, **_):
        super().__init__(f'Error {error_code}: {description}')
        self.error_code = error_code
        self.description = description


def telegram_request(method: str, args: dict):
    data = requests.post(API_URL + f'{TOKEN}/{method}', json=args).json()
    if not data['ok']:
        raise TelegramException(**data)
    return data


def send_message(text: str) -> int:
    return telegram_request('sendMessage', {
        'chat_id': MAIN_GROUP_ID,
        'parse_mode': 'HTML',
        'text': text,
        'link_preview_options': {
            'is_disabled': True
        }
    })['result']['message_id']


def edit_message(message_id: int, text: str) -> int:
    return telegram_request('editMessageText', {
        'chat_id': MAIN_GROUP_ID,
        'parse_mode': 'HTML',
        'message_id': message_id,
        'text': text,
        'link_preview_options': {
            'is_disabled': True
        }
    })['result']['message_id']


def delete_message(message_id: int) -> bool:
    return telegram_request('deleteMessage', {
        'chat_id': MAIN_GROUP_ID,
        'message_id': message_id
    })['result']


def get_current_time() -> str:
    current_time = dt.datetime.now()
    current_time_hour = current_time.hour if current_time.hour >= 10 else "0" + str(current_time.hour)
    current_time_minute = current_time.minute if current_time.minute >= 10 else "0" + str(current_time.minute)
    return f"{current_time_hour}:{current_time_minute}"


def get_dt_obj_from_string(time: str) -> dt.datetime:
    time = time.replace('GMT+3', '+0300')
    locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
    return dt.datetime.strptime(time, "%d %b %Y %H:%M:%S %z")


def generate_link(event_name: str, event_time: str) -> str:
    dt_obj = get_dt_obj_from_string(event_time)
    formatted_time = dt_obj.strftime("%Y%m%d T%H%M%S%z")
    description = f"Дедлайн добавлен ботом {BOT_NAME} (https://t.me/{BOT_USERNAME})"
    link = f"https://calendar.google.com/calendar/u/0/r/eventedit?" \
           f"text={urllib.parse.quote(event_name)}&" \
           f"dates={formatted_time}/{formatted_time}"
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


def relevant_filter_func(d: dict) -> bool:
    dt_obj = get_dt_obj_from_string(d["time"])
    return not dt_obj < dt.datetime.now(dt_obj.tzinfo)


def deadline_type_filter_func(d: dict, dtype: str = '') -> bool:
    if not dtype:
        return not re.match(r'^\[.*\]', d['name'])

    return f"[{dtype.lower()}]" in d["name"].lower()


def get_message_text() -> str:
    try:
        response = requests.get(DEADLINES_URL).json()
    except Exception as e:
        print(f"{dt.datetime.now()} Failed to fetch deadlines: {e}")
        return ""
    all_deadlines = response["deadlines"]

    types = [
        ('', ''), # deadlines
        ('🧑‍💻 Тесты', 'тест'),
        ('🎓 Лекции', 'лекция'),
        ('🛡 Защиты', 'защита'),
        ('🤓 Экзамены', 'экзамен'),
        ('👞 Консультации', 'консультация'),
    ]

    assignments = [(sorted(filter(lambda t: deadline_type_filter_func(t, x[1]) and relevant_filter_func(t), all_deadlines),
                           key=lambda z: timestamp_func(z)), x[0], x[1]) for x in types]

    text = f"🔥️️ <b>Дедлайны</b> (<i>Обновлено в {get_current_time()} 🔄</i>):\n\n"

    if len(assignments[0]) == 0:
        text += "Дедлайнов нет)\n\n"

    def add_items(items: list, category_name: str = '', replace_name: str = ''):
        if len(items) == 0:
            return

        nonlocal text
        REPLACE_PATTERN = re.compile(rf'^\[{replace_name}\] ', flags=re.IGNORECASE)

        if category_name:
            text += f"\n<b>{category_name}</b>:\n\n"

        for i, item in enumerate(items):
            no = i + 1
            if no <= 10:
                no = NUMBER_EMOJIS[no] + " "
            else:
                no = str(no) + ". "

            text += no + "<b>"

            name = re.sub(REPLACE_PATTERN, '', item['name'])
            url = item.get('url')

            if url:
                text += f"<a href='{url}'>{name}</a>"
            else:
                text += name

            text += "</b> — "
            text += get_human_timedelta(item["time"])
            if ADD_CALENDAR_LINK:
                text += f"\n(<a href='{generate_link(name, item['time'])}'>"
                text += get_human_time(item["time"]) + "</a>)\n\n"
            else:
                text += f'\n({get_human_time(item["time"])})\n\n'

    for assignment_type in assignments:
        add_items(*assignment_type)

    text += (
        f"\n🆕 <a href='{ADD_DEADLINE_LINK}'>"
        f"Добавить дедлайн</a>"
    )

    return text


def main() -> None:
    text = get_message_text()

    if EDIT_MESSAGE_ID:
        msg_id = edit_message(EDIT_MESSAGE_ID, text)
    else:
        msg_id = send_message(text)
    started_updating = dt.datetime.now()
    print(dt.datetime.now(), "Message sent. Msg id:", msg_id)

    condition = (lambda: True) if EDIT_MESSAGE_ID else (lambda: dt.datetime.now() - started_updating < dt.timedelta(days=1))
    while condition():
        time.sleep(60)
        try:
            new_text = get_message_text()
            if text != new_text and new_text != "":
                edit_message(msg_id, new_text)
                text = new_text
                print(dt.datetime.now(), "Message updated. Msg id:", msg_id)
            else:
                print(dt.datetime.now(), "Message update skipped. Msg id:", msg_id)

        except Exception as e:
            logging.warning(dt.datetime.now(),f"{dt.datetime.now()} Error updating message: {e}")
            continue

    if not EDIT_MESSAGE_ID:
        delete_message(msg_id)


if __name__ == '__main__':
    main()
