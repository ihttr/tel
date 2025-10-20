import os
import yt_dlp
import time
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    TypeHandler,
    ApplicationHandlerStop,
)

# --- قراءة المتغيرات من الخادم ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
APP_URL = os.environ.get("RENDER_EXTERNAL_URL")
LOG_CHANNEL_ID = os.environ.get("LOG_CHANNEL_ID")
BANNED_IDS_STR = os.environ.get("BANNED_IDS", "")
BANNED_LIST = BANNED_IDS_STR.split(',')
YOUTUBE_COOKIES_TEXT = os.environ.get("YOUTUBE_COOKIES")
TWITTER_COOKIES_TEXT = os.environ.get("TWITTER_COOKIES") 
MAX_FILE_SIZE = 1000 * 1024 * 1024

# (جدار الحماية الخاص بالحظر)
async def check_ban_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user:
        user_id = str(update.effective_user.id)
        if user_id in BANNED_LIST:
            raise ApplicationHandlerStop

# (دالة إرسال السجلات)
async def send_log(message, context: ContextTypes.DEFAULT_TYPE):
    if LOG_CHANNEL_ID:
        try:
            await context.bot.send_message(
                chat_id=LOG_CHANNEL_ID,
                text=message,
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"Error sending log to channel: {e}")

# (دالة /start)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        ["💡 كيفية الاستخدام"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_html(
        rf"أهلاً {user.mention_html()}! 👋",
        reply_markup=reply_markup
    )
    await update.message.reply_text(
        "أرسل لي أي رابط فيديو من (تيك توك)، (يوتيوب) أو (تويتر/X) وسأقوم بإرساله لك. 🎬"
    )
    user_info = f"User: {user.first_name} (@{user.username}, ID: {user.id})"
    await send_log(f"🚀 **Bot Started**\n{user_info}", context)

# (دالة /help)
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "فقط أرسل رابط فيديو (تيك توك)، (يوتيوب) أو (تويتر/X) 🔗"
    )

# (دالة الأزرار)
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "💡 كيفية الاستخدام":
        await help_command(update, context)

# دالة مساعدة لحذف الملف
def cleanup_file(path):
    if os.path.exists(path):
        os.remove(path)

# (handler) دالة لمعالجة الروابط
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text
    user = update.effective_user
    
    is_valid_link = (
        "tiktok.com" in message_text or
        "youtube.com" in message_text or
        "youtu.be" in message_text or
        "twitter.com" in message_text or
        "x.com" in message_text
    )
    
    if is_valid_link:
        
        await update.message.reply_text("...⏳ جاري تحميل الفيديو (بأعلى جودة)، يرجى الانتظار...")
        
        # --- !! التعديل هنا: المسار الكامل هو الاسم !! ---
        video_path = "final_video.mp4" 
        
        cleanup_file(video_path)
        
        cookie_file_path = 'cookies.txt'
        cookie_opts = {}
        cleanup_file(cookie_file_path)
        
        try:
            if ("youtube.com" in message_text or "youtu.be" in message_text) and YOUTUBE_COOKIES_TEXT:
                with open(cookie_file_path, 'w') as f:
                    f.write(YOUTUBE_COOKIES_TEXT)
                cookie_opts = {'cookiefile': cookie_file_path}
            elif ("twitter.com" in message_text or "x.com" in message_text) and TWITTER_COOKIES_TEXT:
                with open(cookie_file_path, 'w') as f:
                    f.write(TWITTER_COOKIES_TEXT)
                cookie_opts = {'cookiefile': cookie_file_path}
                
        except Exception as e:
            print(f"Error writing cookie file: {e}")

        try:
            ydl_opts_best = {
                'format': 'bestvideo+bestaudio/best',
                # --- !! التعديل هنا: نمرر المسار الكامل !! ---
                'outtmpl': video_path, 
                'quiet': False, 
                'merge_output_format': 'mp4', # (هذا سيضمن الدمج كـ mp4 إذا لزم الأمر)
                **cookie_opts
            }

            with yt_dlp.YoutubeDL(ydl_opts_best) as ydl:
                ydl.download([message_text])

            time.sleep(2) 

            if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                file_size = os.path.getsize(video_path)
                
                if file_size < MAX_FILE_SIZE:
                    with open(video_path, 'rb') as video_file:
                        await update.message.reply_video(
                            video=video_file.read(),
                            caption=f"تفضل الفيديو الخاص بك (بأعلى جودة)! 🥳 \n ({file_size // 1024 // 1024} MB)"
                        )
                    await send_log(f"✅ **New Download (HQ)**\nUser: {user.first_name} (@{user.username },ID: {user.id})\nLink: `{message_text}`", context)
                
                else:
                    await update.message.reply_text(
                        f"عذراً، الفيديو كبير جداً ({file_size // 1024 // 1024} MB). 😅\n"
                        "جاري محاولة تحميل نسخة أصغر حجماً (< 50MB)..."
                    )
                    cleanup_file(video_path)
                    
                    ydl_opts_small = {
                        'format': 'best[filesize<48M]/bestvideo[filesize<48M]+bestaudio[filesize<48M]',
                        # --- !! التعديل هنا أيضاً !! ---
                        'outtmpl': video_path, 
                        'quiet': False, 
                        'merge_output_format': 'mp4', 
                        **cookie_opts
                    }
                    
                    with yt_dlp.YoutubeDL(ydl_opts_small) as ydl_small:
                        ydl_small.download([message_text])
                    
                    time.sleep(2) 

                    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                        with open(video_path, 'rb') as video_file_small:
                            await update.message.reply_video(
                                video=video_file_small.read(),
                                caption="تفضل الفيديو (نسخة مضغوطة)! 📦"
                            )
                        await send_log(f"✅ **New Download (LQ)**\nUser: {user.first_name} (@{user.username}, ID: {user.id})\nLink: `{message_text}`", context)
                    else:
                        await update.message.reply_text("عذراً، لم أتمكن من العثور على نسخة بحجم مناسب. 😕")
                        await send_log(f"❌ **Failed (Too Large)**\nUser: {user.first_name}\nLink: `{message_text}`", context)

            else:
                await update.message.reply_text("عذراً، لم أستطع تحميل الفيديو (الملف فارغ بعد الانتظار). 😕")
                await send_log(f"❌ **Failed (Empty File)**\nLink: {message_text}", context)

        except Exception as e:
            print(f"حدث خطأ: {e}")
            await update.message.reply_text("عذراً، حدث خطأ. 🚫\nتأكد أن الرابط عام وليس خاصاً.")
            await send_log(f"🚫 **Error**\nLink: `{message_text}`\nError: `{e}`", context)
            
        finally:
            cleanup_file(video_path) 
            cleanup_file(cookie_file_path)
            
    else:
        await update.message.reply_text(
            "لم أفهم الطلب. 😕\n"
            "الرجاء إرسال رابط (تيك توك)، (يوتيوب) أو (تويتر/X) صحيح. 🔗"
        )


def main():
    """الدالة الرئيسية لتشغيل البوت."""
    print("🤖 البوت قيد التشغيل (TikTok + YouTube + Twitter/X + Buttons)...")
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(TypeHandler(Update, check_ban_status), group=-1)
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^💡 كيفية الاستخدام$"), button_handler))
    
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.Regex("^💡 كيفية الاستخدام$"), 
        handle_message
    ))

    PORT = int(os.environ.get("PORT", 8443))
    
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{APP_URL}/{TOKEN}"
    )

if __name__ == "__main__":
    main()
    






