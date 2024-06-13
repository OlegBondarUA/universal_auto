from telegram import KeyboardButton

from app.models import Driver
from auto_bot.handlers.status.static_text import CORRECT_AUTO, NOT_CORRECT_AUTO, CORRECT_CHOICE, NOT_CORRECT_CHOICE

status_buttons = [
    [KeyboardButton(Driver.ACTIVE)],
    [KeyboardButton(Driver.OFFLINE)]
]


choose_auto_keyboard = [KeyboardButton(f'{CORRECT_AUTO}'), KeyboardButton(f'{NOT_CORRECT_AUTO}')]
correct_keyboard = [KeyboardButton(f'{CORRECT_CHOICE}'),
                    KeyboardButton(f'{NOT_CORRECT_CHOICE}')]
