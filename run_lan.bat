@echo off
cd /d "%~dp0"
echo Telefondan kirish uchun kompyuter IP manzilini bilib oling (ipconfig, IPv4) va shu Wi-Fi tarmoqdagi telefonda oching: http://IP:8001/ilova
echo Diqqat: tarmoqdagi hamma shu serverga kira oladi. Faqat sinov uchun!
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
pause
