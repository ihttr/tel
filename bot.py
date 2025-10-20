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

# (دالة /start)
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

# (دالة /help)
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "فقط أرسل رابط فيديو (تيك توك)، (يوتيوب) أو (تويتر/X) 🔗"
    )

# دالة مساعدة لحذف الملف
def cleanup_file(path):
    if os.path.exists(path):
        os.remove(path)

# -----------------------------------------------------------------
# ------------------!! بداية المنطق الجديد !!-----------------------
# -----------------------------------------------------------------

# (المرحلة 1: عند إرسال رابط يوتيوب)
async def youtube_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يسأل المستخدم عن الصيغة المطلوبة (فيديو أم صوت)"""
    message_text = update.message.text
    context.user_data['url'] = message_text # تخزين الرابط مؤقتاً
    
    # --- !! تم تغيير الأزرار هنا !! ---
    keyboard = [
        [InlineKeyboardButton("🎬 1080p (أعلى جودة)", callback_data='v_1080')],
        [InlineKeyboardButton("🎬 720p (جودة عالية)", callback_data='v_720')],
        [InlineKeyboardButton("🎵 صوت (MP3)", callback_data='audio_mp3')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text('اختر الجودة المطلوبة:', reply_markup=reply_markup)
    return CHOOSE_FORMAT # الانتقال للمرحلة التالية (انتظار الضغط)

# (المرحلة 2: عند الضغط على زر الصيغة)
async def format_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() 
    
    chosen_format = query.data # ('v_1080', 'v_720', or 'audio_mp3')
    context.user_data['format'] = chosen_format
    
    await query.edit_message_text(text=f"تم اختيار {chosen_format}. ⏳ جاري التحميل...")
    
    await process_download(update, context)
    return ConversationHandler.END 

# (المرحلة 1: عند إرسال رابط تيك توك أو تويتر)
async def other_links_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['url'] = update.message.text
    context.user_data['format'] = 'v_best' # (أفضل جودة متاحة لتيك توك/تويتر)
    
    await update.message.reply_text("...⏳ جاري تحميل الفيديو (بأعلى جودة)، يرجى الانتظار...")
    
    await process_download(update, context)
    return ConversationHandler.END 

# (دالة التحميل الرئيسية الموحدة)
async def process_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = context.user_data.get('url')
    chosen_format = context.user_data.get('format')
    user = update.effective_user
    
    reply_target = update.message or update.callback_query.message

    if not url or not chosen_format:
        await reply_target.reply_text("حدث خطأ، يرجى إعادة إرسال الرابط.")
        return

    # تحديد إعدادات الكوكيز
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
    except Exception as e:
        print(f"Error writing cookie file: {e}")

    # تحديد إعدادات yt-dlp بناءً على الاختيار
    ydl_opts = {}
    output_path = ""
    try:
        if chosen_format == 'audio_mp3':
            base_name = "final_audio"
            output_path = f"{base_name}.mp3"
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': base_name,
                'postprocessors': [{ 'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192', }],
                'quiet': False,
                **cookie_opts
            }
        
        else: # (طلبات الفيديو)
            base_name = "final_video"
            output_path = f"{base_name}.mp4"
            
            # --- !! منطق اختيار الجودة !! ---
            if chosen_format == 'v_1080':
                format_string = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]'
            elif chosen_format == 'v_720':
                format_string = 'bestvideo[height<=720]+bestaudio/best[height<=720]'
            else: # (لـ 'v_best' الخاص بتيك توك/تويتر)
                format_string = 'bestvideo+bestaudio/best'

            ydl_opts = {
                'format': format_string,
                'outtmpl': base_name, 
                'quiet': False, 
                'merge_output_format': 'mp4', 
                **cookie_opts
            }

        # --- بدء التحميل ---
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        time.sleep(2) # انتظار لضمان إغلاق الملف

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
                
                await send_log(f"✅ **Sent File ({chosen_format})**\nUser: {user.first_name}\nLink: `{url}`", context)
            
            else:
                # --- الحل 2: إرسال الرابط (أكبر من 50 ميجا) ---
                file_size_mb = file_size // 1024 // 1024
                await reply_target.reply_text(
                    f"عذراً، الملف كبير جداً ({file_size_mb} MB). 😅\n"
                    "جاري جلب رابط تحميل مباشر (بجودة 720p كحد أقصى)..."
                )
                
                # جلب الرابط المباشر (بجودة 720p كخيار آمن ومضمون)
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
                        await send_log(f"✅ **Sent Link (Fallback)**\nUser: {user.first_name}\nLink: `{url}`", context)
                    else:
                        await reply_target.reply_text("عذراً، فشلت في جلب الرابط المباشر. 😕")

        else:
            await reply_target.reply_text("عذراً، لم أستطع تحميل الملف (الملف فارغ بعد الانتظار). 😕")
            await send_log(f"❌ **Failed (Empty File)**\nLink: {url}", context)

    except Exception as e:
        print(f"حدث خطأ: {e}")
        await reply_target.reply_text(
            "عذراً، حدث خطأ. 🚫\n"
            "تأكد أن الرابط عام وليس خاصاً."
        )
        await send_log(f"🚫 **Error**\nLink: `{url}`\nError: `{e}`", context)
        
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
    print("🤖 البوت قيد التشغيل (بإصدار v4 - اختيار الجودة)...")
    
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
