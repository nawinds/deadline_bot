import datetime as dt
import locale
import logging
import os
import re
import time
import urllib.parse
import sys

import requests

# Modify the links and data below
DEADLINES_URL = "https://m3204.nawinds.dev/DEADLINES.json"
ADD_DEADLINE_LINK = "https://m3204.nawinds.dev/deadlines-editing-instructions/"
BOT_NAME = "Дединсайдер M3204"
BOT_USERNAME = "m3104_deadliner_bot"

# Environment variables that should be available:
API_URL = 'https://api.telegram.org/bot'
TOKEN = os.getenv("TOKEN")
MAIN_GROUP_ID = int(os.getenv("MAIN_GROUP_ID") or '0')
EDIT_MESSAGE_ID = int(os.getenv("EDIT_MESSAGE_ID") or '0')
ADD_CALENDAR_LINK = os.getenv("ADD_CALENDAR_LINK") != 'false'

assert TOKEN, "Missing token!"
assert MAIN_GROUP_ID, "Missing group ID!"

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

NUMBER_EMOJIS = ['0.', '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']


class TelegramException(Exception):
    def __init__(self, *, error_code: int, description: str, **_):
        super().__init__(f'Error {error_code}: {description}')
        self.error_code = error_code
        self.description = description


def telegram_request(method: str, args: dict):
    try:
        data = requests.post(API_URL + f'{TOKEN}/{method}', json=args, timeout=30).json()
        if not data['ok']:
            raise TelegramException(**data)
        return data
    except requests.exceptions.RequestException as e:
        logging.error(f"Network error in {method}: {e}")
        raise


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
    try:
        locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
    except locale.Error:
        locale.setlocale(locale.LC_TIME, 'C')
    return dt.datetime.strptime(time, "%d %b %Y %H:%M:%S %z")


def generate_link(event_name: str, event_time: str) -> str:
    dt_obj = get_dt_obj_from_string(event_time)
    formatted_time = dt_obj.strftime("%Y%m%dT%H%M%S%z")
    description = f"Дедлайн добавлен ботом {BOT_NAME} (https://t.me/{BOT_USERNAME})"
    link = f"https://calendar.google.com/calendar/u/0/r/eventedit?" \
           f"text={urllib.parse.quote(event_name)}&" \
           f"dates={formatted_time}/{formatted_time}"
    return link


def get_human_timedelta(time: str) -> str:
    dt_obj = get_dt_obj_from_string(time)
    dt_now = dt.datetime.now(dt_obj.tzinfo)
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
    try:
        locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
    except locale.Error:
        locale.setlocale(locale.LC_TIME, 'C')
    formatted_date = dt_obj.strftime("%a, %d %B в %H:%M")
    return formatted_date


def timestamp_func(a: dict) -> float:
    time = a["time"].replace('GMT+3', '+0300')
    try:
        locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
    except locale.Error:
        locale.setlocale(locale.LC_TIME, 'C')
    a_timestamp = dt.datetime.strptime(time, "%d %b %Y %H:%M:%S %z").timestamp()
    return a_timestamp


def relevant_filter_func(d: dict) -> bool:
    dt_obj = get_dt_obj_from_string(d["time"])
    return not dt_obj < dt.datetime.now(dt_obj.tzinfo)


def deadline_type_filter_func(d: dict, dtype: str = '') -> bool:
    if not dtype:
        return not re.match(r'^\[.*\]', d['name'])

    return f"[{dtype.lower()}]" in d["name"].lower()


def get_message_text() -> str:
    try:
        response = requests.get(DEADLINES_URL, timeout=30).json()
    except Exception as e:
        logging.error(f"Failed to fetch deadlines: {e}")
        return ""

    all_deadlines = response.get("deadlines", [])

    types = [
        ('', ''),  # deadlines
        ('🧑‍💻 Тесты', 'тест'),
        ('🛡 Защиты', 'защита'),
        ('🎓 Лекции', 'лекция'),
        ('🤓 Экзамены', 'экзамен'),
        ('👞 Консультации', 'консультация'),
    ]

    assignments = []
    for x in types:
        filtered = list(filter(lambda t: deadline_type_filter_func(t, x[1]) and relevant_filter_func(t), all_deadlines))
        assignments.append((sorted(filtered, key=lambda z: timestamp_func(z)), x[0], x[1]))

    text = f"🔥️️ <b>Дедлайны</b> (<i>Обновлено в {get_current_time()} 🔄</i>):\n\n"

    if len(assignments[0][0]) == 0:
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
    # Проверяем, есть ли EDIT_MESSAGE_ID
    if EDIT_MESSAGE_ID:
        # Режим обновления существующего сообщения
        text = get_message_text()
        if not text:
            logging.error("Failed to get initial message text")
            return

        try:
            edit_message(EDIT_MESSAGE_ID, text)
            logging.info(f"Message updated successfully. Msg id: {EDIT_MESSAGE_ID}")
        except TelegramException as e:
            logging.error(f"Failed to update message: {e}")
            return
    else:
        # Режим создания нового сообщения (работает 24 часа)
        text = get_message_text()
        if not text:
            logging.error("Failed to get initial message text")
            return

        msg_id = send_message(text)
        logging.info(f"New message sent. Msg id: {msg_id}")

        started_updating = dt.datetime.now()

        # Цикл обновления в течение 24 часов
        while dt.datetime.now() - started_updating < dt.timedelta(days=1):
            time.sleep(60)
            try:
                new_text = get_message_text()
                if new_text and text != new_text:
                    edit_message(msg_id, new_text)
                    text = new_text
                    logging.info(f"Message updated. Msg id: {msg_id}")
                else:
                    logging.debug(f"Message update skipped (no changes). Msg id: {msg_id}")
            except TelegramException as e:
                if e.error_code == 400:  # Message not found (удалено)
                    logging.warning(f"Message {msg_id} was deleted, exiting")
                    break
                elif e.error_code == 429:  # Too Many Requests
                    logging.warning(f"Rate limited, waiting 60s")
                    time.sleep(60)
                else:
                    logging.error(f"Error updating message: {e}")
                    time.sleep(60)
            except Exception as e:
                logging.error(f"Unexpected error: {e}")
                time.sleep(60)

        # Удаляем сообщение после 24 часов
        try:
            delete_message(msg_id)
            logging.info(f"Message deleted after 24 hours. Msg id: {msg_id}")
        except Exception as e:
            logging.error(f"Failed to delete message: {e}")


if __name__ == '__main__':
    main()