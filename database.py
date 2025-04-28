from pymongo import MongoClient
from config import MONGO_URI, MONGO_DB_NAME
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.client = MongoClient(MONGO_URI)
        self.db = self.client[MONGO_DB_NAME]
        self.users = self.db.users
        self.chats = self.db.chats

    def add_user(self, user_id):
        logger.info(f"Adding user {user_id} to database")
        result = self.users.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id}},
            upsert=True
        )
        logger.info(f"User {user_id} added/updated, matched={result.matched_count}, modified={result.modified_count}")

    def get_user_count(self):
        count = self.users.count_documents({})
        logger.info(f"Retrieved user count: {count}")
        return count

    def get_all_users(self):
        users = [doc["user_id"] for doc in self.users.find({}, {"user_id": 1})]
        logger.info(f"Retrieved {len(users)} users")
        return users

    def add_chat(self, chat_id, admin_ids=None, title=None, bot_id=None, bot_admin_status=False):
        logger.info(f"Adding chat {chat_id} with admin_ids={admin_ids}, title={title}, bot_id={bot_id}, bot_admin_status={bot_admin_status}")
        update_data = {"chat_id": chat_id}
        if admin_ids:
            update_data["admin_ids"] = admin_ids
        if title:
            update_data["title"] = title
        if bot_id:
            update_data["bot_id"] = bot_id
        update_data["bot_admin_status"] = bot_admin_status
        result = self.chats.update_one(
            {"chat_id": chat_id},
            {"$set": update_data, "$setOnInsert": {"settings": {}}},
            upsert=True
        )
        logger.info(f"Chat {chat_id} added/updated, matched={result.matched_count}, modified={result.modified_count}")

    def get_chat_count(self):
        count = self.chats.count_documents({})
        logger.info(f"Retrieved chat count: {count}")
        return count

    def get_chat_settings(self, chat_id):
        logger.info(f"Retrieving settings for chat {chat_id}")
        chat = self.chats.find_one({"chat_id": chat_id})
        logger.info(f"Settings retrieved for chat {chat_id}: {chat}")
        return chat if chat else {}

    def update_chat_settings(self, chat_id, settings):
        logger.info(f"Updating settings for chat {chat_id}: {settings}")
        result = self.chats.update_one(
            {"chat_id": chat_id},
            {"$set": settings},
            upsert=True
        )
        logger.info(f"Settings updated for chat {chat_id}, matched={result.matched_count}, modified={result.modified_count}")

    def get_all_chats_for_user(self, user_id):
        chats = list(self.chats.find({"admin_ids": user_id}))
        logger.info(f"Retrieved {len(chats)} chats for user {user_id}: {chats}")
        return chats

    def get_all_chats(self):
        chats = list(self.chats.find({}))
        logger.info(f"Retrieved {len(chats)} chats: {chats}")
        return chats

    def remove_chat(self, chat_id):
        logger.info(f"Removing chat {chat_id} from database")
        result = self.chats.delete_one({"chat_id": chat_id})
        logger.info(f"Chat {chat_id} removed, deleted_count={result.deleted_count}")
