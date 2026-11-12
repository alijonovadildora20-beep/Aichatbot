import io
import os
import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BufferedInputFile,
)

from config import BOT_TOKEN, ADMIN_ID
from ai_service import ask_gemini, ask_gemini_multimodal, transcribe_audio
from formatter import format_to_telegram_html
import memory_service
from file_processor import (
    MAX_FILE_SIZE,
    MAX_AUDIO_SIZE,
    process_document_content,
)

# Loglarni sozlash
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dp = Dispatcher()


# Admin xabar tarqatish holati
class AdminState(StatesGroup):
    waiting_for_broadcast_message = State()


# Pastki doimiy boshqaruv paneli (tugmalar)
def get_user_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    buttons = [
        [
            KeyboardButton(text="📊 Xotira holati"),
            KeyboardButton(text="🗑 Xotirani tozalash"),
        ],
        [
            KeyboardButton(text="ℹ️ Bot haqida"),
        ],
    ]
    # Agar admin bo'lsa, maxsus admin tugmasini ham chiqarish
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="🛠 Admin Panel")])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        is_persistent=True,
    )


# Admin Inline klaviaturasi
admin_inline_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 To'liq statistika", callback_data="admin_stats"),
            InlineKeyboardButton(text="📜 Oxirgi so'rovlar", callback_data="admin_logs"),
        ],
        [
            InlineKeyboardButton(text="📢 Xabar tarqatish (Broadcast)", callback_data="admin_broadcast"),
        ],
        [
            InlineKeyboardButton(text="🔄 Yangilash", callback_data="admin_refresh"),
        ],
    ]
)


