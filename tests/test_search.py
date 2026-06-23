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
    keywords=None,
    processed=True,
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
        "chunks": _build_stored_chunks(text_content),
        "keywords": keywords or [],
        "summary": f"Summary for {title}",
        "processed": processed,
    }

    result = database.db.documents.insert_one(document)
    return result.inserted_id


def register_and_login(client, *, email, name="Other User"):
    password = "password123"
    client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": password,
            "name": name,
        },
    )
    login_response = client.post(
        "/api/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )
    user = database.db.users.find_one({"email": email})
    headers = {
        "Authorization": f"Bearer {login_response.get_json()['token']}"
    }
    return user, headers


class TestSearch:
    def test_search_returns_ranked_results_without_sensitive_fields(
        self,
        client,
        auth_headers,
        registered_user,
    ):
        user = database.db.users.find_one({"email": registered_user["email"]})
        insert_document(
            title="Pump Maintenance Manual",
            uploaded_by=user["_id"],
            text_content="Pump seal pressure requires weekly inspection.",
            keywords=["pump", "seal", "pressure"],
        )
        insert_document(
            title="Boiler Startup Notes",
            uploaded_by=user["_id"],
            text_content="Boiler startup requires water level verification.",
            keywords=["boiler", "startup"],
        )

        response = client.get("/api/search?q=pump%20seal", headers=auth_headers)

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["query"] == "pump seal"
        assert payload["count"] == 1
        assert payload["success"] is True

        result = payload["data"][0]
        assert result["document_id"]
        assert result["matched_chunk"]
        assert result["chunk_id"] == 1
        assert result["filename"] == "pump-maintenance-manual.txt"
        assert result["relevance_score"] > 0
        assert "filepath" not in result
        assert "text_content" not in result
        assert "title" not in result
        assert "keywords" not in result

    def test_search_ranks_more_relevant_document_first(
        self,
        client,
        auth_headers,
        registered_user,
    ):
        user = database.db.users.find_one({"email": registered_user["email"]})
        relevant_id = insert_document(
            title="Pump Seal Pressure Guide",
            uploaded_by=user["_id"],
            text_content=(
                "Pump seal pressure maintenance requires pump pressure "
                "inspection and seal vibration monitoring."
            ),
            keywords=["pump", "seal", "pressure"],
        )
        insert_document(
            title="General Engineering Notes",
            uploaded_by=user["_id"],
            text_content="The pump appears once in these unrelated notes.",
            keywords=["engineering"],
        )

        response = client.get(
            "/api/search?q=pump%20seal%20pressure",
            headers=auth_headers,
        )

        assert response.status_code == 200
        results = response.get_json()["data"]
        assert results[0]["document_id"] == str(relevant_id)

    def test_search_ranks_chunk_with_stronger_term_overlap_first(
        self,
        client,
        auth_headers,
        registered_user,
    ):
        user = database.db.users.find_one({"email": registered_user["email"]})
        relevant_id = insert_document(
            title="Pump Manual",
            uploaded_by=user["_id"],
            text_content=(
                "Pump manual covers pump maintenance and pump pressure checks."
            ),
            keywords=["pump", "manual"],
        )
        insert_document(
            title="Engineering Notes",
            uploaded_by=user["_id"],
            text_content="Contains pump once.",
            keywords=["engineering"],
        )

        response = client.get(
            "/api/search?q=pump%20manual",
            headers=auth_headers,
        )

        assert response.status_code == 200
        results = response.get_json()["data"]
        assert results[0]["document_id"] == str(relevant_id)

    def test_search_requires_authentication(self, client):
        response = client.get("/api/search?q=pump")

        assert response.status_code == 401

    def test_search_requires_query(self, client, auth_headers):
        response = client.get("/api/search", headers=auth_headers)

        assert response.status_code == 400
        assert response.get_json()["error"] == "search query is required"

    def test_search_rejects_empty_query(self, client, auth_headers):
        response = client.get("/api/search?q=%20%20%20", headers=auth_headers)

        assert response.status_code == 400
        assert response.get_json()["error"] == "search query is required"

    def test_search_returns_empty_results_when_nothing_matches(
        self,
        client,
        auth_headers,
        registered_user,
    ):
        user = database.db.users.find_one({"email": registered_user["email"]})
        insert_document(
            title="Boiler Startup Notes",
            uploaded_by=user["_id"],
            text_content="Boiler startup requires water level verification.",
            keywords=["boiler", "startup"],
        )

        response = client.get("/api/search?q=compressor", headers=auth_headers)

        assert response.status_code == 200
        assert response.get_json() == {
            "query": "compressor",
            "count": 0,
            "success": True,
            "data": [],
        }

    def test_search_spans_documents_uploaded_by_different_users(
        self,
        client,
        auth_headers,
        registered_user,
    ):
        first_user = database.db.users.find_one({"email": registered_user["email"]})
        second_user, _second_headers = register_and_login(
            client,
            email="other@example.com",
            name="Other User",
        )
        insert_document(
            title="Pump Manual",
            uploaded_by=first_user["_id"],
            text_content="Pump maintenance instructions.",
            keywords=["pump"],
        )
        second_document_id = insert_document(
            title="Compressor Guide",
            uploaded_by=second_user["_id"],
            text_content="Compressor vibration troubleshooting.",
            keywords=["compressor", "vibration"],
        )

        response = client.get("/api/search?q=compressor", headers=auth_headers)

        assert response.status_code == 200
        results = response.get_json()["data"]
        assert len(results) == 1
        assert results[0]["document_id"] == str(second_document_id)

    def test_search_only_includes_processed_documents(
        self,
        client,
        auth_headers,
        registered_user,
    ):
        user = database.db.users.find_one({"email": registered_user["email"]})
        processed_id = insert_document(
            title="Processed Pump Guide",
            uploaded_by=user["_id"],
            text_content="Processed pump instructions.",
            keywords=["pump"],
            processed=True,
        )
        insert_document(
            title="Draft Pump Notes",
            uploaded_by=user["_id"],
            text_content="Draft pump instructions.",
            keywords=["pump"],
            processed=False,
        )

        response = client.get("/api/search?q=pump", headers=auth_headers)

        assert response.status_code == 200
        results = response.get_json()["data"]
        assert len(results) == 1
        assert results[0]["document_id"] == str(processed_id)

    def test_search_rejects_invalid_limit(self, client, auth_headers):
        response = client.get("/api/search?q=pump&limit=zero", headers=auth_headers)

        assert response.status_code == 400
        assert response.get_json()["error"] == "limit must be a positive integer"
