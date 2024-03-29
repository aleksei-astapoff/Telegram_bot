import os
import sys
import time
import logging
from logging import StreamHandler, Formatter
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv

import exceptions

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

logger = logging.getLogger(__name__)
log_file_path = os.path.abspath(__file__ + '.log')
file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
file_handler.setFormatter(
    Formatter(fmt='%(asctime)s, [%(levelname)s],'
              '%(funcName)s:%(lineno)d, %(message)s, %(name)s')
)
stdout_handler = StreamHandler(stream=sys.stdout)
stdout_handler.setLevel(logging.DEBUG)
stdout_handler.setFormatter(
    Formatter(fmt='%(asctime)s, [%(levelname)s],'
                  '%(funcName)s:%(lineno)d, %(message)s, %(name)s')
)
logger.addHandler(file_handler)
logger.addHandler(stdout_handler)
logger.setLevel(logging.DEBUG)


def check_tokens():
    """Проверка доступности переменных окружения."""
    logger.info('Проводим проверку переменных окружения')
    missing_token = None
    tokens = (
        ('PRACTICUM_TOKEN', PRACTICUM_TOKEN),
        ('TELEGRAM_TOKEN', TELEGRAM_TOKEN),
        ('TELEGRAM_CHAT_ID', TELEGRAM_CHAT_ID)
    )
    for token_name, token_value in tokens:
        if not token_value or token_value != os.getenv(token_name):
            missing_token = token_name
            logger.critical(f'Переменная окружения {missing_token}'
                            f' не доступна или не верна')
            break
    if missing_token:
        raise ValueError(f'Отсутствует или не верная '
                         f'переменная окружения: {missing_token}')


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    message_send = True
    logger.info(f'Сообщение: {message} подготовленно к отправке в Telegram.')
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'Сообщение отправлено в Telegram чат: {message}')
    except telegram.error.TelegramError:
        message_send = False
        logger.error('Сообщение не отправленно в Telegram чат!')
    return message_send


def get_api_answer(timestamp):
    """Получить статус домашней работы."""
    api_params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp},
    }
    error_message_params = (
        'Данные для запроса: url: '
        '{url} c headers: {headers} '
        'и params: {params}'.format(**api_params)
    )
    logger.info('Готовим запрос на url: {url} c headers: {headers} '
                'и params: {params}'.format(**api_params))
    try:
        homework_statuses = requests.get(**api_params)
        response = homework_statuses.json()
    except requests.exceptions.RequestException as error:
        error_message = (
            f'{error_message_params} '
            f'Ошибка при отправке запроса к API: {error}'
        )
        raise ConnectionError(error_message)

    if homework_statuses.status_code != HTTPStatus.OK:
        error_message = (
            'Некорректный статус ответа от API: {status_code}. '
            'Причина: {reason}, '
            'Текст ошибки: {error_text}'.format(**homework_statuses)
        )
        raise exceptions.InvalidResponnseCode(error_message)
    return response


def check_response(response):
    """Проверяет ответ API на соответствие типу данных."""
    if not isinstance(response, dict):
        raise TypeError('Ответ API-сервера содержит некорректный тип данных.')
    if 'homeworks' not in response:
        raise exceptions.EmptyResponnseFopmAPI(
            'Ответ от API не содержит ключ "homeworks".'
        )
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError('Ответ API-сервера содержит некорректный тип данных.')
    logger.debug('Ответ API-сервера корректный.')
    return homeworks


def parse_status(homework):
    """Извлечение данных о конкретной домашней работе, статус этой работы."""
    try:
        homework_name = homework['homework_name']
        logger.debug(f'Извлекаем название работы: {homework_name}')
        homework_status = homework['status']
        logger.debug(f'Извлекаем статус работы: {homework_status}')
    except KeyError as error:
        raise KeyError(f'В словаре нет ключа {error}')
    if homework_status not in HOMEWORK_VERDICTS:
        raise ValueError('Недопустимый статус домашней работы')
    verdict = HOMEWORK_VERDICTS[homework_status]
    logger.debug(f'Информации о домашней работе обработана: {verdict}')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()
    logger.critical('Отсутствует переменная окружения')
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = 0
    last_message = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            logger.debug('Выполнение "get_api_answer" проверка статуса работы')
            homeworks = check_response(response)
            logger.debug('Выполнение "check_response"'
                         'Проверяет ответ API на соответствие типу данных')
            if homeworks:
                message = parse_status(homeworks[0])
                logger.debug('Выполнение "parse_status" извлечение данных'
                             'о конкретной домашней работе')
            else:
                message = 'Нет новых статусов'
            if message != last_message:
                if send_message(bot, message):
                    last_message = message
                    timestamp = response.get('current_date', timestamp)
            else:
                logger.debug(f'Текущее сообщение: {message}')
        except exceptions.EmptyResponnseFopmAPI:
            logger.error('Ответ от API не содержит ключи')

        except Exception as error:
            logger.exception('Ошибка при выполнении кода:', exc_info=True)
            message = f'Сбой в работе программы: {error}'
            logger.error('Бот не смог отправить сообщение')
            if message != last_message:
                send_message(bot, message)
                last_message = message

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s, [%(levelname)s],'
               '%(funcName)s:%(lineno)d, %(message)s, %(name)s',
    )
    main()
