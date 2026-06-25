from datetime import datetime, timezone

import app.database as database
from app.services.retrieval import chunk_text


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
