@echo off
cd /d "%~dp0"

rem --- Telegram ogohlantirish (yangi ariza kelganda xabar yuboradi) ---
rem Yoqish uchun ikki qator boshidagi "rem" ni olib tashlang va qiymatlarni yozing:
rem set TELEGRAM_BOT_TOKEN=bot_tokeningiz
rem set TELEGRAM_CHAT_ID=chat_id_raqami

rem --- Xavfsizlik: o'zingizning uzun tasodifiy kalitingizni yozing ---
rem set SECRET_KEY=uzun_tasodifiy_matn

echo Distribyutor serveri: http://127.0.0.1:8001/
uvicorn app.main:app --reload --port 8001
pause
