import asyncio
import logging
from typing import List, Dict, Optional
from google import genai
from google.genai import types
from config import GEMINI_API_KEY
from search_service import search_web, should_search_web

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """Siz O'zbekistondagi eng aqlli, muloyim va foydali sun'iy intellekt yordamchisiz.
Asosiy qoidalar:
1. Siz FAQAT va FAQAT o'zbek tilida muloqot qilasiz. Barcha savollarga to'laqonli, aniq, muloyim va faqat o'zbek tilida javob bering.
2. MUHIM QOIDA: Agar foydalanuvchi sizga o'zbek tilidan boshqa tilda yozsa, hech qanday boshqa tilda javob bermang! Faqat quyidagi matnni javob sifatida qaytaring:
"Kechirasiz, men ushbu tilda gaplasha olmayman. Men faqat o'zbek tilida muloqot olib boraman. Iltimos, murojaatingizni o'zbek tilida yozing."
3. Siz foydalanuvchi bilan davomiy suhbat olib borasiz. Oldingi xabarlar tarixini (kontekstni) inobatga olgan holda javob qaytaring.
4. Javoblaringizni Telegram uchun chiroyli qilib yozing. Matnda chalkash yulduzchalar (*** yoki **) ishlatmang, kerak bo'lsa oddiy va tushunarli uslubda ifodalang.
5. Agar internetdan qidiruv ma'lumotlari taqdim etilgan bo'lsa, ulardan to'liq foydalanib, eng so'nggi va aniq javobni taqdim eting.
"""

AUDIO_TRANSCRIPTION_INSTRUCTION = """Siz o'zbek tili bo'yicha professional audio transkriptor (nutqni matnga o'giruvchi) mutaxassissiz.
Vazifangiz:
1. Ushbu audio yozuvdagi o'zbek tilidagi (yoki aralash) nutqni juda aniq, so'zma-so'z, lotin alifbosida matnga aylantiring.
2. O'zbek tili imlo va tinish belgilari qoidalariga to'liq rioya qiling.
3. Hech qanday kirish so'zi, tushuntirish yoki sharh yozmang. Faqat va faqat audioda eshitilgan matnni to'g'ridan-to'g'ri yozing.
"""

USER_FRIENDLY_ERROR = (
    "Kechirasiz, hozirda sun'iy intellekt tizimida vaqtinchalik yuqori yuklama kuzatilmoqda. "
    "Iltimos, 1 daqiqadan so'ng qayta so'rab ko'ring."
)

client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)

# Modellarning ustuvorlik tartibi (Limitga yetganda avtomatik keyingisiga o'tadi)
AVAILABLE_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
]


def _sync_generate_response(history: List[Dict[str, str]], prompt: str) -> str:
    """Matnli so'rov (Internet qidiruvi va modellar rotatsiyasi bilan)."""
    if not client:
        return "Tizim sozlanmagan: Gemini API kaliti kiritilmagan."

    # Agar so'rov internetdan ma'lumot talab qilsa, qidiruv natijalarini qo'shish
    effective_prompt = prompt
    if should_search_web(prompt):
        web_info = search_web(prompt)
        if web_info:
            effective_prompt = (
                f"[Internetdan olingan eng so'nggi ma'lumotlar]:\n{web_info}\n\n"
                f"Foydalanuvchi so'rovi: {prompt}\n"
                f"(Iltimos, yuqoridagi internet ma'lumotlaridan foydalangan holda javob bering.)"
            )

    contents = []
    for msg in history:
        contents.append(
            types.Content(
                role=msg["role"],
                parts=[types.Part.from_text(text=msg["content"])],
            )
        )
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=effective_prompt)],
        )
    )

    last_error = None
    for model_name in AVAILABLE_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.7,
                ),
            )
            if response.text:
                return response.text
        except Exception as e:
            logger.warning(f"Model {model_name} cheklovga uchradi: {e}. Keyingi model sinab ko'rilmoqda...")
            last_error = e
            continue

    logger.error(f"Barcha modellar muvaffaqiyatsiz bo'ldi. Oxirgi xatolik: {last_error}")
    return USER_FRIENDLY_ERROR


def _sync_generate_multimodal_response(
    history: List[Dict[str, str]],
    prompt: str,
    media_bytes: bytes,
    mime_type: str,
) -> str:
    """Rasm va fayllar uchun multimodal so'rov (modellar rotatsiyasi bilan)."""
    if not client:
        return "Tizim sozlanmagan: Gemini API kaliti kiritilmagan."

    contents = []
    for msg in history:
        contents.append(
            types.Content(
                role=msg["role"],
                parts=[types.Part.from_text(text=msg["content"])],
            )
        )

    user_parts = [
        types.Part.from_bytes(data=media_bytes, mime_type=mime_type),
        types.Part.from_text(text=prompt or "Ushbu ma'lumotni to'liq tahlil qilib, o'zbek tilida ma'lumot bering."),
    ]
    contents.append(types.Content(role="user", parts=user_parts))

    last_error = None
    for model_name in AVAILABLE_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.7,
                ),
            )
            if response.text:
                return response.text
        except Exception as e:
            logger.warning(f"Model {model_name} multimodal xatolik: {e}. Keyingisiga o'tilmoqda...")
            last_error = e
            continue

    logger.error(f"Multimodal barcha modellar xatolik berdi: {last_error}")
    return USER_FRIENDLY_ERROR


def _sync_transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """Ovozli xabarni o'zbek tilida transkripsiya qilish."""
    if not client:
        return "Tizim sozlanmagan: Gemini API kaliti kiritilmagan."

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                types.Part.from_text(text="Iltimos, ushbu ovozli xabardagi barcha nutqni to'liq o'zbek tilida transkripsiya qilib bering."),
            ],
        )
    ]

    last_error = None
    for model_name in AVAILABLE_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=AUDIO_TRANSCRIPTION_INSTRUCTION,
                    temperature=0.2,
                ),
            )
            if response.text:
                return response.text
        except Exception as e:
            logger.warning(f"Model {model_name} audio transkripsiya xatoligi: {e}. Keyingi modelga o'tilmoqda...")
            last_error = e
            continue

    logger.error(f"Audio transkripsiya barcha modellar uchun ishlamadi: {last_error}")
    return USER_FRIENDLY_ERROR


async def ask_gemini(history: List[Dict[str, str]], prompt: str) -> str:
    return await asyncio.to_thread(_sync_generate_response, history, prompt)


async def ask_gemini_multimodal(
    history: List[Dict[str, str]],
    prompt: str,
    media_bytes: bytes,
    mime_type: str,
) -> str:
    return await asyncio.to_thread(
        _sync_generate_multimodal_response, history, prompt, media_bytes, mime_type
    )


async def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    return await asyncio.to_thread(_sync_transcribe_audio, audio_bytes, mime_type)
