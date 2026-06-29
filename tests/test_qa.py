from datetime import datetime, timezone

import app.database as database
from app.services import qa_service
from app.services.retrieval import Chunk, build_tfidf_vectorizer, chunk_text


def test_tfidf_vectorizer_stems_terms_keeps_stopword_removal_and_uses_bigrams():
    vectorizer = build_tfidf_vectorizer()
    matrix = vectorizer.fit_transform([
        "We operate cloud services",
        "Operating cloud service",
    ])
    features = set(vectorizer.get_feature_names_out())

    assert vectorizer.ngram_range == (1, 2)
    assert "cloud servic" in features
    assert "oper" in features
    assert "we" not in features
    assert matrix[0].multiply(matrix[1]).sum() > 0


def test_question_classifier_recognizes_new_rule_based_types():
    examples = {
        "What are Microsoft's business segments?": qa_service.QUESTION_TYPE_LIST,
        "How much revenue did Microsoft report?": qa_service.QUESTION_TYPE_NUMERIC,
        "What was the operating income?": qa_service.QUESTION_TYPE_NUMERIC,
        "What did the CEO say about security?": qa_service.QUESTION_TYPE_NARRATIVE,
        "What are Microsoft's sustainability goals?": (
            qa_service.QUESTION_TYPE_NARRATIVE
        ),
    }

    for question, expected_type in examples.items():
        assert qa_service._classify_question(question) == expected_type


def test_numeric_scoring_prefers_the_sentence_with_a_numeric_value():
    candidates = [
        {
            "sentence": "Revenue is recognized when control transfers.",
            "sentence_index": 0,
            "chunk_sentences": [],
            "document": "annual-report.txt",
            "chunk_id": 1,
            "chunk_score": 0.5,
            "is_chunk_start": True,
        },
        {
            "sentence": "Revenue was $281,724 million.",
            "sentence_index": 0,
            "chunk_sentences": [],
            "document": "annual-report.txt",
            "chunk_id": 2,
            "chunk_score": 0.5,
            "is_chunk_start": True,
        },
    ]

    best_candidate, _score = qa_service._rank_sentences(
        "What was the revenue?",
        candidates,
    )

    assert best_candidate["chunk_id"] == 2


def test_list_context_collects_consecutive_list_items():
    sentences = [
        "Microsoft reports three business segments:",
        "Productivity and Business Processes.",
        "Intelligent Cloud.",
        "More Personal Computing.",
        "The company also reports corporate-level activity separately.",
    ]
    candidate = {
        "sentence": sentences[0],
        "sentence_index": 0,
        "chunk_sentences": sentences,
    }

    answer = qa_service._answer_context(
        "What are Microsoft's three business segments?",
        candidate,
    )

    assert answer == " ".join(sentences[:4])

    candidate["sentence"] = sentences[2]
    candidate["sentence_index"] = 2
    assert qa_service._answer_context(
        "What are Microsoft's three business segments?",
        candidate,
    ) == " ".join(sentences[:4])


def test_narrative_context_uses_sentence_window_until_next_heading():
    sentences = [
        "Shareholder Letter.",
        "The CEO described security as a core responsibility.",
        "The company will continue investing in cyber defense.",
        "Financial Highlights.",
        "Revenue increased during the year.",
    ]
    candidate = {
        "sentence": sentences[1],
        "sentence_index": 1,
        "chunk_sentences": sentences,
    }

    answer = qa_service._answer_context(
        "What did the CEO say about security?",
        candidate,
    )

    assert answer == " ".join(sentences[:3])


def test_retrieval_debug_output_can_be_disabled(monkeypatch, capsys):
    ranked_chunks = [(
        Chunk("document-id", "report.txt", "Risk Factors include cyber threats.", 81),
        0.87,
    )]
    monkeypatch.setattr(qa_service, "RETRIEVAL_DEBUG_ENABLED", True)
    qa_service._log_retrieval_debug("What risks are mentioned?", ranked_chunks)

    output = capsys.readouterr().out
    assert "Question:\nWhat risks are mentioned?" in output
    assert "Chunk 81 Score 0.8700" in output

    monkeypatch.setattr(qa_service, "RETRIEVAL_DEBUG_ENABLED", False)
    qa_service._log_retrieval_debug("Hidden question", ranked_chunks)
    assert capsys.readouterr().out == ""


