import os
import yt_dlp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- قراءة المتغيرات من الخادم ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
APP_URL = os.environ.get("RENDER_EXTERNAL_URL")
# --- المتغير الجديد الخاص بقناة السجلات ---
LOG_CHANNEL_ID = os.environ.get("LOG_CHANNEL_ID") 

# دالة مساعدة لإرسال السجلات
async def send_log(message, context: ContextTypes.DEFAULT_TYPE):
    """يرسل رسالة إلى قناة السجلات إذا كانت موجودة"""
    if LOG_CHANNEL_ID:
        try:
            await context.bot.send_message(
                chat_id=LOG_CHANNEL_ID,
                text=message,
                parse_mode='Markdown' # لجعل النص منسقاً
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
        "أرسل لي أي رابط فيديو من تيك توك وسأقوم بإرساله لك بأعلى جودة. 🎬"
    )
    
    # --- إرسال سجل عند ضغط /start ---
    user_info = f"User: {user.first_name} (@{user.username}, ID: {user.id})"
    await send_log(f"🚀 **Bot Started**\n{user_info}", context)

# (handler) دالة لآمر /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "فقط أرسل رابط فيديو تيك توك 🔗"
    )

# (handler) دالة لمعالجة الروابط
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text
    user = update.effective_user # <-- جلب معلومات المستخدم
    
    if "tiktok.com" in message_text:
        await update.message.reply_text("...⏳ جاري تحميل الفيديو (بأعلى جودة)، قد يستغرق هذا وقتاً أطول قليلاً...")
        video_path = "final_video.mp4"
        
        if os.path.exists(video_path):
            os.remove(video_path)
            
        try:
            ydl_opts = {
                'format': 'bestvideo+bestaudio/best',
                'outtmpl': video_path,
                'quiet': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([message_text])

            if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                with open(video_path, 'rb') as video_file:
                    video_bytes = video_file.read()

                await update.message.reply_video(
                    video=video_bytes,
                    caption="تفضل الفيديو الخاص بك (بأعلى جودة)! 🥳"
                )
                
                # --- إرسال سجل عند نجاح التحميل ---
                user_info = f"User: {user.first_name} (@{user.username}, ID: {user.id})"
                log_message = (
                    f"✅ **New Download**\n\n"
                    f"{user_info}\n\n"
                    f"Link: `{message_text}`" # نضع الرابط بين علامتي ` لنسخه بسهولة
                )
                await send_log(log_message, context)
                
            else:
                await update.message.reply_text("عذراً، لم أستطع تحميل الفيديو (الملف فارغ). 😕")
                # --- إرسال سجل عند فشل التحميل ---
                await send_log(f"❌ **Download Failed (Empty File)**\nLink: {message_text}", context)

        except Exception as e:
            print(f"حدث خطأ: {e}")
            await update.message.reply_text(
                "عذراً، حدث خطأ. 🚫\n"
                "تأكد أن الرابط عام وليس خاصاً، أو أن الفيديو لم يُحذف."
            )
            # --- إرسال سجل عند حدوث خطأ ---
            await send_log(f"🚫 **Error**\nLink: `{message_text}`\nError: `{e}`", context)
            
        finally:
            if os.path.exists(video_path):
                os.remove(video_path)
    else:
        await update.message.reply_text(
            "الرجاء إرسال رابط تيك توك صحيح. 🔗"
        )


def main():
    """الدالة الرئيسية لتشغيل البوت (بنظام Webhook)."""
    print("🤖 البوت قيد التشغيل (بنظام Webhook + Logging)...")
    
    application = Application.builder().token(TOKEN).build()

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
