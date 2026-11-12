import logging
from ddgs import DDGS

logger = logging.getLogger(__name__)


def search_web(query: str, max_results: int = 4) -> str:
    """Internetdan ma'lumot izlash (DuckDuckGo orqali)."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            if not results:
                return ""
            
            snippets = []
            for r in results:
                title = r.get("title", "")
                body = r.get("body", "")
                link = r.get("href", "")
                snippets.append(f"• {title}\n  {body}\n  Manba: {link}")
            
            return "\n\n".join(snippets)
    except Exception as e:
        logger.warning(f"Internet qidiruvida xatolik: {e}")
        return ""


def should_search_web(prompt: str) -> bool:
    """So'rovda internetdan qidiruv kerak yoki yo'qligini aniqlash."""
    keywords = [
        "qidir", "izla", "yangilik", "bugun", "kecha", "kurs", "dollar",
        "narx", "ob-havo", "havo", "prezident", "futbol", "o'yin",
        "kim", "qachon", "qayerda", "2024", "2025", "2026", "sayt",
        "qonun", "qaror", "natija", "google", "internet"
    ]
    prompt_lower = prompt.lower()
    return any(k in prompt_lower for k in keywords)
