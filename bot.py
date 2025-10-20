import os
import yt_dlp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- سنقرأ التوكن من متغيرات البيئة (الخادم) ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
# --- اسم الرابط الذي سيعطيه لنا الخادم ---
APP_URL = os.environ.get("RENDER_EXTERNAL_URL")


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


# (handler) دالة لآمر /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "فقط أرسل رابط فيديو تيك توك 🔗"
    )


# (handler) دالة لمعالجة الروابط
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text

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
            else:
                await update.message.reply_text("عذراً، لم أستطع تحميل الفيديو (الملف فارغ). 😕")

        except Exception as e:
            print(f"حدث خطأ: {e}")
            await update.message.reply_text(
                "عذراً، حدث خطأ. 🚫\n"
                "تأكد أن الرابط عام وليس خاصاً، أو أن الفيديو لم يُحذف."
            )
        finally:
            if os.path.exists(video_path):
                os.remove(video_path)
    else:
        await update.message.reply_text(
            "الرجاء إرسال رابط تيك توك صحيح. 🔗"
        )


def main():
    """الدالة الرئيسية لتشغيل البوت (بنظام Webhook)."""
    print("🤖 البوت قيد التشغيل (بنظام Webhook)...")

    application = Application.builder().token(TOKEN).build()

    # إضافة الأوامر
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # --- هذا هو الجزء الأهم للتشغيل على الخادم ---
    # الخادم سيعطينا رقم "بورت" (منفذ) ليعمل عليه البوت
    PORT = int(os.environ.get("PORT", 8443))

    # ابدأ البوت بنظام Webhook
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,  # نستخدم التوكن كجزء من الرابط لزيادة الأمان
        webhook_url=f"{APP_URL}/{TOKEN}"
    )


if __name__ == "__main__":
    main()