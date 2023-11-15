import os
import requests
import sys
import time
import telegram
import logging
import exceptions

from dotenv import load_dotenv
from logging import StreamHandler, Formatter
from http import HTTPStatus

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


logging.basicConfig(
    level=logging.DEBUG,
    filename='program.log',
    format='%(asctime)s, %(levelname)s, %(message)s, %(name)s'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = StreamHandler(stream=sys.stdout)
handler.setFormatter(Formatter(fmt='%(asctime)s, [%(levelname)s] %(message)s'))
logger.addHandler(handler)


def check_tokens():
    """Проверка доступности переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Сообщение отправлено в Telegram чат: {}'.format(message))
    except telegram.error.TelegramError:
        logger.error('Сообщение не отправленно в Telegram чат!')
        raise AssertionError(
            'При отправке сообщения в Telegram чат возникла ошибка.'
        )


def get_api_answer(timestamp):
    """Получить статус домашней работы."""
    try:
        homework_statuses = requests.get(url=ENDPOINT,
                                         headers=HEADERS,
                                         params={'from_date': timestamp})
        response = homework_statuses.json()
    except Exception as error:
        logger.error(error, exc_info=True)
        raise exceptions.APIConnectError('Нет доступа к API')
    if homework_statuses.status_code != HTTPStatus.OK:
        raise exceptions.HttpStatusError(
            f'Некорректный статус ответа: {homework_statuses.status_code}')
    return response


def check_response(response):
    """Проверяет ответ API на соответствие типу данных."""
    if not isinstance(response, dict):
        raise TypeError('Ответ API-сервера содержит некорректный тип данных.')
    if 'homeworks' not in response:
        raise KeyError('Ответ от API не содержит ключ "homeworks".')
    if 'current_date' not in response:
        raise KeyError('Ответ от API не содержит ключ "current_date".')
    homework = response['homeworks']
    if not isinstance(homework, list):
        raise TypeError('Ответ API-сервера содержит некорректный тип данных.')
    logger.debug('Ответ API-сервера корректный.')
    return homework


def parse_status(homework):
    """Извлечение данных о конкретной домашней работе, статус этой работы"""
    try:
        homework_name = homework['homework_name']
        logger.debug(f'Извлекаем название работы: {homework_name}')
    except KeyError:
        raise KeyError('В словаре нет ключа "homework_name"')
    try:
        homework_status = homework['status']
        logger.debug(f'Извлекаем статус работы: {homework_status}')
    except KeyError:
        raise KeyError('В словаре нет ключа "status"')
    if homework_status not in HOMEWORK_VERDICTS:
        raise exceptions.StatusWorkException(
            'Недопустимый статус домашней работы'
        )
    verdict = HOMEWORK_VERDICTS[homework_status]
    logger.debug(f'Информации о домашней работе обработана: {verdict}')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_message = ''
    homework_message_sent = False

    if not check_tokens():
        logger.critical('Отсутствует переменная окружения')
        sys.exit('Отсутствует переменная окружения, завершение программы')

    while True:
        try:
            response = get_api_answer(timestamp)
            logger.debug('Выполнение "get_api_answer" проверка статуса работы')
            homeworks = check_response(response)
            logger.debug('Выполнение "check_response"'
                         ' Проверяет ответ API на соответствие типу данных')
            if len(homeworks) == 0 and not homework_message_sent:
                homework_message_sent = True
                logging.debug('Домашних работ нет.')
                send_message(bot, 'Домашних работ на проверку нет.')
                break
            for homework in homeworks:
                message = parse_status(homework)
                logger.debug('Выполнение "parse_status" извлечение данных'
                             'о конкретной домашней работе')
                if message:
                    last_message = message
                    send_message(bot, message)
                    logger.debug('Выполнение "send_message"'
                                 'отправка сообщение в Telegram')
                else:
                    message = 'Отсутствие новых статусов'
                    last_message = message
                    send_message(bot, message)
                    logger.debug('Отсутствие новых статусов')

        except Exception as error:
            if last_message != message:
                logger.error('Бот не смог отправить сообщение')
                message = f'Сбой в работе программы: {error}'
                send_message(bot, message)

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
