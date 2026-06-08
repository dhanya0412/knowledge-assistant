from werkzeug.security import check_password_hash, generate_password_hash
from pymongo.errors import DuplicateKeyError

import app.database as database
from app.models.user import (
    create_user_document,
    user_to_dict,
    validate_registration_data,
)


class AuthError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def register_user(email, password, name):
    errors = validate_registration_data(email, password, name)
    if errors:
        raise AuthError(errors[0])

    password_hash = generate_password_hash(password)
    user_doc = create_user_document(email, password_hash, name)

    try:
        result = database.db.users.insert_one(user_doc)
    except DuplicateKeyError:
        raise AuthError("email already registered", status_code=409)

    user_doc["_id"] = result.inserted_id
    return user_to_dict(user_doc)


def login_user(email, password):
    if not email or not password:
        raise AuthError("email and password are required")

    user = database.db.users.find_one({"email": email.strip().lower()})
    if not user or not check_password_hash(user["password"], password):
        raise AuthError("invalid email or password", status_code=401)

    return user
