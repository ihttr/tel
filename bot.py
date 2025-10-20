import os
import yt_dlp
import time
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    TypeHandler,
    ApplicationHandlerStop,
    ConversationHandler,
    CallbackQueryHandler,
)

# --- قراءة المتغيرات من الخادم ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
APP_URL = os.environ.get("RENDER_EXTERNAL_URL")
LOG_CHANNEL_ID = os.environ.get("LOG_CHANNEL_ID")
BANNED_IDS_STR = os.environ.get("BANNED_IDS", "")
BANNED_LIST = BANNED_IDS_STR.split(',')
YOUTUBE_COOKIES_TEXT = os.environ.get("YOUTUBE_COOKIES")
TWITTER_COOKIES_TEXT = os.environ.get("TWITTER_COOKIES") 
TIKTOK_COOKIES_TEXT = os.environ.get("TIKTOK_COOKIES")
MAX_FILE_SIZE = 48 * 1024 * 1024 

# --- تعريف "حالات" المحادثة ---
(CHOOSE_FORMAT, HANDLE_DOWNLOAD) = range(2)

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

# (دوال /start و /help - كما هي)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_html(
        rf"أهلاً {user.mention_html()}! 👋",
    )
    await update.message.reply_text(
        "أرسل لي أي رابط فيديو من (تيك توك)، (يوتيوب) أو (تويتر/X) وسأقوم بإرساله لك. 🎬"
    )
    user_info = f"User: {user.first_name} (@{user.username}, ID: {user.id})"
    await send_log(f"🚀 **Bot Started**\n{user_info}", context)
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "فقط أرسل رابط فيديو (تيك توك)، (يوتيوب) أو (تويتر/X) 🔗"
    )

# دالة مساعدة لحذف الملف
def cleanup_file(path):
    if os.path.exists(path):
        os.remove(path)

