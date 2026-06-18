from datetime import datetime, timezone

import app.database as database


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
        data = response.get_json()
        assert data["query"] == "pump seal"
        assert data["count"] == 1

        result = data["results"][0]
        assert result["title"] == "Pump Maintenance Manual"
        assert result["keywords"] == ["pump", "seal", "pressure"]
        assert result["uploaded_by"] == str(user["_id"])
        assert result["uploaded_by_name"] == registered_user["name"]
        assert result["score"] > 0
        assert "filepath" not in result
        assert "text_content" not in result

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
        results = response.get_json()["results"]
        assert results[0]["id"] == str(relevant_id)

    def test_search_ranking_uses_weighted_title_and_keywords(
        self,
        client,
        auth_headers,
        registered_user,
    ):
        user = database.db.users.find_one({"email": registered_user["email"]})
        titled_document_id = insert_document(
            title="Pump Manual",
            uploaded_by=user["_id"],
            text_content="Very short.",
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
        results = response.get_json()["results"]
        assert results[0]["id"] == str(titled_document_id)

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
            "results": [],
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
        results = response.get_json()["results"]
        assert len(results) == 1
        assert results[0]["id"] == str(second_document_id)
        assert results[0]["uploaded_by"] == str(second_user["_id"])
        assert results[0]["uploaded_by_name"] == "Other User"

    def test_search_only_includes_processed_documents(
        self,
        client,
        auth_headers,
        registered_user,
    ):
        user = database.db.users.find_one({"email": registered_user["email"]})
        insert_document(
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
        titles = [result["title"] for result in response.get_json()["results"]]
        assert titles == ["Processed Pump Guide"]

    def test_search_rejects_invalid_limit(self, client, auth_headers):
        response = client.get("/api/search?q=pump&limit=zero", headers=auth_headers)

        assert response.status_code == 400
        assert response.get_json()["error"] == "limit must be a positive integer"
