import re
from datetime import datetime, timezone


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8


def validate_registration_data(email, password, name):
    errors = []

    if not name or not str(name).strip():
        errors.append("name is required")
    elif len(str(name).strip()) < 2:
        errors.append("name must be at least 2 characters")

    if not email or not str(email).strip():
        errors.append("email is required")
    elif not EMAIL_PATTERN.match(str(email).strip().lower()):
        errors.append("email format is invalid")

    if not password:
        errors.append("password is required")
    elif len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"password must be at least {MIN_PASSWORD_LENGTH} characters")

    return errors


def create_user_document(email, password_hash, name):
    return {
        "email": email.strip().lower(),
        "password": password_hash,
        "name": name.strip(),
        "created_at": datetime.now(timezone.utc),
    }


def user_to_dict(user):
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "name": user["name"],
        "created_at": user["created_at"].isoformat(),
    }
