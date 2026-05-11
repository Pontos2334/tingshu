import re


def split_text(text: str, chunk_size: int = 500) -> list[str]:
    text = text.strip()
    if not text:
        return []

    paragraphs = text.split("\n\n")
    chunks = []

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) <= chunk_size:
            chunks.append(para)
        else:
            sentences = re.split(r"([。！？；，])", para)
            current = ""
            for i in range(0, len(sentences), 2):
                sent = sentences[i]
                sep = sentences[i + 1] if i + 1 < len(sentences) else ""
                piece = sent + sep
                if len(current) + len(piece) > chunk_size and current:
                    chunks.append(current)
                    current = piece
                else:
                    current += piece
            if current:
                chunks.append(current)

    return chunks