def split_text(text: str, max_length: int = 3800) -> list[str]:
    chunks = []
    while len(text) > max_length:
        split_idx = text.rfind("\n", 0, max_length)
        if split_idx == -1:
            split_idx = max_length
        chunks.append(text[:split_idx])
        text = text[split_idx:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


async def send_formatted_message(message: Message, text: str):
    """Matnni Telegram HTML formatida chiroyli yuborish."""
    html_text = format_to_telegram_html(text)
    chunks = split_text(html_text)
    for chunk in chunks:
        try:
            await message.answer(chunk, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"HTML parse xatoligi: {e}. Oddiy matnda yuborilmoqda.")
            raw_chunks = split_text(text)
            for r_chunk in raw_chunks:
                await message.answer(r_chunk, parse_mode=None)


async def notify_admin(bot: Bot, message: Message, msg_type: str, prompt: str, reply: str):
    """Boshqa foydalanuvchilarning muloqotini real vaqt rejimida adminga bildirish."""
    user = message.from_user
    user_id = user.id

    # Foydalanuvchini bazaga yozish va faollikni qayd etish
    memory_service.upsert_user(
        user_id=user_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    user_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    if user.username:
        user_name += f" (@{user.username})"

    # Loglar bazasiga yozish
    memory_service.log_interaction(
        user_id=user_id,
        user_name=user_name,
        msg_type=msg_type,
        prompt=prompt[:1000],
        response=reply[:1000],
    )

    # Agar foydalanuvchi adminning o'zi bo'lsa, o'ziga bildirishnoma yubormaydi
    if user_id == ADMIN_ID:
        return

    admin_text = (
        "🔔 <b>Yangi muloqot qayd etildi:</b>\n\n"
        f"👤 <b>Foydalanuvchi:</b> {user_name}\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"📁 <b>Turi:</b> {msg_type}\n\n"
        f"📩 <b>So'rov:</b>\n<i>{prompt[:350]}</i>\n\n"
        f"🤖 <b>AI Javobi:</b>\n<i>{reply[:350]}</i>"
    )
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=admin_text, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Adminga bildirishnoma yuborilmadi: {e}")


# ==================== ADMIN PANEL HANDLERS ====================

@dp.message(Command("admin"))
@dp.message(F.text == "🛠 Admin Panel")
async def handle_admin_command(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("Kechirasiz, ushbu bo'lim faqat bot administratori uchun mo'ljallangan.")
        return

    stats = memory_service.get_admin_stats()
    admin_welcome = (
        "<b>🛠 Administrator boshqaruv paneli</b>\n\n"
        f"👥 <b>Jami foydalanuvchilar:</b> <code>{stats['total_users']}</code> ta\n"
        f"💬 <b>Jami savol-javoblar:</b> <code>{stats['total_logs']}</code> ta\n"
        f"📅 <b>Bugungi faollik:</b> <code>{stats['today_logs']}</code> ta xabar\n\n"
        "Quyidagi tugmalar orqali to'liq ma'lumotlarni ko'rishingiz mumkin:"
    )
    await message.answer(admin_welcome, parse_mode="HTML", reply_markup=admin_inline_kb)


@dp.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Ruxsat berilmagan!", show_alert=True)
        return

    stats = memory_service.get_admin_stats()
    text = (
        "<b>📊 Bot statistikasi:</b>\n\n"
        f"• Foydalanuvchilar soni: <b>{stats['total_users']}</b> nafar\n"
        f"• Jami amalga oshirilgan so'rovlar: <b>{stats['total_logs']}</b> ta\n"
        f"• Bugun berilgan savollar: <b>{stats['today_logs']}</b> ta\n"
        f"• Holat: 🟢 Faol (Modellar avtomatik rotatsiyada)"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=admin_inline_kb)
    await callback.answer()


@dp.callback_query(F.data == "admin_logs")
async def cb_admin_logs(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Ruxsat berilmagan!", show_alert=True)
        return

    logs = memory_service.get_recent_logs(limit=5)
    if not logs:
        await callback.answer("Hozircha hech qanday muloqot tarixi mavjud emas.", show_alert=True)
        return

    text_parts = ["<b>📜 Oxirgi 5 ta muloqot:</b>\n"]
    for l in logs:
        text_parts.append(
            f"👤 <b>{l['user_name']}</b> (<code>{l['user_id']}</code>) | {l['msg_type']}\n"
            f"❓ <i>{l['prompt'][:100]}</i>\n"
            f"💡 <i>{l['response'][:100]}</i>\n"
            f"🕒 <code>{l['created_at']}</code>\n"
            f"———————————————"
        )

    await callback.message.edit_text("\n".join(text_parts), parse_mode="HTML", reply_markup=admin_inline_kb)
    await callback.answer()


@dp.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Ruxsat berilmagan!", show_alert=True)
        return

    await state.set_state(AdminState.waiting_for_broadcast_message)
    await callback.message.answer(
        "📢 Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yozing (yoki bekor qilish uchun /cancel deb yozing):"
    )
    await callback.answer()


@dp.message(AdminState.waiting_for_broadcast_message)
async def process_broadcast(message: Message, state: FSMContext, bot: Bot):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Xabar tarqatish bekor qilindi.")
        return

    user_ids = memory_service.get_all_user_ids()
    sent_count = 0
    fail_count = 0

    progress_msg = await message.answer(f"⏳ Xabar tarqatilmoqda... (Jami: {len(user_ids)} ta)")

    for uid in user_ids:
        try:
            await bot.send_message(chat_id=uid, text=message.text)
            sent_count += 1
            await asyncio.sleep(0.05)  # Telegram limitiga tushmaslik uchun
        except Exception:
            fail_count += 1

    await state.clear()
    await progress_msg.edit_text(
        f"✅ <b>Xabar tarqatish yakunlandi!</b>\n\n"
        f"• Muvaffaqiyatli yetkazildi: <b>{sent_count}</b> ta\n"
        f"• Yetkazilmadi (bloklangan/ochiq emas): <b>{fail_count}</b> ta",
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "admin_refresh")
async def cb_admin_refresh(callback: CallbackQuery):
    stats = memory_service.get_admin_stats()
    text = (
        "<b>🛠 Administrator boshqaruv paneli (Yangilandi)</b>\n\n"
        f"👥 <b>Jami foydalanuvchilar:</b> <code>{stats['total_users']}</code> ta\n"
        f"💬 <b>Jami savol-javoblar:</b> <code>{stats['total_logs']}</code> ta\n"
        f"📅 <b>Bugungi faollik:</b> <code>{stats['today_logs']}</code> ta xabar"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=admin_inline_kb)
    await callback.answer("Ma'lumotlar yangilandi!")


# ==================== ASOSIY BOT HANDLERS ====================

@dp.message(CommandStart())
async def handle_start(message: Message):
    user_id = message.from_user.id
    # Foydalanuvchini ro'yxatdan o'tkazish
    memory_service.upsert_user(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
    )

    welcome_text = (
        "<b>Assalomu alaykum! Men sun'iy intellekt botiman.</b> (4-bosqich)\n\n"
        "Men siz bilan to'laqonli <b>o'zbek tilida</b> muloqot qilaman.\n\n"
        "🚀 <b>Yangi va kuchaytirilgan imkoniyatlarim:</b>\n"
        "• <b>🌐 Internetdan ma'lumot izlash:</b> Eng so'nggi yangiliklar, ob-havo, valyuta kurslari va dolzarb ma'lumotlarni internetdan topib beraman.\n"
        "• <b>🎙 Ovozli so'rovlar va transkripsiya:</b> Ovozli xabaringizni aniq o'zbek tilida matnga o'girib (<b>.txt</b>) beraman va savolingizga to'liq javob qaytaraman!\n"
        "• <b>⚡️ Barqaror modellar:</b> Yuklama yuqori bo'lsa ham avtomatik zaxira modellarga ulanib, xatolarsiz ishlayman.\n"
        "• <b>📄 Hujjatlar va Rasmlar:</b> 2 MB gacha fayllar (PDF, Word, Excel) va suratlarni sinchkovlik bilan tahlil qilaman.\n"
        "• <b>🧠 Xotira tizimi:</b> Suhbatimiz kontekstini eslab qolaman.\n\n"
        "Savolingizni matn yoki ovoz ko'rinishida yuborishingiz mumkin!"
    )
    await message.answer(
        welcome_text,
        parse_mode="HTML",
        reply_markup=get_user_keyboard(user_id),
    )


@dp.message(Command("help"))
@dp.message(F.text == "ℹ️ Bot haqida")
async def handle_help(message: Message):
    user_id = message.from_user.id
    help_text = (
        "<b>ℹ️ Bot qo'llanmasi (4-bosqich):</b>\n\n"
        "1. <b>Internet qidiruvi:</b> 'Bugungi yangiliklar', 'Dollar kursi', 'Ertaga ob-havo' kabi savollarga internetdan eng yangi ma'lumotlarni topib javob beradi.\n"
        "2. <b>Ovozli xabarlar:</b> Ovozli xabar yuborsangiz, bot uni matnga (transkripsiya) aylantirib .txt fayl beradi va savolingizga javob ham qaytaradi.\n"
        "3. <b>Fayllar (PDF, DOCX, Excel):</b> 2 MB gacha bo'lgan hujjatlarni tahlil qiladi.\n"
        "4. <b>Xotira:</b> So'nggi 20-50 ta xabar eslab qolinadi. '🗑 Xotirani tozalash' tugmasi orqali xotirani tozalash mumkin."
    )
    await message.answer(help_text, parse_mode="HTML", reply_markup=get_user_keyboard(user_id))


# Xotira holati
@dp.message(F.text == "📊 Xotira holati")
async def handle_memory_status(message: Message):
    user_id = message.from_user.id
    status = memory_service.get_memory_status(user_id)

    filled_blocks = int(status["percentage"] / 10)
    bar = "🟩" * filled_blocks + "⬜️" * (10 - filled_blocks)

    status_message = (
        f"<b>🧠 Xotira holati ko'rsatkichlari:</b>\n\n"
        f"{status['indicator']} <b>Holat:</b> {status['status_text']}\n"
        f"📊 <b>Saqlangan xabarlar:</b> <code>{status['count']} / {status['max_limit']}</code> ta\n"
        f"📈 <b>To'lish darajasi:</b> <code>{status['percentage']}%</code>\n"
        f"[{bar}]\n\n"
        f"• <i>Minimal xotira hajmi:</i> 20 ta xabar\n"
        f"• <i>Maksimal chegara:</i> 50 ta xabar (avtomatik yangilanish)\n"
    )
    await message.answer(status_message, parse_mode="HTML", reply_markup=get_user_keyboard(user_id))


# Xotirani tozalash
@dp.message(F.text == "🗑 Xotirani tozalash")
async def handle_clear_memory(message: Message):
    user_id = message.from_user.id
    deleted_count = memory_service.clear_history(user_id)

    reply_text = (
        "<b>🗑 Suhbat xotirasi muvaffaqiyatli tozalandi!</b>\n\n"
        f"O'chirilgan xabarlar soni: <code>{deleted_count}</code> ta.\n"
        "Hozirda xotira: <code>0 / 50</code> (to'liq bo'sh).\n\n"
        "Endi yangi mavzuni toza sahifadan boshlashimiz mumkin!"
    )
    await message.answer(reply_text, parse_mode="HTML", reply_markup=get_user_keyboard(user_id))


# 1. RASMLARNI QABUL QILISH VA TAHLIL QILISH
@dp.message(F.photo)
async def handle_photo(message: Message, bot: Bot):
    user_id = message.from_user.id
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

    photo = message.photo[-1]
    prompt = message.caption or "Ushbu rasmni batafsil tahlil qiling va nimalar tasvirlanganini to'liq o'zbek tilida tushuntirib bering."

    file_io = io.BytesIO()
    await bot.download(photo, destination=file_io)
    img_bytes = file_io.getvalue()

    history = memory_service.get_history(user_id)
    reply = await ask_gemini_multimodal(
        history=history,
        prompt=prompt,
        media_bytes=img_bytes,
        mime_type="image/jpeg",
    )

    memory_service.add_message(user_id, "user", f"[Rasm yuborildi] {prompt}")
    memory_service.add_message(user_id, "model", reply)

    await send_formatted_message(message, reply)
    await notify_admin(bot, message, "Rasm 🖼", prompt, reply)


# 2. OVOZLI XABARLAR (TRANSKRIPSIYA + SAVOLGA JAVOB)
@dp.message(F.voice | F.audio)
async def handle_audio(message: Message, bot: Bot):
    user_id = message.from_user.id
    is_voice = bool(message.voice)
    audio_obj = message.voice if is_voice else message.audio
    file_size = audio_obj.file_size or 0

    if file_size > MAX_AUDIO_SIZE:
        size_mb = round(file_size / (1024 * 1024), 2)
        await message.reply(
            f"⚠️ <b>Xatolik:</b> Audio hajmi juda katta ({size_mb} MB)!\n"
            "Ovozli xabar va audio fayllar hajmi <b>20 MB dan oshmasligi</b> kerak.",
            parse_mode="HTML",
        )
        return

    status_msg = await message.reply("⏳ Ovozli xabar qabul qilindi. O'zbek tilida transkripsiya qilinmoqda...")
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.RECORD_VOICE)

    file_io = io.BytesIO()
    await bot.download(audio_obj, destination=file_io)
    audio_bytes = file_io.getvalue()

    mime_type = "audio/ogg" if is_voice else (audio_obj.mime_type or "audio/mp3")

    # 1. O'zbek tilida transkripsiya qilish
    transcription = await transcribe_audio(audio_bytes, mime_type=mime_type)

    txt_bytes = transcription.encode("utf-8")
    txt_file = BufferedInputFile(txt_bytes, filename="transkripsiya.txt")

    await status_msg.delete()

    # Transkripsiya faylini taqdim etish
    caption = "🎙 <b>Ovozli xabar transkripsiyasi (.txt) tayyor!</b>"
    await message.answer_document(
        document=txt_file,
        caption=caption,
        parse_mode="HTML",
    )

    # 2. Savolga javob berish (Ovozli so'rovga AI javobi)
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    history = memory_service.get_history(user_id)
    ai_reply = await ask_gemini(history, transcription)

    # Javobni yuborish
    full_answer = (
        f"📝 <b>Aytilgan nutq:</b>\n<i>\"{transcription}\"</i>\n\n"
        f"🤖 <b>Javob:</b>\n{ai_reply}"
    )
    await send_formatted_message(message, full_answer)

    # Xotiraga kiritish
    memory_service.add_message(user_id, "user", f"[Ovozli xabar]: {transcription}")
    memory_service.add_message(user_id, "model", ai_reply)

    # Adminga bildirish
    await notify_admin(bot, message, "Ovoz 🎙", transcription, ai_reply)


# 3. HUJJATLAR (PDF, DOCX, EXCEL, TXT)
@dp.message(F.document)
async def handle_document(message: Message, bot: Bot):
    user_id = message.from_user.id
    doc = message.document
    file_size = doc.file_size or 0
    file_name = doc.file_name or "fayl"

    if file_size > MAX_FILE_SIZE:
        size_mb = round(file_size / (1024 * 1024), 2)
        await message.reply(
            f"⚠️ <b>Xatolik:</b> Fayl hajmi <b>2 MB dan oshmasligi kerak!</b>\n"
            f"Siz yuborgan fayl hajmi: <code>{size_mb} MB</code>.\n"
            f"Iltimos, hajmi 2 MB gacha bo'lgan PDF, Word, Excel yoki matnli fayl yuboring.",
            parse_mode="HTML",
        )
        return

    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    status_msg = await message.reply(f"📄 <code>{file_name}</code> tahlil qilinmoqda...")

    file_io = io.BytesIO()
    await bot.download(doc, destination=file_io)
    file_bytes = file_io.getvalue()

    user_prompt = message.caption or "Ushbu hujjatni tahlil qiling va uning asosiy mazmunini o'zbek tilida batafsil tushuntirib bering."

    text_content, raw_bytes, mime_type = process_document_content(file_name, file_bytes)
    history = memory_service.get_history(user_id)

    if raw_bytes:
        reply = await ask_gemini_multimodal(
            history=history,
            prompt=user_prompt,
            media_bytes=raw_bytes,
            mime_type=mime_type,
        )
    else:
        full_prompt = (
            f"Foydalanuvchi quyidagi '{file_name}' nomli hujjatni yubordi:\n\n"
            f"--- HUJJAT MATNI ---\n{text_content}\n--- HUJJAT TUGADI ---\n\n"
            f"Savol / Vazifa: {user_prompt}"
        )
        reply = await ask_gemini(history, full_prompt)

    await status_msg.delete()

    memory_service.add_message(user_id, "user", f"[Fayl: {file_name}] {user_prompt}")
    memory_service.add_message(user_id, "model", reply)

    await send_formatted_message(message, reply)
    await notify_admin(bot, message, f"Hujjat 📄 ({file_name})", user_prompt, reply)


# Qo'llab-quvvatlanmaydigan media
@dp.message(F.video | F.video_note | F.sticker | F.animation)
async def handle_unsupported_media(message: Message):
    await message.reply(
        "Kechirasiz, video yoki stikerlar qo'llab-quvvatlanmaydi.\n\n"
        "Siz quyidagilarni yuborishingiz mumkin:\n"
        "• Matnli savollar (Internetdan ham qidiriladi)\n"
        "• Ovozli xabarlar (Transkripsiya + Javob)\n"
        "• Rasmlar\n"
        "• PDF, Word (DOCX), Excel (XLSX) va TXT fayllar (2 MB gacha)"
    )


# 4. ODDIY MATNLI XABARLAR (INTERNET QIDIRUVI + XOTIRA)
@dp.message(F.text)
async def handle_text(message: Message, bot: Bot):
    user_id = message.from_user.id
    prompt = message.text

    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

    history = memory_service.get_history(user_id)
    reply = await ask_gemini(history, prompt)

    memory_service.add_message(user_id, "user", prompt)
    memory_service.add_message(user_id, "model", reply)

    await send_formatted_message(message, reply)
    await notify_admin(bot, message, "Matn 💬", prompt, reply)


async def health_check(request):
    """Render va cron-job.org uchun health check sahifasi."""
    return web.Response(text="Bot is running 24/7!", status=200)


async def start_web_server():
    """Render uchun aiohttp web serverini ishga tushirish."""
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)

    port = int(os.getenv("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Web server {port}-portda muvaffaqiyatli ishga tushdi.")


async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN topilmadi!")
        return

    # Render uchun web serverni fonda ishga tushirish
    await start_web_server()

    bot = Bot(token=BOT_TOKEN)
    logger.info("Bot ishga tushmoqda (4-bosqich: Render 24/7 moslashuvi)...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
