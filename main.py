import os
import shutil
from config import BOT_TOKEN
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from yt_dlp import YoutubeDL

# Шлях до робочого столу
DESKTOP_PATH = os.path.join(os.path.expanduser("~"), "Desktop")
DOWNLOAD_FOLDER = os.path.join(DESKTOP_PATH, "YouTube Bot Downloads")
LOG_FOLDER = os.path.join(DESKTOP_PATH, "YouTube Bot Logs")

# Створюємо папки, якщо їх немає
if not os.path.exists(LOG_FOLDER):
    os.makedirs(LOG_FOLDER)

# Налаштування логування
logging.basicConfig(
    filename=os.path.join(LOG_FOLDER, 'bot.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger()

# Стадії розмови
CONFIRM_CLEAN, DOWNLOAD, RENAME = range(3)

# Регулярний вираз для перевірки посилання
LINK_REGEX = r'https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w-]+'

async def start(update: Update, _):
    if os.path.exists(DOWNLOAD_FOLDER) and os.listdir(DOWNLOAD_FOLDER):
        keyboard = [
            [InlineKeyboardButton("Так", callback_data="clean_yes"),
             InlineKeyboardButton("Ні", callback_data="clean_no")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🗂️ Папка для завантажень вже існує. Очистити перед новим завантаженням?", 
            reply_markup=reply_markup
        )
        return CONFIRM_CLEAN
    else:
        os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
        await update.message.reply_text("📥 Надішли список посилань на YouTube (через пробіл або нові рядки).")
        return DOWNLOAD

async def confirm_clean(update: Update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "clean_yes":
        shutil.rmtree(DOWNLOAD_FOLDER)
        os.makedirs(DOWNLOAD_FOLDER)
        await query.edit_message_text("🧹 Папку очищено. Надішли посилання.")
    else:
        await query.edit_message_text("📥 Надішли посилання.")

    return DOWNLOAD

async def download_videos(update: Update, context):
    links = update.message.text.strip().split()
    
    yt_links = []  # Збереження лише YouTube-посилань
    non_yt_links = []  # Збереження не-YouTube-посилань
    link_order = {}  # Збереження порядкових номерів
    
    for i, link in enumerate(links, start=1):
        if re.match(LINK_REGEX, link):
            if link in link_order:
                link_order[link].append(i)
            else:
                link_order[link] = [i]
                yt_links.append(link)
        else:
            non_yt_links.append(i)  # Запам'ятовуємо порядковий номер
    
    context.user_data["link_order"] = link_order
    context.user_data["video_files"] = {}
    context.user_data["non_yt_links"] = non_yt_links
    
    await update.message.reply_text("⏳ Завантажую відео...")
    downloaded_count = 0
    failed_links = []
    
    for link in yt_links:
        try:
            with YoutubeDL({
                'format': 'bestvideo+bestaudio/best',
                'merge_output_format': 'mkv',  
                'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
                'socket_timeout': 30
            }) as ydl:
                info = ydl.extract_info(link, download=True)
                filename = os.path.basename(ydl.prepare_filename(info))
                context.user_data["video_files"][link] = filename
                downloaded_count += 1
        except Exception:
            failed_links.append(link)
    
    result_msg = f"✅ Завантажено {downloaded_count} відео."
    if failed_links:
        result_msg += f"\n❌ Не вдалося завантажити: {', '.join(failed_links)}."
    await update.message.reply_text(result_msg)
    await update.message.reply_text("📝 Введи стартову цифру для перейменування першого відео.")
    return RENAME

async def rename_videos(update: Update, context):
    try:
        start_number = int(update.message.text.strip())
        link_order = context.user_data["link_order"]
        video_files = context.user_data["video_files"]
        non_yt_links = context.user_data["non_yt_links"]
        renamed_files = []
        
        for link, filename in video_files.items():
            ext = os.path.splitext(filename)[1]
            order_numbers = "_".join(map(str, link_order[link]))
            new_name = f"{start_number}_{order_numbers}{ext}"
            os.rename(os.path.join(DOWNLOAD_FOLDER, filename), os.path.join(DOWNLOAD_FOLDER, new_name))
            renamed_files.append(new_name)
            start_number += 1
        
        if non_yt_links:
            renamed_files.append(f"Пропущені посилання: {', '.join(map(str, non_yt_links))}")
        
        await update.message.reply_text("✅ Перейменування завершено.")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❗️ Введи коректне число.")
        return RENAME

async def cancel(update: Update, _):
    await update.message.reply_text("🚫 Операцію скасовано.")
    logger.info(f"User {update.effective_user.id} canceled the operation.")
    return ConversationHandler.END

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CONFIRM_CLEAN: [CallbackQueryHandler(confirm_clean)],
            DOWNLOAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, download_videos)],
            RENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, rename_videos)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