def _build_stored_chunks(text_content):
    return [
        {
            "chunk_id": index,
            "text": chunk,
            "word_count": len(chunk.split()),
        }
        for index, chunk in enumerate(chunk_text(text_content), start=1)
    ]


def insert_document(
    *,
    title,
    uploaded_by,
    text_content,
    chunks=None,
    processed=True,
    status=None,
):
    document = {
        "title": title,
        "original_filename": f"{title.lower().replace(' ', '-')}.txt",
        "filename": f"{title.lower().replace(' ', '-')}-stored.txt",
        "filepath": f"/tmp/{title.lower().replace(' ', '-')}.txt",
        "uploaded_by": uploaded_by,
        "file_size": len(text_content),
        "content_type": "text/plain",
        "uploaded_at": datetime.now(timezone.utc),
        "tags": [],
        "text_content": text_content,
        "chunks": chunks if chunks is not None else _build_stored_chunks(text_content),
        "keywords": [],
        "summary": f"Summary for {title}",
        "processed": processed,
    }
    if status is not None:
        document["status"] = status

    result = database.db.documents.insert_one(document)
    return result.inserted_id


class TestQuestionAnswering:
    def test_ask_returns_answer_from_best_sentence(
        self,
        client,
        auth_headers,
        registered_user,
    ):
        user = database.db.users.find_one({"email": registered_user["email"]})
        expected = (
            "System requirements include Windows 10 or later, 8GB RAM minimum, "
            "and 500MB free disk space."
        )
        insert_document(
            title="Engineering User Manual",
            uploaded_by=user["_id"],
            text_content=(
                "The dashboard refreshes every 30 seconds. "
                f"{expected} "
                "Operators should keep the cabinet door closed."
            ),
        )

        response = client.post(
            "/api/ask",
            json={"question": "What are the system requirements?"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["success"] is True
        assert payload["data"]["question"] == "What are the system requirements?"
        assert payload["data"]["answer"] == expected
        assert payload["data"]["source"]["document"] == "engineering-user-manual.txt"
        assert payload["data"]["source"]["chunk_id"] == 1
        assert payload["data"]["confidence"] > 0

    def test_ask_expands_procedural_intro_to_following_steps(
        self,
        client,
        auth_headers,
        registered_user,
    ):
        user = database.db.users.find_one({"email": registered_user["email"]})
        expected = (
            "Below is a step by step process to install Ubuntu. "
            "Step 1: Download the Ubuntu ISO file from the official website. "
            "Step 2: Create a bootable USB drive using Rufus. "
            "Step 3: Restart the system and boot from the USB drive."
        )
        insert_document(
            title="Ubuntu Installation",
            uploaded_by=user["_id"],
            text_content=(
                expected
                + " Step 4: Follow the installer prompts to complete setup."
            ),
        )

        response = client.post(
            "/api/ask",
            json={"question": "How to install Ubuntu?"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.get_json()["data"]
        assert data["answer"] == expected
        assert data["source"] == {
            "document": "ubuntu-installation.txt",
            "chunk_id": 1,
        }
        assert data["confidence"] > 0

    def test_ask_requires_authentication(self, client):
        response = client.post(
            "/api/ask",
            json={"question": "What is the minimum RAM?"},
        )

        assert response.status_code == 401

    def test_ask_requires_question(self, client, auth_headers):
        response = client.post("/api/ask", json={}, headers=auth_headers)

        assert response.status_code == 400
        assert response.get_json()["error"] == "question is required"

    def test_ask_rejects_empty_question(self, client, auth_headers):
        response = client.post(
            "/api/ask",
            json={"question": "   "},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert response.get_json()["error"] == "question is required"

    def test_ask_returns_null_when_no_relevant_answer(
        self,
        client,
        auth_headers,
        registered_user,
    ):
        user = database.db.users.find_one({"email": registered_user["email"]})
        insert_document(
            title="Pump Manual",
            uploaded_by=user["_id"],
            text_content="Pump seal pressure requires weekly inspection.",
        )

        response = client.post(
            "/api/ask",
            json={"question": "What is the cafeteria menu?"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.get_json() == {
            "success": True,
            "data": {
                "question": "What is the cafeteria menu?",
                "answer": None,
                "source": None,
                "confidence": 0,
            },
        }

    def test_ask_retrieves_across_multiple_documents(
        self,
        client,
        auth_headers,
        registered_user,
    ):
        user = database.db.users.find_one({"email": registered_user["email"]})
        insert_document(
            title="Pump Manual",
            uploaded_by=user["_id"],
            text_content="Pump seal pressure requires weekly inspection.",
        )
        compressor_id = insert_document(
            title="Compressor Guide",
            uploaded_by=user["_id"],
            text_content=(
                "Compressor vibration above 12 mm/s requires immediate shutdown. "
                "Log the event after shutdown."
            ),
        )

        response = client.post(
            "/api/ask",
            json={"question": "When does compressor vibration require shutdown?"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.get_json()["data"]
        assert data["answer"] == (
            "Compressor vibration above 12 mm/s requires immediate shutdown."
        )
        assert data["source"]["document"] == "compressor-guide.txt"
        assert database.db.documents.find_one({"_id": compressor_id})

    def test_ask_retrieves_documents_uploaded_by_other_users(
        self,
        client,
        auth_headers,
        registered_user,
    ):
        first_user = database.db.users.find_one({"email": registered_user["email"]})
        client.post(
            "/api/auth/register",
            json={
                "email": "other@example.com",
                "password": "password123",
                "name": "Other User",
            },
        )
        other_user = database.db.users.find_one({"email": "other@example.com"})
        insert_document(
            title="Pump Manual",
            uploaded_by=first_user["_id"],
            text_content="Pump seal pressure requires weekly inspection.",
        )
        insert_document(
            title="Remote Compressor Guide",
            uploaded_by=other_user["_id"],
            text_content=(
                "Remote compressor filters must be replaced every 400 hours."
            ),
        )

        response = client.post(
            "/api/ask",
            json={"question": "When must remote compressor filters be replaced?"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.get_json()["data"]
        assert data["answer"] == (
            "Remote compressor filters must be replaced every 400 hours."
        )
        assert data["source"]["document"] == "remote-compressor-guide.txt"

    def test_ask_only_uses_processed_documents(
        self,
        client,
        auth_headers,
        registered_user,
    ):
        user = database.db.users.find_one({"email": registered_user["email"]})
        insert_document(
            title="Processed Guide",
            uploaded_by=user["_id"],
            text_content="Processed pump calibration requires a 5 Nm torque wrench.",
            processed=True,
            status="processed",
        )
        insert_document(
            title="Draft Guide",
            uploaded_by=user["_id"],
            text_content="Draft pump calibration requires a 99 Nm torque wrench.",
            processed=False,
            status="pending",
        )

        response = client.post(
            "/api/ask",
            json={"question": "What torque wrench does pump calibration require?"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.get_json()["data"]["answer"] == (
            "Processed pump calibration requires a 5 Nm torque wrench."
        )

    def test_ask_returns_source_document_and_chunk_id(
        self,
        client,
        auth_headers,
        registered_user,
    ):
        user = database.db.users.find_one({"email": registered_user["email"]})
        chunks = [
            {
                "chunk_id": 2,
                "text": "Hydraulic oil temperature must stay below 85 C.",
                "word_count": 8,
            }
        ]
        insert_document(
            title="Hydraulic Limits",
            uploaded_by=user["_id"],
            text_content="Hydraulic oil temperature must stay below 85 C.",
            chunks=chunks,
        )

        response = client.post(
            "/api/ask",
            json={"question": "What is the hydraulic oil temperature limit?"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        source = response.get_json()["data"]["source"]
        assert source == {
            "document": "hydraulic-limits.txt",
            "chunk_id": 2,
        }

    def test_ask_confidence_score_is_present(
        self,
        client,
        auth_headers,
        registered_user,
    ):
        user = database.db.users.find_one({"email": registered_user["email"]})
        insert_document(
            title="Valve Manual",
            uploaded_by=user["_id"],
            text_content="Valve actuator pressure must remain under 90 PSI.",
        )

        response = client.post(
            "/api/ask",
            json={"question": "What pressure must valve actuator remain under?"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        confidence = response.get_json()["data"]["confidence"]
        assert isinstance(confidence, float)
        assert confidence > 0
