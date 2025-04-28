from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure
import logging
import time

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, max_retries=3, retry_delay=5):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.client = None
        self.db = None
        self.chats = None
        self.users = None
        self.connect()

    def connect(self):
        """Attempt to connect to MongoDB with retries."""
        try:
            from config import MONGO_URI
        except ImportError:
            MONGO_URI = 'mongodb://localhost:27017/'  # Fallback to default

        for attempt in range(self.max_retries):
            try:
                logger.info(f"Attempting to connect to MongoDB at {MONGO_URI} (attempt {attempt + 1}/{self.max_retries})")
                self.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
                self.client.admin.command('ping')
                self.db = self.client['all_in_one']
                self.chats = self.db['chats']
                self.users = self.db['users']
                logger.info(f"Successfully connected to MongoDB at {MONGO_URI}")
                return
            except (ServerSelectionTimeoutError, ConnectionFailure) as e:
                logger.error(f"MongoDB connection attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    logger.info(f"Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error("Failed to connect to MongoDB after retries. Database operations will fail.")
                    raise ConnectionFailure(f"Could not connect to MongoDB at {MONGO_URI}. Please ensure the MongoDB service is running and the connection string is correct.")

    def add_user(self, user_id: int):
        logger.info(f"Adding user {user_id} to database")
        try:
            self.users.update_one(
                {'user_id': user_id},
                {'$set': {'user_id': user_id}},
                upsert=True
            )
            logger.info(f"User {user_id} added or updated in database")
        except Exception as e:
            logger.error(f"Failed to add user {user_id} to database: {e}")
            raise

    def is_user_exists(self, user_id: int) -> bool:
        logger.info(f"Checking if user {user_id} exists in database")
        try:
            return self.users.find_one({'user_id': user_id}) is not None
        except Exception as e:
            logger.error(f"Failed to check if user {user_id} exists: {e}")
            raise

    def get_user_count(self):
        logger.info("Retrieving total user count")
        try:
            return self.users.count_documents({})
        except Exception as e:
            logger.error(f"Failed to retrieve user count: {e}")
            raise

    def get_all_users(self):
        logger.info("Retrieving all users")
        try:
            return [user['user_id'] for user in self.users.find()]
        except Exception as e:
            logger.error(f"Failed to retrieve all users: {e}")
            raise

    def add_chat(self, chat_id: int, admin_ids: list, title: str, bot_id: int, bot_admin_status: bool):
        logger.info(f"Adding chat {chat_id} to database")
        try:
            self.chats.update_one(
                {'chat_id': chat_id},
                {
                    '$set': {
                        'chat_id': chat_id,
                        'admin_ids': admin_ids,
                        'title': title,
                        'bot_id': bot_id,
                        'bot_admin_status': bot_admin_status,
                        'settings': {
                            'auto_request': {
                                'accepted_users': []
                            }
                        }
                    }
                },
                upsert=True
            )
            logger.info(f"Chat {chat_id} added or updated in database")
        except Exception as e:
            logger.error(f"Failed to add chat {chat_id} to database: {e}")
            raise

    def get_chat_settings(self, chat_id: int):
        logger.info(f"Retrieving settings for chat {chat_id}")
        try:
            chat = self.chats.find_one({'chat_id': chat_id}) or {}
            logger.info(f"Settings retrieved for chat {chat_id}: {chat}")
            return chat
        except Exception as e:
            logger.error(f"Failed to retrieve settings for chat {chat_id}: {e}")
            raise

    def update_chat_settings(self, chat_id: int, settings_update: dict):
        logger.info(f"Updating settings for chat {chat_id}: {settings_update}")
        try:
            update_dict = {}
            for key, value in settings_update.items():
                if key in ["$set", "$push"]:
                    update_dict[key] = value
                else:
                    update_dict["$set"] = update_dict.get("$set", {})
                    update_dict["$set"][f"settings.{key}"] = value
            result = self.chats.update_one(
                {'chat_id': chat_id},
                update_dict,
                upsert=True
            )
            logger.info(f"Chat {chat_id} settings updated, matched: {result.matched_count}, modified: {result.modified_count}")
        except Exception as e:
            logger.error(f"Failed to update settings for chat {chat_id}: {e}")
            raise

    def get_all_chats(self):
        logger.info("Retrieving all chats")
        try:
            chats = list(self.chats.find())
            logger.info(f"Retrieved {len(chats)} chats")
            return chats
        except Exception as e:
            logger.error(f"Failed to retrieve all chats: {e}")
            raise

    def get_all_chats_for_user(self, user_id: int):
        logger.info(f"Retrieving chats for user {user_id}")
        try:
            chats = self.chats.find({'admin_ids': user_id})
            return list(chats)
        except Exception as e:
            logger.error(f"Failed to retrieve chats for user {user_id}: {e}")
            raise

    def get_chat_count(self):
        logger.info("Retrieving total chat count")
        try:
            return self.chats.count_documents({})
        except Exception as e:
            logger.error(f"Failed to retrieve chat count: {e}")
            raise
