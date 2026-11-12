import io
from typing import Tuple, Optional
import pypdf
import docx
import openpyxl

MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB
MAX_AUDIO_SIZE = 20 * 1024 * 1024  # 20 MB


def extract_text_from_docx(file_bytes: bytes) -> str:
    """DOCX fayldan barcha matn va jadvallarni ajratib olish."""
    doc = docx.Document(io.BytesIO(file_bytes))
    lines = []
    for p in doc.paragraphs:
        if p.text.strip():
            lines.append(p.text.strip())

    for table in doc.tables:
        lines.append("\n[Jadval:]")
        for row in table.rows:
            row_data = [cell.text.strip() for cell in row.cells]
            lines.append(" | ".join(row_data))

    return "\n".join(lines)


def extract_text_from_excel(file_bytes: bytes) -> str:
    """Excel (.xlsx) fayldan barcha varaqlardagi ma'lumotlarni ajratib olish."""
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    lines = []
    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        lines.append(f"\n--- Varaq: {sheet_name} ---")
        for row in sheet.iter_rows(values_only=True):
            if any(cell is not None for cell in row):
                row_str = " | ".join(str(cell) if cell is not None else "" for cell in row)
                lines.append(row_str)
    return "\n".join(lines)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """PDF fayldan matnlarni ajratib olish."""
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    pages_text = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text:
            pages_text.append(f"--- Sahifa {i + 1} ---\n{text.strip()}")
    return "\n\n".join(pages_text)


def process_document_content(file_name: str, file_bytes: bytes) -> Tuple[Optional[str], Optional[bytes], str]:
    """Hujjatdan matn yoki to'g'ridan-to'g'ri Gemini part uchun baytlarni ajratish.
    
    Qaytaradi: (text_content, raw_bytes_if_pdf, mime_type)
    """
    ext = file_name.split(".")[-1].lower() if "." in file_name else ""

    if ext == "pdf":
        # PDF ni Gemini bevosita 'application/pdf' sifatida yaxshi tushunadi,
        # lekin matnini ham o'qib qo'yish mumkin.
        return None, file_bytes, "application/pdf"
    elif ext in ["docx", "doc"]:
        try:
            text = extract_text_from_docx(file_bytes)
            return text, None, "text/plain"
        except Exception as e:
            return f"DOCX o'qishda xatolik: {e}", None, "text/plain"
    elif ext in ["xlsx", "xls"]:
        try:
            text = extract_text_from_excel(file_bytes)
            return text, None, "text/plain"
        except Exception as e:
            return f"Excel o'qishda xatolik: {e}", None, "text/plain"
    elif ext in ["txt", "csv", "json", "xml", "md"]:
        try:
            text = file_bytes.decode("utf-8", errors="ignore")
            return text, None, "text/plain"
        except Exception as e:
            return f"Faylni o'qishda xatolik: {e}", None, "text/plain"
    else:
        # Boshqa noma'lum hujjat turlari uchun matn sifatida urinib ko'rish
        try:
            text = file_bytes.decode("utf-8", errors="ignore")
            return text, None, "text/plain"
        except Exception:
            return None, file_bytes, "application/octet-stream"
