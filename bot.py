import os
import yt_dlp
from telegram import Update
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

# --- تحديد حجم الإرسال الأقصى (بالبايت) ---
# 50 ميجابايت، لكن نتركه 48 للآمان
MAX_FILE_SIZE = 48 * 1024 * 1024 

# -----------------------------------------------------------------
# ------------------!! جدار الحماية (Ban Check) !!------------------
# -----------------------------------------------------------------
async def check_ban_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يتحقق إذا كان المستخدم في قائمة الحظر."""
    if update.effective_user:
        user_id = str(update.effective_user.id)
        if user_id in BANNED_LIST:
            raise ApplicationHandlerStop
# -----------------------------------------------------------------

# دالة مساعدة لإرسال السجلات
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

# (handler) دالة لآمر /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_html(
        rf"أهلاً {user.mention_html()}! 👋",
        reply_markup=None
    )
    await update.message.reply_text(
        "أرسل لي أي رابط فيديو من (تيك توك) أو (يوتيوب) وسأقوم بإرساله لك. 🎬"
    )
    user_info = f"User: {user.first_name} (@{user.username}, ID: {user.id})"
    await send_log(f"🚀 **Bot Started**\n{user_info}", context)

# (handler) دالة لآمر /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "فقط أرسل رابط فيديو تيك توك أو يوتيوب 🔗"
    )

# دالة مساعدة لحذف الملف
def cleanup_file(path):
    """يحذف الملف إذا كان موجوداً"""
    if os.path.exists(path):
        os.remove(path)

# (handler) دالة لمعالجة الروابط
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text
    user = update.effective_user
    
    # --- !! التعديل الجديد: التحقق من تيك توك أو يوتيوب !! ---
    if "tiktok.com" in message_text or "youtube.com" in message_text or "youtu.be" in message_text:
        
        await update.message.reply_text("...⏳ جاري تحميل الفيديو (بأعلى جودة)، يرجى الانتظار...")
        video_path = "final_video.mp4"
        cleanup_file(video_path) # تنظيف أي ملف قديم
        
        try:
            # --- المحاولة الأولى: تحميل أعلى جودة ---
            ydl_opts_best = {
                'format': 'bestvideo+bestaudio/best',
                'outtmpl': video_path,
                'quiet': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts_best) as ydl:
                ydl.download([message_text])

            # --- التحقق من الحجم ---
            if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                file_size = os.path.getsize(video_path)
                
                if file_size < MAX_FILE_SIZE:
                    # --- 1. ناجح والحجم مناسب ---
                    with open(video_path, 'rb') as video_file:
                        await update.message.reply_video(
                            video=video_file.read(),
                            caption="تفضل الفيديو الخاص بك (بأعلى جودة)! 🥳"
                        )
                    await send_log(f"✅ **New Download (HQ)**\nUser: {user.first_name} (@{user.username})\nLink: `{message_text}`", context)
                
                else:
                    # --- 2. ناجح لكن الحجم كبير جداً ---
                    await update.message.reply_text(
                        f"عذراً، الفيديو كبير جداً ({file_size // 1024 // 1024} MB). 😅\n"
                        "جاري محاولة تحميل نسخة أصغر حجماً (< 50MB)..."
                    )
                    cleanup_file(video_path) # حذف الملف الكبير
                    
                    # --- المحاولة الثانية: تحميل نسخة أصغر ---
                    ydl_opts_small = {
                        # اطلب أفضل جودة حجمها أقل من 48 ميجا
                        'format': 'best[filesize<48M]/bestvideo[filesize<48M]+bestaudio[filesize<48M]',
                        'outtmpl': video_path,
                        'quiet': True,
                    }
                    
                    with yt_dlp.YoutubeDL(ydl_opts_small) as ydl_small:
                        ydl_small.download([message_text])
                        
                    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                        with open(video_path, 'rb') as video_file_small:
                            await update.message.reply_video(
                                video=video_file_small.read(),
                                caption="تفضل الفيديو (نسخة مضغوطة)! 📦"
                            )
                        await send_log(f"✅ **New Download (LQ)**\nUser: {user.first_name} (@{user.username})\nLink: `{message_text}`", context)
                    else:
                        await update.message.reply_text("عذراً، لم أتمكن من العثور على نسخة بحجم مناسب. 😕")
                        await send_log(f"❌ **Failed (Too Large)**\nUser: {user.first_name}\nLink: `{message_text}`", context)

            else:
                # --- فشل التحميل الأولي (ملف فارغ) ---
                await update.message.reply_text("عذراً، لم أستطع تحميل الفيديو (الملف فارغ). 😕")
                await send_log(f"❌ **Failed (Empty File)**\nLink: {message_text}", context)

        except Exception as e:
            print(f"حدث خطأ: {e}")
            await update.message.reply_text("عذراً، حدث خطأ. 🚫\nتأكد أن الرابط عام وليس خاصاً.")
            await send_log(f"🚫 **Error**\nLink: `{message_text}`\nError: `{e}`", context)
            
        finally:
            cleanup_file(video_path) # حذف الفيديو من الخادم دائماً
            
    else:
        await update.message.reply_text(
            "الرجاء إرسال رابط تيك توك أو يوتيوب صحيح. 🔗"
        )


def main():
    """الدالة الرئيسية لتشغيل البوت."""
    print("🤖 البوت قيد التشغيل (TikTok + YouTube)...")
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(TypeHandler(Update, check_ban_status), group=-1)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    PORT = int(os.environ.get("PORT", 8443))
    
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{APP_URL}/{TOKEN}"
    )


if __name__ == "__main__":
    main()
