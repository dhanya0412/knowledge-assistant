import re


def clean_text(text):
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [
        re.sub(r"[ \t]+", " ", line).strip()
        for line in text.split("\n")
    ]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def tokenize(text):
    return re.findall(r"[A-Za-z0-9]+", (text or "").lower())
