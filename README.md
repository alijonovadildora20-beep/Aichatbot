# Sun'iy intellektli Telegram Bot (4-bosqich)

Ushbu loyiha Google Gemini sun'iy intellekti bilan ishlaydigan Telegram botning 4-bosqichidir.

## 📌 4-bosqichda kiritilgan yangiliklar:

1. **🎙 O'zbek tili uchun mukammallashtirilgan Ovozli so'rovlar:**
   - O'zbek tili orfografiyasi va talaffuziga to'liq moslashtirilgan transkripsiya ko'rsatmasi.
   - Ovozli xabar yuborilganda:
     1. To'liq nutq `transkripsiya.txt` fayl ko'rinishida beriladi.
     2. Shu ovozli so'rovdagi savol/topshiriqqa Gemini AI to'laqonli o'zbek tilida javob qaytaradi!

2. **🌐 Internetdan ma'lumot izlash (Web Search):**
   - Yangiliklar, ob-havo, dollar kursi, so'nggi voqealar va internet ma'lumotlari so'ralganda bot internetdan eng yangi ma'lumotlarni izlab, unga asoslanib javob beradi.

3. **⚡️ Modellar rotatsiyasi (Fallback) & Xatoliklarni yashirish:**
   - Bir nechta Gemini modellari zaxirada (`gemini-3.5-flash-lite`, `gemini-3.8-flash`, `gemini-3.5-flash`, `gemini-2.5-flash`).
   - Agar bitta model limitga uchrasa yoki band bo'lsa, foydalanuvchiga hech qanday texnik xatolik ko'rsatmasdan avtomatik keyingisiga o'tadi.

4. **👮‍♂️ Admin Panel & Real-time Monitoring (ID: 5130423971):**
   - **Real-time bildirishnoma:** Boshqa foydalanuvchilar botga qanday savollar beryapti va Gemini nima javob beryapti — barchasi darhol Admin Telegramiga xabar sifatida yuboriladi.
   - **Admin buyrug'i:** `/admin` yoki menyudagi `🛠 Admin Panel` tugmasi:
     - 📊 To'liq statistika (Jami foydalanuvchilar, jami savol-javoblar, bugungi xabarlar).
     - 📜 Oxirgi so'rovlar tarixi.
     - 📢 Barcha foydalanuvchilarga xabar tarqatish (Broadcast).
