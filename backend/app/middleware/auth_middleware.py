from functools import wraps

from flask import g
from flask_jwt_extended import get_jwt_identity, jwt_required


def token_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        g.user_id = get_jwt_identity()
        return fn(*args, **kwargs)

    return wrapper