# (المرحلة 1: عند إرسال رابط يوتيوب)
async def youtube_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text
    context.user_data['url'] = message_text 
    
    keyboard = [
        [InlineKeyboardButton("🎬 1080p (أعلى جودة)", callback_data='v_1080')],
        [InlineKeyboardButton("🎬 720p (جودة عالية)", callback_data='v_720')],
        [InlineKeyboardButton("🎵 صوت (MP3)", callback_data='audio_mp3')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text('اختر الجودة المطلوبة:', reply_markup=reply_markup)
    return CHOOSE_FORMAT 

# (المرحلة 2: عند الضغط على زر الصيغة)
async def format_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() 
    
    chosen_format = query.data 
    context.user_data['format'] = chosen_format
    
    await query.edit_message_text(text=f"تم اختيار {chosen_format}. ⏳ جاري التحميل...")
    
    await process_download(update, context)
    return ConversationHandler.END 

# (المرحلة 1: عند إرسال رابط تيك توك أو تويتر)
async def other_links_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['url'] = update.message.text
    context.user_data['format'] = 'v_best' # (أفضل جودة متاحة)
    
    await update.message.reply_text("...⏳ جاري تحميل الفيديو (بأعلى جودة)، يرجى الانتظار...")
    
    await process_download(update, context)
    return ConversationHandler.END 

# (دالة التحميل الرئيسية الموحدة)
async def process_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = context.user_data.get('url')
    chosen_format = context.user_data.get('format')
    user = update.effective_user
    
    reply_target = update.message or update.callback_query.message
    
    # --- !! هذا هو الإصلاح (Goal 1) !! ---
    # (تعريف معلومات المستخدم لإرسالها للسجل)
    user_info = f"User: {user.first_name} (@{user.username}, ID: {user.id})"
    # --- !! نهاية الإصلاح !! ---

    if not url or not chosen_format:
        await reply_target.reply_text("حدث خطأ، يرجى إعادة إرسال الرابط.")
        return

    # --- الكود الذكي لاختيار الكوكيز ---
    cookie_file_path = 'cookies.txt'
    cookie_opts = {}
    cleanup_file(cookie_file_path)
    try:
        if ("youtube.com" in url or "youtu.be" in url) and YOUTUBE_COOKIES_TEXT:
            with open(cookie_file_path, 'w') as f: f.write(YOUTUBE_COOKIES_TEXT)
            cookie_opts = {'cookiefile': cookie_file_path}
        elif ("twitter.com" in url or "x.com" in url) and TWITTER_COOKIES_TEXT:
            with open(cookie_file_path, 'w') as f: f.write(TWITTER_COOKIES_TEXT)
            cookie_opts = {'cookiefile': cookie_file_path}
        elif ("tiktok.com" in url) and TIKTOK_COOKIES_TEXT: 
            with open(cookie_file_path, 'w') as f: f.write(TIKTOK_COOKIES_TEXT)
            cookie_opts = {'cookiefile': cookie_file_path}
            
    except Exception as e:
        print(f"Error writing cookie file: {e}")

try:
            ydl_opts_best = {
                'format': 'bestvideo+bestaudio/best',
                'outtmpl': video_base_name, 
                'quiet': False, 
                'merge_output_format': 'mp4', 
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
                            caption="تفضل الفيديو الخاص بك (بأعلى جودة)! 🥳"
                        )
                    await send_log(f"✅ **New Download (HQ)**\nUser: {user.first_name} (@{user.username}, ID: {user.id})\nLink: `{message_text}`", context)
                
                else:
                    await update.message.reply_text(
                        f"عذراً، الفيديو كبير جداً ({file_size // 1024 // 1024} MB). 😅\n"
                        "جاري محاولة تحميل نسخة أصغر حجماً (< 50MB)..."
                    )
                    cleanup_file(video_path)
                    
                    ydl_opts_small = {
                        'format': 'best[filesize<48M]/bestvideo[filesize<48M]+bestaudio[filesize<48M]',
                        'outtmpl': video_base_name, 
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
                        await send_log(f"❌ **Failed (Too Large)**\nUser: {user.first_name}, ID: {user.id}\nLink: `{message_text}`", context)

            else:
                await update.message.reply_text("عذراً، لم أستطع تحميل الفيديو (الملف فارغ بعد الانتظار). 😕")
                await send_log(f"❌ **Failed (Empty File)**, ID: {user.id}\nLink: {message_text}", context)

        except Exception as e:
            print(f"حدث خطأ: {e}")
            await update.message.reply_text("عذراً، حدث خطأ. 🚫\nتأكد أن الرابط عام وليس خاصاً.")
            await send_log(f"🚫 **Error**, ID: {user.id}\nLink: `{message_text}`\nError: `{e}`", context)
            
        finally:
            cleanup_file(video_path) 
            cleanup_file(cookie_file_path)
            
    else:
        # (إذا لم تكن رسالة صالحة أو زر)
        await update.message.reply_text(
            "لم أفهم الطلب. 😕\n"
            "الرجاء إرسال رابط (تيك توك)، (يوتيوب) أو (تويتر/X) صحيح. 🔗"
        )

# (دالة لإلغاء المحادثة)
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('تم إلغاء الأمر. أرسل رابطاً جديداً.')
    return ConversationHandler.END


def main():
    """الدالة الرئيسية لتشغيل البوت."""
    print("🤖 البوت قيد التشغيل (بإصدار v7 - إصلاح السجلات)...")
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(TypeHandler(Update, check_ban_status), group=-1)
    
    # --- معالج المحادثة لليوتيوب ---
    youtube_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'(youtube\.com|youtu\.be)'), youtube_handler)],
        states={
            CHOOSE_FORMAT: [CallbackQueryHandler(format_choice)]
        },
        fallbacks=[CommandHandler("start", start), MessageHandler(filters.TEXT, cancel)]
    )
    application.add_handler(youtube_conv_handler)
    
    # --- المعالج المنفصل لتيك توك وتويتر ---
    other_links_filter = filters.Regex(r'(tiktok\.com|twitter\.com|x\.com)')
    application.add_handler(MessageHandler(other_links_filter, other_links_handler))
    
    # الأوامر العادية
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # (هذا المعالج للرد على أي رسالة ليست رابطاً صالحاً)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~other_links_filter & ~filters.Regex(r'(youtube\.com|youtu\.be)'),
        help_command 
    ))

    # --- تشغيل Webhook ---
    PORT = int(os.environ.get("PORT", 8443))
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{APP_URL}/{TOKEN}"
    )

if __name__ == "__main__":
    main()

