# Distribyutor platformasi (1-bosqich)

## Ishga tushirish
    python -m venv venv
    venv\Scripts\activate        # Linux/Mac: source venv/bin/activate
    pip install -r requirements.txt
    uvicorn app.main:app --reload

Brauzerda http://127.0.0.1:8000/docs oching (avtomatik Swagger).

## Birinchi kirish
Login: `admin`  Parol: `admin123`  (darhol o'zgartiring!)
Swagger'da yuqoridagi "Authorize" tugmasi orqali kiring.

## Tekshirish tartibi
1. Admin sifatida: POST /admin/products (masalan, Cola, birlik: blok)
2. POST /admin/users  (role: dokon) -> POST /admin/stores (user_id bilan bog'lang)
3. POST /admin/users  (role: zavod)
4. Har bir rol bilan /auth/login qilib, ruxsatlar to'g'ri ishlashini ko'ring.

## Keyingi bosqich
Do'kon kabinasi: qoldiq, sotuv kiritish, ariza yuborish.

---
# 2-bosqich: Do'kon kabinasi

## Yangi endpointlar (rol: dokon)
- GET  /dokon/deliveries            yetkazilgan tovarlar (?only_pending=true)
- POST /dokon/deliveries/{id}/confirm   yetkazishni qabul qilish
- GET  /dokon/stock                 qoldiq + tavsiya etilgan buyurtma miqdori
- POST /dokon/sales                 kunlik sotuv kiritish
- GET  /dokon/sales                 sotuvlar tarixi
- POST /dokon/orders                distribyutorga ariza yuborish
- GET  /dokon/orders                arizalar va holatlari
- POST /dokon/orders/{id}/cancel    yangi arizani bekor qilish
- GET  /dokon/debt                  qarzdorlik

## Sinash tartibi (cola misoli)
1. Admin: tovar (Cola, blok, 50000), do'kon foydalanuvchisi (role: dokon), do'kon (user_id bilan), zavod foydalanuvchisi.
2. Zavod/Admin: POST /zavod/deliveries  {store_id, product_id, quantity: 10}
3. Do'kon bilan kiring: GET /dokon/deliveries -> POST .../confirm
4. POST /dokon/sales  2, 3, 3, 2 (har bir sotuv alohida)
5. GET /dokon/stock -> qoldiq 0, tavsiya etilgan miqdor 10
6. POST /dokon/orders  {product_id, quantity: 12}

---
# 3-bosqich: Zavod kabinasi (rol: zavod yoki admin)

- GET  /zavod/dashboard                bosh sahifa: yangi arizalar, umumiy qarz, to'ldirish kerak bo'lganlar
- GET  /zavod/orders                   arizalar (?status=yangi&store_id=1)
- POST /zavod/orders/{id}/approve      arizani tasdiqlash
- POST /zavod/orders/{id}/reject       arizani rad etish
- POST /zavod/orders/{id}/deliver      arizani yetkazish (miqdor/narx ixtiyoriy)
- POST /zavod/deliveries               arizasiz yetkazish kiritish
- GET  /zavod/deliveries               yetkazishlar (?only_pending=true)
- GET  /zavod/stock                    barcha do'konlar qoldig'i
- GET  /zavod/stores/{id}/stock        bitta do'kon qoldig'i
- POST /zavod/payments                 do'kon to'lovini kiritish
- GET  /zavod/payments                 to'lovlar tarixi
- GET  /zavod/debts                    do'konlar qarzdorligi

## Sinash (cola misoli)
1. Do'kon sotuvni 2, 3, 3, 2 kiritgach ariza yuboradi (POST /dokon/orders, 12 blok).
2. Zavod: GET /zavod/dashboard -> new_orders: 1
3. POST /zavod/orders/{id}/deliver -> do'kon yetkazishni tasdiqlaydi (POST /dokon/deliveries/{id}/confirm)
4. GET /zavod/debts -> do'kon qarzi 12 x 50000 = 600000
5. POST /zavod/payments {store_id, amount: 300000} -> qarz 300000

---
# 4-bosqich: Veb-interfeys
Server ishga tushgach brauzerda http://127.0.0.1:8000/ ni oching (Swagger: /docs).
Rolga qarab o'z kabinasi ochiladi: do'kon, distribyutor (zavod) yoki administrator.
Interfeys fayli: app/static/index.html

---
# 5-bosqich: 3 ta alohida panel
- **Admin paneli:** umumiy ko'rsatkichlar, foydalanuvchilar (bloklash, parolni tiklash), do'konlar va tovarlarni tahrirlash, hisobot (CSV).
- **Zavod paneli:** bosh sahifa, arizalar, yetkazish, do'konlar qoldig'i, to'lov va qarz.
- **Do'kon paneli:** qoldiq, qabul qilish, sotuv, ariza, qarz.
- Hamma panelda "Parol" bo'limi bor. Birinchi kirishda admin parolini o'zgartiring!

## Telegram ogohlantirish
run.bat ichidagi TELEGRAM_BOT_TOKEN va TELEGRAM_CHAT_ID qatorlaridan "rem" ni olib tashlab, qiymatlarni yozing.
Do'kon ariza yuborganda distribyutor chatiga xabar boradi. Token maxfiy: uni hech kimga bermang.

---
# Sinov uchun tayyor hisoblar
seed_demo.bat ni bir marta ishga tushiring (yoki: python seed_demo.py). Quyidagilar yaratiladi:

| Panel          | Login  | Parol    |
|----------------|--------|----------|
| Admin paneli   | admin  | admin123 |
| Zavod paneli   | zavod1 | zavod123 |
| Do'kon paneli  | dokon1 | dokon123 |

Shuningdek "Namuna do'kon" (dokon1 ga biriktirilgan) va "Cola" tovari qo'shiladi.
Haqiqiy foydalanishdan oldin parollarni "Parol" bo'limida o'zgartiring!
