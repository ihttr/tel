# 1. ابدأ بصورة بايثون رسمية
FROM python:3.10-slim

# 2. قم بتثبيت ffmpeg (هذا هو سبب استخدامنا لدوكر)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# 3. إعداد مجلد العمل داخل الكونتينر
WORKDIR /app

# 4. انسخ ملف المكتبات وقم بتثبيتها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. انسخ باقي ملفات الكود
COPY . .

# 6. حدد الأمر الذي سيتم تشغيله (نفس الأمر السابق)
CMD ["python", "bot.py"]
