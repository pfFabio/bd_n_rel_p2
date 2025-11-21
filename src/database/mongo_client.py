from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import os
import time

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = "corridas_db"
COLLECTION_NAME = "corridas"

class MongoClientSingleton:
    _instance = None
    client = None
    db = None
    collection = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoClientSingleton, cls).__new__(cls)
        return cls._instance

    def connect(self):
        retries = 5
        while retries > 0:
            try:
                self.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
                self.client.admin.command('ismaster')
                print("Successfully connected to MongoDB.")
                self.db = self.client[DB_NAME]
                self.collection = self.db[COLLECTION_NAME]
                return
            except ConnectionFailure:
                retries -= 1
                print(f"Could not connect to MongoDB. Retrying in 5 seconds... ({retries} retries left)")
                time.sleep(5)
        raise ConnectionFailure("Could not connect to MongoDB after several retries.")

    def close(self):
        if self.client:
            self.client.close()
            print("MongoDB connection closed.")

def get_mongo_collection():
    if MongoClientSingleton().collection is None:
        # This will happen if the startup event fails.
        # We can either raise an exception or handle it gracefully.
        # For now, let's raise a clear exception.
        raise Exception("MongoDB collection not initialized. The application might not have started correctly.")
    return MongoClientSingleton().collection
