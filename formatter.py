import re
import html


def format_to_telegram_html(text: str) -> str:
    """Gemini tomonidan berilgan matnni Telegram HTML formatiga xavfsiz va chiroyli o'tkazish.
    
    Yulduzchalar (***, **) va boshqa markdown elementlarini to'g'rilaydi.
    """
    if not text:
        return ""

    # 1. HTML xavfsizligi: <, >, & belgilarini escape qilish
    text = html.escape(text)

    # 2. Ko'p qatorli kod bloklari: ```python ... ``` -> <pre><code>...</code></pre>
    def replace_code_block(match):
        code = match.group(2)
        # Oldin escape qilingan kodni joylaymiz
        return f"<pre><code>{code.strip()}</code></pre>"

    text = re.sub(r"```(?:\w+)?\n?(.*?)```", replace_code_block, text, flags=re.DOTALL)

    # 3. Bir qatorli kodlar: `kod` -> <code>kod</code>
    text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)

    # 4. Sarlavhalar: ### Sarlavha -> <b>Sarlavha</b>
    text = re.sub(r"(?m)^#{1,6}\s*(.+)$", r"<b>\1</b>", text)

    # 5. ***uchta yulduzcha*** -> <b><i>matn</i></b>
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", text)

    # 6. **ikkita yulduzcha** -> <b>matn</b>
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    # 7. *bitta yulduzcha* -> <i>matn</i> (so'z orasidagi ko'paytirish belgilariga tegmaslik uchun)
    text = re.sub(r"(?<!\w)\*([^\*\n]+?)\*(?!\w)", r"<i>\1</i>", text)

    # 8. Ro'yxat belgilari (* yoki - qator boshida) -> chiroyli bullet •
    text = re.sub(r"(?m)^[\*\-]\s+", "• ", text)

    return text
