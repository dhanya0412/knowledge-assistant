import re


_NLTK_RESOURCES = {
    "punkt": "tokenizers/punkt",
    "punkt_tab": "tokenizers/punkt_tab",
    "stopwords": "corpora/stopwords",
    "wordnet": "corpora/wordnet",
    "omw-1.4": "corpora/omw-1.4",
}
_nltk_ready = False
_stop_words = None
_lemmatizer = None
nltk = None
stopwords = None
WordNetLemmatizer = None
nltk_sent_tokenize = None
word_tokenize = None


def ensure_nltk_data():
    global _nltk_ready
    global nltk
    global stopwords
    global WordNetLemmatizer
    global nltk_sent_tokenize
    global word_tokenize

    if _nltk_ready:
        return

    try:
        import nltk as nltk_module
        from nltk.corpus import stopwords as stopwords_module
        from nltk.stem import WordNetLemmatizer as wordnet_lemmatizer_class
        from nltk.tokenize import sent_tokenize as sent_tokenize_function
        from nltk.tokenize import word_tokenize as word_tokenize_function
    except ImportError as exc:
        raise RuntimeError("nltk dependency is not installed") from exc

    nltk = nltk_module
    stopwords = stopwords_module
    WordNetLemmatizer = wordnet_lemmatizer_class
    nltk_sent_tokenize = sent_tokenize_function
    word_tokenize = word_tokenize_function

    for package, resource in _NLTK_RESOURCES.items():
        try:
            nltk.data.find(resource)
        except LookupError:
            nltk.download(package, quiet=True)

    _nltk_ready = True


def clean_document_text(text):
    """Light, lossless-as-possible document cleaning.

    This is the ONLY cleaning step that may touch text before it is stored
    as `text_content` or used to build chunks. It must preserve the
    original wording, sentence order, and grammar of the document. It only:

      - normalizes Windows/Linux line endings
      - strips unprintable/control characters (extraction artefacts)
      - normalizes runs of whitespace
      - collapses excessive blank lines / rejoins wrapped lines into
        paragraphs
      - drops obvious page-number artefacts

    It must NOT lowercase, tokenize, lemmatize, remove stopwords, or
    otherwise rewrite the text. For NLP-only preprocessing, use
    `preprocess_for_nlp()` instead.
    """
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")

    # Strip unprintable/control characters (common PDF/OCR extraction
    # artefacts) while leaving normal punctuation, symbols, and unicode
    # text untouched. \t and \n are kept since they're handled below.
    text = "".join(
        ch for ch in text
        if ch in ("\n", "\t") or ch == " " or ch.isprintable()
    )

    paragraphs = []
    current_lines = []

    for raw_line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw_line).strip()

        if not line:
            if current_lines and _line_ends_paragraph(current_lines[-1]):
                paragraphs.append(" ".join(current_lines))
                current_lines = []
            continue

        if _looks_like_page_number(line):
            continue

        if current_lines and _starts_new_block(line, current_lines[-1]):
            paragraphs.append(" ".join(current_lines))
            current_lines = []

        current_lines.append(line)

    if current_lines:
        paragraphs.append(" ".join(current_lines))

    return "\n\n".join(paragraphs).strip()


def clean_text(text):
    """Deprecated alias for clean_document_text. Kept so existing imports
    (e.g. keyword_extractor, summarizer) keep working unchanged; prefer
    `clean_document_text` in new code."""
    return clean_document_text(text)


def _line_ends_paragraph(line):
    return bool(re.search(r"[.!?:)]$", line))


def _looks_like_page_number(line):
    return bool(re.fullmatch(r"\d{1,4}", line))


def _starts_new_block(line, previous_line):
    if re.match(r"^(step\s+\d+|method\s+[ivx]+|downloads?)\b", line, re.I):
        return True

    if not _line_ends_paragraph(previous_line):
        return False

    return bool(re.match(r"[A-Z0-9]", line))


def preprocess_for_nlp(text):
    """Internal-only NLP preprocessing: tokenize, lowercase, drop stopwords,
    lemmatize. The output is for ML/NLP consumers (e.g. keyword extraction,
    word counts) and must never be written back to storage — it does not
    preserve original wording, casing, or sentence structure.
    """
    global _stop_words
    global _lemmatizer

    ensure_nltk_data()
    if _stop_words is None:
        _stop_words = set(stopwords.words("english"))
    if _lemmatizer is None:
        _lemmatizer = WordNetLemmatizer()

    tokens = word_tokenize(clean_document_text(text))
    normalized = []
    for token in tokens:
        token = token.lower()
        if not re.fullmatch(r"[a-z0-9]+", token):
            continue
        if token in _stop_words:
            continue

        normalized.append(_lemmatizer.lemmatize(token))

    return normalized


# Backward-compatible alias. Prefer `preprocess_for_nlp` for new code; this
# function is internal-NLP-only and its output must not be stored.
def tokenize_and_normalize(text):
    return preprocess_for_nlp(text)


def sent_tokenize(text):
    cleaned_text = clean_document_text(text)
    if not cleaned_text:
        return []

    ensure_nltk_data()
    return [
        re.sub(r"\s+", " ", sentence).strip()
        for sentence in nltk_sent_tokenize(cleaned_text)
        if sentence.strip()
    ]


def tokenize(text):
    return re.findall(r"[A-Za-z0-9]+", (text or "").lower())