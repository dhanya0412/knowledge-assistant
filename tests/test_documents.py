import os
from io import BytesIO

import app.database as database


DEFAULT_CONTENT = (
    b"Pump maintenance requires pressure inspection. "
    b"Seal pressure and pump vibration should be monitored weekly."
)


def upload_file(client, auth_headers, filename="manual.txt", content=DEFAULT_CONTENT, **fields):
    data = {
        "file": (BytesIO(content), filename),
        **fields,
    }
    return client.post(
        "/api/documents/upload",
        data=data,
        headers=auth_headers,
        content_type="multipart/form-data",
    )


class TestDocumentUpload:
    def test_upload_success(self, client, auth_headers):
        response = upload_file(
            client,
            auth_headers,
            title="Pump Manual",
            tags="pump, manual, engineering",
        )

        assert response.status_code == 201
        data = response.get_json()
        document = data["document"]

        assert data["message"] == "document uploaded successfully"
        assert document["title"] == "Pump Manual"
        assert document["original_filename"] == "manual.txt"
        assert document["filename"] != "manual.txt"
        assert document["filename"].endswith(".txt")
        assert document["tags"] == ["pump", "manual", "engineering"]
        assert document["processed"] is True
        assert document["text_content"] == DEFAULT_CONTENT.decode("utf-8")
        assert document["keywords"]
        assert document["summary"]
        assert "filepath" in document
        assert database.db.documents.count_documents({}) == 1

        stored_document = database.db.documents.find_one({})
        assert stored_document["processed"] is True
        assert stored_document["text_content"] == document["text_content"]
        assert stored_document["keywords"] == document["keywords"]
        assert stored_document["summary"] == document["summary"]

    def test_upload_cleans_text_before_insert(self, client, auth_headers):
        response = upload_file(
            client,
            auth_headers,
            content=(
                b" Pump   manual\r\n\r\n\r\n"
                b"Check\tpressure before startup. "
                b"Pump pressure requires inspection."
            ),
        )

        assert response.status_code == 201
        document = response.get_json()["document"]
        assert document["text_content"] == (
            "Pump manual\n\n"
            "Check pressure before startup. Pump pressure requires inspection."
        )
        assert document["processed"] is True

    def test_upload_rejects_empty_document_without_insert(self, client, auth_headers, app):
        response = upload_file(
            client,
            auth_headers,
            content=b"   \n\t\n",
        )

        assert response.status_code == 400
        assert response.get_json()["error"] == "no extractable text found"
        assert database.db.documents.count_documents({}) == 0
        assert os.listdir(app.config["UPLOAD_FOLDER"]) == []

    def test_upload_requires_authentication(self, client):
        response = client.post(
            "/api/documents/upload",
            data={"file": (BytesIO(b"hello"), "manual.txt")},
            content_type="multipart/form-data",
        )

        assert response.status_code == 401

    def test_upload_rejects_missing_file(self, client, auth_headers):
        response = client.post(
            "/api/documents/upload",
            data={},
            headers=auth_headers,
            content_type="multipart/form-data",
        )

        assert response.status_code == 400
        assert response.get_json()["error"] == "file is required"

    def test_upload_rejects_empty_filename(self, client, auth_headers):
        response = upload_file(client, auth_headers, filename="")

        assert response.status_code == 400
        assert response.get_json()["error"] == "filename is required"

    def test_upload_rejects_unsupported_file_type(self, client, auth_headers):
        response = upload_file(client, auth_headers, filename="manual.exe")

        assert response.status_code == 400
        assert response.get_json()["error"] == "file type is not allowed"


class TestDocumentList:
    def test_list_documents_returns_only_current_user_documents(self, client, auth_headers):
        upload_file(client, auth_headers, filename="first.txt", title="First")

        client.post(
            "/api/auth/register",
            json={
                "email": "other@example.com",
                "password": "password123",
                "name": "Other User",
            },
        )
        login_response = client.post(
            "/api/auth/login",
            json={
                "email": "other@example.com",
                "password": "password123",
            },
        )
        other_headers = {
            "Authorization": f"Bearer {login_response.get_json()['token']}"
        }
        upload_file(client, other_headers, filename="second.txt", title="Second")

        response = client.get("/api/documents", headers=auth_headers)

        assert response.status_code == 200
        documents = response.get_json()["documents"]
        assert len(documents) == 1
        assert documents[0]["title"] == "First"
        assert "filepath" not in documents[0]
        assert "text_content" not in documents[0]


class TestDocumentDetail:
    def test_get_document_success(self, client, auth_headers):
        upload_response = upload_file(client, auth_headers, title="Pump Manual")
        document_id = upload_response.get_json()["document"]["id"]

        response = client.get(f"/api/documents/{document_id}", headers=auth_headers)

        assert response.status_code == 200
        document = response.get_json()["document"]
        assert document["id"] == document_id
        assert document["title"] == "Pump Manual"
        assert "filepath" in document

    def test_get_document_returns_not_found_for_unknown_document(self, client, auth_headers):
        response = client.get("/api/documents/000000000000000000000000", headers=auth_headers)

        assert response.status_code == 404
        assert response.get_json()["error"] == "document not found"


class TestDocumentDelete:
    def test_delete_document_success(self, client, auth_headers):
        upload_response = upload_file(client, auth_headers)
        document = upload_response.get_json()["document"]

        response = client.delete(
            f"/api/documents/{document['id']}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.get_json()["message"] == "document deleted successfully"
        assert database.db.documents.count_documents({}) == 0

    def test_delete_document_returns_not_found_for_unknown_document(self, client, auth_headers):
        response = client.delete(
            "/api/documents/000000000000000000000000",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert response.get_json()["error"] == "document not found"
