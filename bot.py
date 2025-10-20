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

    # تحديد إعدادات yt-dlp بناءً على الاختيار
    ydl_opts = {}
    output_path = ""
    try:
        if chosen_format == 'audio_mp3':
            output_path = "final_audio.mp3"
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_path,
                'postprocessors': [{ 'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192', }],
                'quiet': False,
                **cookie_opts
            }
        
        else: # (طلبات الفيديو)
            output_path = "final_video.mp4"
            
            if chosen_format == 'v_1080':
                format_string = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]'
            elif chosen_format == 'v_720':
                format_string = 'bestvideo[height<=720]+bestaudio/best[height<=720]'
            else: # (لـ 'v_best' الخاص بتيك توك/تويتر)
                format_string = 'bestvideo+bestaudio/best'

            ydl_opts = {
                'format': format_string,
                'outtmpl': output_path, 
                'quiet': False, 
                'merge_output_format': 'mp4', 
                **cookie_opts
            }

        # --- بدء التحميل ---
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        time.sleep(2) 

        # --- فحص الملف بعد التحميل ---
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            file_size = os.path.getsize(output_path)
            
            if file_size < MAX_FILE_SIZE:
                # --- الحل 1: إرسال الملف (أقل من 50 ميجا) ---
                caption = "تفضل الملف الخاص بك! 🥳"
                if chosen_format == 'audio_mp3':
                    await reply_target.reply_audio(audio=open(output_path, 'rb'), caption=caption)
                else:
                    await reply_target.reply_video(video=open(output_path, 'rb'), caption=caption)
                
                # --- !! هذا هو الإصلاح (Goal 2) !! ---
                await send_log(f"✅ **Sent File ({chosen_format})**\n{user_info}\nLink: `{url}`", context)
            
            else:
                # --- الحل 2: إرسال الرابط (أكبر من 50 ميجا) ---
                file_size_mb = file_size // 1024 // 1024
                await reply_target.reply_text(
                    f"عذراً، الملف كبير جداً ({file_size_mb} MB). 😅\n"
                    "جاري جلب رابط تحميل مباشر (بجودة 720p كحد أقصى)..."
                )
                
                link_opts = {
                    'format': 'best[ext=mp4][height<=720]/best[height<=720]',
                    'quiet': True,
                    **cookie_opts
                }
                with yt_dlp.YoutubeDL(link_opts) as ydl_link:
                    info = ydl_link.extract_info(url, download=False)
                    direct_link = info.get('url') 
                    if direct_link:
                        await reply_target.reply_text(f"🔗 تفضل الرابط المباشر (صالح لبضع دقائق فقط):\n\n`{direct_link}`", parse_mode='Markdown')
                        # --- !! هذا هو الإصلاح (Goal 3) !! ---
                        await send_log(f"✅ **Sent Link (Fallback)**\n{user_info}\nLink: `{url}`", context)
                    else:
                        await reply_target.reply_text("عذراً، فشلت في جلب الرابط المباشر. 😕")

        else:
            await reply_target.reply_text("عذراً، لم أستطع تحميل الملف (الملف فارغ بعد الانتظار). 😕")
            # --- !! هذا هو الإصلاح (Goal 4) !! ---
            await send_log(f"❌ **Failed (Empty File)**\n{user_info}\nLink: `{url}`", context)

    except Exception as e:
        print(f"حدث خطأ: {e}")
        await reply_target.reply_text(
            "عذراً، حدث خطأ. 🚫\n"
            "تأكد أن الرابط عام وليس خاصاً."
        )
        # --- !! هذا هو الإصلاح (Goal 5) !! ---
        await send_log(f"🚫 **Error**\n{user_info}\nLink: `{url}`\nError: `{e}`", context)
        
    finally:
        cleanup_file(output_path) 
        cleanup_file(cookie_file_path)
        context.user_data.clear() 

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
