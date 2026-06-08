from pymongo import MongoClient

client = None
db = None


def init_db(app):
    global client
    global db

    client = MongoClient(
        app.config["MONGO_URI"]
    )

    db = client["knowledge_db"]
    db.users.create_index("email", unique=True)