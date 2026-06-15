from app.services.preprocessor import clean_text


def extract_keywords(text, top_n=10):
    cleaned_text = clean_text(text)
    if not cleaned_text:
        raise ValueError("text is required for keyword extraction")

    if top_n <= 0:
        return []

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ImportError as exc:
        raise RuntimeError("scikit-learn dependency is not installed") from exc

    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        lowercase=True,
    )

    try:
        matrix = vectorizer.fit_transform([cleaned_text])
    except ValueError as exc:
        if "empty vocabulary" in str(exc):
            return []
        raise

    scores = matrix.toarray()[0]
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
