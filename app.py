import os
import asyncio
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER (чтобы он не ругался) ---
web_app = Flask(__name__)
@web_app.route('/')
def home(): return "Бот работает!"
def run_web(): web_app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# --- НАСТРОЙКИ БОТА ---
WAIT_USERNAME, SELECT_MODE, SELECT_MAP, SEARCHING = range(4)

MODES = {
    "Окна": ["Sandstone", "Rust", "Province"],
    "Союзники": ["Sandstone", "Rust", "Province"],
    "Закладка бомбы": ["Rust", "Dune", "Province"],
}
search_queue = {}

async def stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите ваш игровой username (без @):")
    return WAIT_USERNAME

async def receive_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip().lstrip("@")
    context.user_data["game_username"] = username
    keyboard = [[InlineKeyboardButton(m, callback_data=f"mode_{m}")] for m in MODES]
    await update.message.reply_text(f"✅ Username: {username}\nВыберите режим:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_MODE

async def mode_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    mode = query.data.replace("mode_", "")
    context.user_data["mode"] = mode
    maps = MODES.get(mode, [])
    keyboard = [[InlineKeyboardButton(m, callback_data=f"map_{m}")] for m in maps]
    await query.edit_message_text(f"Режим: {mode}\nВыберите карту:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_MAP

async def map_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chosen_map = query.data.replace("map_", "")
    mode = context.user_data["mode"]
    game_username = context.user_data["game_username"]
    user_id = query.from_user.id
    key = (mode, chosen_map)

    if key not in search_queue: search_queue[key] = []

    ally_id = None
    for uid in search_queue[key]:
        if uid != user_id:
            ally_id = uid
            break

    if ally_id:
        search_queue[key].remove(ally_id)
        if user_id in search_queue[key]: search_queue[key].remove(user_id)
        try:
            ally_user = await context.bot.get_chat(ally_id)
            ally_username = ally_user.username or f"id:{ally_id}"
        except Exception:
            ally_username = f"id:{ally_id}"

        await query.edit_message_text(f"✅ Союзник найден!\nРежим: {mode} | Карта: {chosen_map}\nСоюзник: @{ally_username}")
        try: await context.bot.send_message(ally_id, f"✅ Союзник найден!\nРежим: {mode} | Карта: {chosen_map}\nСоюзник: @{query.from_user.username or game_username}")
        except Exception: pass
        return ConversationHandler.END
    else:
        search_queue[key].append(user_id)
        await query.edit_message_text(f"⏳ Поиск... Режим: {mode} | Карта: {chosen_map}\nЧерез 15 минут отменится.")
        context.job_queue.run_once(timeout_cancel, when=15*60, chat_id=user_id, name=f"timeout_{user_id}", data={"key": key, "user_id": user_id})
        return SEARCHING

async def timeout_cancel(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    key = job.data["key"]
    user_id = job.data["user_id"]
    if key in search_queue and user_id in search_queue[key]:
        search_queue[key].remove(user_id)
        await context.bot.send_message(user_id, "⏰ 15 минут прошло, союзник не найден. Поиск отменён.")

if __name__ == '__main__':
    Thread(target=run_web).start()
    # Токен берется из настроек Render!
    token = os.environ.get("TELEGRAM_TOKEN")
    app = Application.builder().token(token).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("stars", stars)],
        states={
            WAIT_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_username)],
            SELECT_MODE: [CallbackQueryHandler(mode_chosen, pattern="^mode_")],
            SELECT_MAP: [CallbackQueryHandler(map_chosen, pattern="^map_")],
        },
        fallbacks=[]
    )
    app.add_handler(conv_handler)
    print("Бот запущен...")
    app.run_polling()
