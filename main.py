import os
import logging
import asyncio
from flask import Flask, request

import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler
)

# --- Налаштування ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
# WEBHOOK_URL - це публічна адреса вашого сервісу на Render
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')

if not all([TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, WEBHOOK_URL]):
    raise ValueError("ПОМИЛКА: Один або декілька ключів (Telegram, Gemini, Webhook URL) не знайдено.")

genai.configure(api_key=GEMINI_API_KEY)
# Повертаємося до найбільш стабільної моделі, яка точно працює з новими ключами
gemini_model = genai.GenerativeModel('gemini-pro')

SELECTING_PLATFORM, GETTING_TOPIC = range(2)
user_data_storage = {}

# --- Логіка Telegram-бота (залишається без змін) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton("TikTok 🎬", callback_data='TikTok'), InlineKeyboardButton("Instagram 📸", callback_data='Instagram')],
        [InlineKeyboardButton("YouTube 🎥", callback_data='YouTube'), InlineKeyboardButton("Telegram 💬", callback_data='Telegram')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Вітаю у AI Content Generator!\n\n"
        "Я допоможу створювати віральні ідеї та описи для постів.\n\n"
        "Обери платформу, з якої почнемо:",
        reply_markup=reply_markup
    )
    return SELECTING_PLATFORM

async def platform_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    platform = query.data
    user_data_storage[user_id] = {'platform': platform}
    await query.edit_message_text(
        text=f"Чудово, обрано {platform}! ✨\n\nТепер вкажи тему або нішу (наприклад: фітнес, подорожі, мотивація, крипта)."
    )
    return GETTING_TOPIC

async def generate_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    topic = update.message.text
    if user_id not in user_data_storage:
        await update.message.reply_text("Будь ласка, почніть спочатку з команди /start.")
        return ConversationHandler.END
    platform = user_data_storage[user_id]['platform']
    await update.message.reply_text("🤖 Генерую ідеї... Це може зайняти до 30 секунд.")
    try:
        prompt = (
            f"Створи 3 унікальні ідеї для контенту в соціальній мережі {platform} на тему '{topic}'. "
            f"Для кожної ідеї надай: привабливий заголовок (Ідея), короткий опис/текст для посту (Текст) "
            f"та добірку з 5-7 релевантних хештегів (Хештеги). "
            f"Відповідь надай чітко структурованою, використовуючи маркери '1️⃣', '2️⃣', '3️⃣'."
        )
        response = gemini_model.generate_content(prompt)
        final_message = f"✨ Ось твої ідеї контенту для **{platform}** на тему **{topic}**:\n\n{response.text}"
        await update.message.reply_text(final_message, parse_mode='Markdown')
        await update.message.reply_text("Щоб створити новий контент, використайте команду /new.")
    except Exception as e:
        logger.error(f"Error generating content with Gemini: {e}")
        await update.message.reply_text("😔 Виникла помилка під час генерації контенту. Спробуйте змінити запит або повторіть пізніше.")
    if user_id in user_data_storage:
        del user_data_storage[user_id]
    return ConversationHandler.END

async def new_generation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Починаємо спочатку!")
    return await start(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Діалог скасовано.")
    if update.effective_user.id in user_data_storage:
        del user_data_storage[update.effective_user.id]
    return ConversationHandler.END


# --- Налаштування Application та Flask ---
ptb_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start), CommandHandler('new', new_generation)],
    states={
        SELECTING_PLATFORM: [CallbackQueryHandler(platform_choice)],
        GETTING_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_content)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)
ptb_app.add_handler(conv_handler)

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Webhook server is running. Bot is active."

@flask_app.route(f'/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
async def telegram_webhook():
    update_data = request.get_json()
    update = Update.de_json(data=update_data, bot=ptb_app.bot)
    await ptb_app.process_update(update)
    return {'ok': True}

async def main():
    logger.info("Setting webhook...")
    await ptb_app.bot.set_webhook(url=f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}")
    logger.info("Webhook is set.")

# Запускаємо налаштування вебхука перед запуском gunicorn
if __name__ != '__main__':
    asyncio.run(main())
