import os
import sys
import time
import logging
from logging import Formatter
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
file_handler = logging.FileHandler(log_file_path)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    Formatter(fmt='%(asctime)s, [%(levelname)s],'
              '%(funcName)s:%(lineno)d, %(message)s, %(name)s')
)
logger.addHandler(file_handler)


def check_tokens():
    """Проверка доступности переменных окружения."""
    logger.info('Проводим проверку переменных окружения')
    missing_token = None
    bool_token = True
    tokens = (
        ('PRACTICUM_TOKEN', PRACTICUM_TOKEN),
        ('TELEGRAM_TOKEN', TELEGRAM_TOKEN),
        ('TELEGRAM_CHAT_ID', TELEGRAM_CHAT_ID)
    )
    for token_name, token_value in tokens:
        if not token_value or token_value != os.getenv(token_name):
            missing_token = token_name
            bool_token = False
            logger.critical(f'Переменная окружения {missing_token}'
                            f' не доступна или не верна')
            break
    if missing_token:
        raise ValueError(f'Отсутствует или не верная '
                         f'переменная окружения: {missing_token}')
    return bool_token


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    message_send = True
    logger.info(f'Сообщение: {message} подготовленно к отправке в Telegram.')
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Сообщение отправлено в Telegram чат: {}'.format(message))
    except telegram.error.TelegramError:
        message_send = False
        logger.error('Сообщение не отправленно в Telegram чат!')
    return message_send


def get_api_answer(timestamp):
    """Получить статус домашней работы."""
    api_params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': timestamp,
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
            error_message_params
            + f'Ошибка при отправке запроса к API: {error}'
        )
        raise ConnectionError(error_message)

    if homework_statuses.status_code != HTTPStatus.OK:
        status_code = homework_statuses.status_code
        error_message = (
            error_message_params
            + f'Некорректный статус ответа от API: {status_code}'
            )
        api_response = response.get('error_message')
        if api_response:
            error_message += f', Причина: {api_response}'
        raise ConnectionError(error_message)
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
    except KeyError:
        if not homework_name:
            raise KeyError('В словаре нет ключа "homework_name"')
        if not homework_name:
            raise KeyError('В словаре нет ключа "status"')
    if homework_status not in HOMEWORK_VERDICTS:
        raise ValueError('Недопустимый статус домашней работы')
    verdict = HOMEWORK_VERDICTS[homework_status]
    logger.debug(f'Информации о домашней работе обработана: {verdict}')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical('Отсутствует переменная окружения')
        sys.exit('Отсутствует переменная окружения, завершение программы')

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = 0 # int(time.time())
    last_message = ''
    homework_message_sent = False

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
            if not send_message():
                logger.critical('Ошибка. Сообщение не отправлено.')

        except Exception as error:
            if last_message != message:
                logger.error('Бот не смог отправить сообщение')
                message = f'Сбой в работе программы: {error}'
                send_message(bot, message)

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        filename='program.log',
        format='%(asctime)s, [%(levelname)s],'
               '%(funcName)s:%(lineno)d, %(message)s, %(name)s'
        )
    main()
