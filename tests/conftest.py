import os
import shutil

import pytest
from flask import Blueprint, jsonify

os.environ.setdefault("MONGO_DB_NAME", "knowledge_db_test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-bytes-minimum!!")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-32bytes-min!!")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")

from app import create_app
from app.middleware.auth_middleware import token_required

test_bp = Blueprint("test", __name__)


@test_bp.route("/protected", methods=["GET"])
@token_required
def test_protected():
    return jsonify({"message": "authenticated"}), 200


@pytest.fixture
def app():
    application = create_app()
    application.config["TESTING"] = True
    application.config["UPLOAD_FOLDER"] = os.path.abspath(
        os.path.join(os.getcwd(), "uploads", "test")
    )
    application.register_blueprint(test_bp, url_prefix="/api/test")
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def clean_users(app):
    import app.database as database

    database.db.users.delete_many({})
    database.db.documents.delete_many({})
    shutil.rmtree(app.config["UPLOAD_FOLDER"], ignore_errors=True)
    yield
    database.db.users.delete_many({})
    database.db.documents.delete_many({})
    shutil.rmtree(app.config["UPLOAD_FOLDER"], ignore_errors=True)


@pytest.fixture
def registered_user(client):
    payload = {
        "email": "test@example.com",
        "password": "password123",
        "name": "Test User",
    }
    response = client.post("/api/auth/register", json=payload)
    return {**payload, "response": response}


@pytest.fixture
def auth_token(client, registered_user):
    response = client.post(
        "/api/auth/login",
        json={
            "email": registered_user["email"],
            "password": registered_user["password"],
        },
    )
    return response.get_json()["token"]


@pytest.fixture
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}
