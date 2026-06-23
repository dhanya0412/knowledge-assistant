from app.services.preprocessor import clean_document_text
from app.services.preprocessor import sent_tokenize


def generate_summary(text, max_sentences=5, sentences=None):
    cleaned_text = clean_document_text(text)
    if not cleaned_text:
        raise ValueError("text is required for summarization")

    sentences = sentences or sent_tokenize(cleaned_text)
    if not sentences:
        raise ValueError("text is required for summarization")

    if max_sentences <= 0:
        return ""

    if len(sentences) <= max_sentences:
        return " ".join(sentences)

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ImportError as exc:
        raise RuntimeError("scikit-learn dependency is not installed") from exc

    vectorizer = TfidfVectorizer(stop_words="english", lowercase=True)

    try:
        matrix = vectorizer.fit_transform(sentences)
    except ValueError as exc:
        if "empty vocabulary" in str(exc):
            return " ".join(sentences[:max_sentences])
        raise

    sentence_scores = matrix.sum(axis=1).A1
    ranked_indexes = sorted(
        range(len(sentences)),
        key=lambda index: (-sentence_scores[index], index),
    )
    selected_indexes = sorted(ranked_indexes[:max_sentences])

    return " ".join(sentences[index] for index in selected_indexes)
