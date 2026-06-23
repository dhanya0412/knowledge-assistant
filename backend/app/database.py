from pymongo import MongoClient

client = None
db = None


def init_db(app):
    global client
    global db

    client = MongoClient(
        app.config["MONGO_URI"]
    )

    db = client[app.config["MONGO_DB_NAME"]]
    db.users.create_index("email", unique=True)
    db.documents.create_index([("text_content", "text")])
