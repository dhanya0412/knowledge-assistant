from app.services.preprocessor import clean_document_text, sent_tokenize


def extract_keywords(text, top_n=10, sentences=None):
    cleaned_text = clean_document_text(text)
    if not cleaned_text:
        raise ValueError("text is required for keyword extraction")

    if top_n <= 0:
        return []

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ImportError as exc:
        raise RuntimeError("scikit-learn dependency is not installed") from exc

    sentences = sentences or sent_tokenize(cleaned_text)
    if not sentences:
        return []

    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))

    try:
        matrix = vectorizer.fit_transform(sentences)
    except ValueError as exc:
        if "empty vocabulary" in str(exc):
            return []
        raise

    scores = matrix.sum(axis=0).A1
    terms = vectorizer.get_feature_names_out()
    ranked_terms = sorted(
        zip(terms, scores),
        key=lambda item: (-item[1], item[0]),
    )

    return [
        term
        for term, score in ranked_terms[:top_n]
        if score > 0
    ]
