import io

from pypdf import PdfReader

from app.core.config import settings


def extract_text(data: bytes, filename: str) -> str:
    """Извлекает текст из PDF или TXT."""
    if filename.lower().endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return data.decode("utf-8", errors="ignore")


def chunk_text(text: str) -> list[str]:
    """
    Разбивает текст на чанки по chunk_size символов с перекрытием chunk_overlap.
    Старается не разрывать предложения — разбивает по абзацам, потом по размеру.
    """
    size = settings.chunk_size
    overlap = settings.chunk_overlap

    # Сначала разбиваем по абзацам
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) <= size:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                chunks.append(current)
            # Если абзац сам по себе длиннее chunk_size — режем по символам
            if len(para) > size:
                for i in range(0, len(para), size - overlap):
                    chunks.append(para[i : i + size])
            else:
                current = para

    if current:
        chunks.append(current)

    return [c for c in chunks if c]
