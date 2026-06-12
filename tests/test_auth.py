class TestRegister:
    def test_register_success(self, client):
        response = client.post(
            "/api/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "password123",
                "name": "New User",
            },
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data["message"] == "user registered successfully"
        assert data["user"]["email"] == "newuser@example.com"
        assert data["user"]["name"] == "New User"
        assert "id" in data["user"]
        assert "password" not in data["user"]

    def test_register_duplicate_email(self, client, registered_user):
        response = client.post(
            "/api/auth/register",
            json={
                "email": registered_user["email"],
                "password": "password123",
                "name": "Another User",
            },
        )

        assert response.status_code == 409
        assert response.get_json()["error"] == "email already registered"

    def test_register_missing_fields(self, client):
        response = client.post("/api/auth/register", json={})

        assert response.status_code == 400
        assert "error" in response.get_json()


class TestLogin:
    def test_login_success(self, client, registered_user):
        response = client.post(
            "/api/auth/login",
            json={
                "email": registered_user["email"],
                "password": registered_user["password"],
            },
        )

        assert response.status_code == 200
        data = response.get_json()
        assert "token" in data
        assert data["user"]["email"] == registered_user["email"]
        assert "password" not in data["user"]

    def test_login_wrong_password(self, client, registered_user):
        response = client.post(
            "/api/auth/login",
            json={
                "email": registered_user["email"],
                "password": "wrongpassword",
            },
        )

        assert response.status_code == 401
        assert response.get_json()["error"] == "invalid email or password"

    def test_login_unknown_email(self, client):
        response = client.post(
            "/api/auth/login",
            json={
                "email": "unknown@example.com",
                "password": "password123",
            },
        )

        assert response.status_code == 401
        assert response.get_json()["error"] == "invalid email or password"


class TestJWTProtection:
    def test_protected_with_valid_token(self, client, auth_headers):
        response = client.get("/api/test/protected", headers=auth_headers)

        assert response.status_code == 200
        assert response.get_json()["message"] == "authenticated"

    def test_protected_without_token(self, client):
        response = client.get("/api/test/protected")

        assert response.status_code == 401

    def test_protected_with_expired_token(self, client, app):
        from datetime import timedelta

        from flask_jwt_extended import create_access_token

        with app.app_context():
            expired_token = create_access_token(
                identity="fake-user-id",
                expires_delta=timedelta(seconds=-1),
            )

        response = client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {expired_token}"},
        )

        assert response.status_code == 401

    def test_protected_with_invalid_token(self, client, app):
        from datetime import timedelta

        from flask_jwt_extended import create_access_token

        with app.app_context():
            expired_token = create_access_token(
                identity="fake-user-id",
                expires_delta=timedelta(seconds=-1),
            )

        response = client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {expired_token}"},
        )

        assert response.status_code == 401
