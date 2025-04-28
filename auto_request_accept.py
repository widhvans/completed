import logging
import asyncio
from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import format_time
from pyrogram.errors.exceptions.bad_request_400 import MessageNotModified, UserNotParticipant, PeerIdInvalid
from pyrogram.errors import FloodWait

logger = logging.getLogger(__name__)

class AutoRequestAccept:
    def __init__(self, db):
        self.db = db
        self.pending = {}  # Store pending custom delay settings: {user_id: chat_id}
        self.pending_welcome = {}  # Store pending welcome message settings: {user_id: chat_id}

    async def handle_menu(self, client: Client, callback_query):
        chat_id = int(callback_query.data.split("_")[-1])
        user_id = callback_query.from_user.id
        logger.info(f"Auto-request menu requested for chat {chat_id} by user {user_id}")

        settings = self.db.get_chat_settings(chat_id).get("settings", {}).get("auto_request", {})
        delay = settings.get("delay", -1)  # -1 means manual
        delay_text = "Manual" if delay == -1 else format_time(delay)

        buttons = [
            [InlineKeyboardButton(f"Delay: {delay_text}", callback_data=f"autorequest_menu_{chat_id}")],
            [InlineKeyboardButton("Instant (0s)", callback_data=f"autorequest_instant_{chat_id}"),
             InlineKeyboardButton("5m", callback_data=f"autorequest_5min_{chat_id}")],
            [InlineKeyboardButton("10m", callback_data=f"autorequest_10min_{chat_id}"),
             InlineKeyboardButton("Manual", callback_data=f"autorequest_manual_{chat_id}")],
            [InlineKeyboardButton("Custom Time", callback_data=f"autorequest_custom_{chat_id}")],
            [InlineKeyboardButton("Set Welcome", callback_data=f"autorequest_welcome_{chat_id}")]
        ]
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="help")])
        reply_markup = InlineKeyboardMarkup(buttons)

        welcome_message = settings.get("welcome_message", "Not set")
        new_text = f"Configure auto-request settings for chat {chat_id}:\nCurrent delay: {delay_text}\nWelcome message: {welcome_message[:50]}{'...' if len(welcome_message) > 50 else ''}"

        try:
            if (callback_query.message.text != new_text or
                callback_query.message.reply_markup != reply_markup):
                await callback_query.message.edit(
                    new_text,
                    reply_markup=reply_markup
                )
            await callback_query.answer("Auto-request menu opened")
        except MessageNotModified:
            logger.debug(f"Message not modified for chat {chat_id}, same content")
            await callback_query.answer("Auto-request menu opened")
        except Exception as e:
            logger.error(f"Error editing auto-request menu for chat {chat_id}: {e}", exc_info=True)
            await callback_query.answer("Error updating menu", show_alert=True)
            return

        logger.info(f"Auto-request menu sent for chat {chat_id} to user {user_id}")

    async def set_delay(self, client: Client, callback_query, delay: int):
        chat_id = int(callback_query.data.split("_")[-1])
        user_id = callback_query.from_user.id
        logger.info(f"Setting auto-request delay to {delay} seconds for chat {chat_id} by user {user_id}")

        try:
            self.db.update_chat_settings(chat_id, {"auto_request.delay": delay})
            await callback_query.message.edit(
                f"Auto-request delay set to {format_time(delay) if delay >= 0 else 'Manual'} for chat {chat_id}.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"autorequest_menu_{chat_id}")]])
            )
            await callback_query.answer("Delay updated")
            logger.info(f"Auto-request delay set to {delay} seconds for chat {chat_id} by user {user_id}")
        except Exception as e:
            logger.error(f"Failed to set auto-request delay for chat {chat_id}: {e}", exc_info=True)
            await callback_query.answer("Error setting delay", show_alert=True)

    async def set_custom(self, client: Client, callback_query):
        chat_id = int(callback_query.data.split("_")[-1])
        user_id = callback_query.from_user.id
        logger.info(f"Setting custom auto-request delay for chat {chat_id} by user {user_id}")

        self.pending[user_id] = chat_id
        await callback_query.message.edit(
            "Please enter the custom delay (e.g., 5s for 5 seconds, 1m for 1 minute, 1h for 1 hour):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data=f"autorequest_cancel_{chat_id}")]])
        )
        await callback_query.answer("Enter custom delay")
        logger.info(f"Prompted user {user_id} to enter custom auto-request delay for chat {chat_id}")

    async def set_welcome(self, client: Client, callback_query):
        chat_id = int(callback_query.data.split("_")[-1])
        user_id = callback_query.from_user.id
        logger.info(f"Setting welcome message for chat {chat_id} by user {user_id}")

        self.pending_welcome[user_id] = chat_id
        await callback_query.message.edit(
            "Please enter the welcome message for new users (or send 'clear' to remove the message):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data=f"autorequest_cancel_{chat_id}")]])
        )
        await callback_query.answer("Enter welcome message")
        logger.info(f"Prompted user {user_id} to enter welcome message for chat {chat_id}")

    async def cancel_action(self, client: Client, callback_query):
        chat_id = int(callback_query.data.split("_")[-1])
        user_id = callback_query.from_user.id
        logger.info(f"Canceling auto-request action for chat {chat_id} by user {user_id}")

        if user_id in self.pending or user_id in self.pending_welcome:
            self.pending.pop(user_id, None)
            self.pending_welcome.pop(user_id, None)
            await callback_query.message.edit(
                "Action canceled. Returning to auto-request menu.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"autorequest_menu_{chat_id}")]])
            )
            await callback_query.answer("Action canceled")
            logger.info(f"Canceled pending action for user {user_id} in chat {chat_id}")
        else:
            logger.warning(f"No pending action to cancel for user {user_id} in chat {chat_id}")
            await callback_query.answer("No pending action to cancel.", show_alert=True)

    async def process_custom(self, client: Client, message, chat_id: int):
        user_id = message.from_user.id
        if user_id not in self.pending or self.pending[user_id] != chat_id:
            logger.warning(f"No pending auto-request custom delay action for user {user_id} in chat {chat_id}")
            await message.reply("No pending auto-request custom delay action.")
            return False

        input_text = message.text.lower().strip()
        try:
            if input_text.endswith("s"):
                delay = int(input_text[:-1])
            elif input_text.endswith("m"):
                delay = int(input_text[:-1]) * 60
            elif input_text.endswith("h"):
                delay = int(input_text[:-1]) * 3600
            else:
                delay = int(input_text)  # Assume seconds if no suffix
            if delay < 0:
                raise ValueError("Delay cannot be negative")
        except ValueError:
            logger.warning(f"Invalid custom delay input by user {user_id} for chat {chat_id}: {input_text}")
            await message.reply(
                "Invalid input. Please enter a non-negative time (e.g., 5s for 5 seconds, 1m for 1 minute, 1h for 1 hour).",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data=f"autorequest_cancel_{chat_id}")]])
            )
            return False

        try:
            self.db.update_chat_settings(chat_id, {"auto_request.delay": delay})
            self.pending.pop(user_id)
            await message.reply(
                f"Custom auto-request delay set to {format_time(delay)} for chat {chat_id}.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"autorequest_menu_{chat_id}")]])
            )
            logger.info(f"Custom auto-request delay set to {delay} seconds for chat {chat_id} by user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to set custom auto-request delay for chat {chat_id}: {e}", exc_info=True)
            await message.reply("Error setting custom delay.")
            return False

    async def process_welcome(self, client: Client, message, chat_id: int):
        user_id = message.from_user.id
        if user_id not in self.pending_welcome or self.pending_welcome[user_id] != chat_id:
            logger.info(f"No pending welcome message action for user {user_id} in chat {chat_id}, ignoring message")
            return False

        message_text = message.text.strip()
        try:
            if message_text.lower() == "clear":
                self.db.update_chat_settings(chat_id, {"auto_request.welcome_message": None})
                response = f"Welcome message cleared for chat {chat_id}."
            else:
                self.db.update_chat_settings(chat_id, {"auto_request.welcome_message": message_text})
                response = f"Welcome message set for chat {chat_id}."

            self.pending_welcome.pop(user_id)
            await message.reply(
                response,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"autorequest_menu_{chat_id}")]])
            )
            logger.info(f"{response} by user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to process welcome message for chat {chat_id}: {e}", exc_info=True)
            await message.reply("Error setting welcome message.")
            return False

    async def handle_request(self, client: Client, chat_id: int, user_id: int, start_func):
        logger.info(f"Starting join request handling for chat {chat_id} from user {user_id}")
        try:
            # Retrieve settings
            logger.info(f"Retrieving settings for chat {chat_id}")
            settings = self.db.get_chat_settings(chat_id).get("settings", {}).get("auto_request", {})
            logger.info(f"Settings retrieved: {settings}")
            delay = settings.get("delay", -1)  # -1 means manual
            welcome_message = settings.get("welcome_message", None)
            logger.info(f"Delay: {delay}, Welcome message: {welcome_message}")

            if delay == -1:
                logger.info(f"Manual mode enabled for chat {chat_id}, skipping auto-accept for user {user_id}")
                return

            # Apply delay if set
            if delay > 0:
                logger.info(f"Delaying auto-accept for user {user_id} in chat {chat_id} by {delay} seconds")
                await asyncio.sleep(delay)
            
            # Accept the join request
            logger.info(f"Attempting to accept join request for user {user_id} in chat {chat_id}")
            try:
                await client.approve_chat_join_request(chat_id, user_id)
                logger.info(f"Successfully auto-accepted user {user_id} in chat {chat_id}")
            except UserNotParticipant as e:
                logger.error(f"Cannot accept join request for user {user_id} in chat {chat_id}: {e}", exc_info=True)
                return
            except FloodWait as e:
                logger.warning(f"Flood wait triggered for user {user_id} in chat {chat_id}, waiting {e.value} seconds")
                await asyncio.sleep(e.value)
                await client.approve_chat_join_request(chat_id, user_id)
                logger.info(f"Successfully auto-accepted user {user_id} in chat {chat_id} after flood wait")
            except Exception as e:
                logger.error(f"Unexpected error accepting join request for user {user_id} in chat {chat_id}: {e}", exc_info=True)
                return

            # Send welcome message to all users immediately after approval
            if welcome_message:
                try:
                    logger.info(f"Sending welcome message to user {user_id}: {welcome_message}")
                    await client.send_message(user_id, welcome_message)
                    logger.info(f"Successfully sent welcome message to user {user_id} for chat {chat_id}")
                except PeerIdInvalid:
                    logger.error(f"Cannot send welcome message to user {user_id} for chat {chat_id}: User likely blocked the bot or not interacted", exc_info=True)
                except UserNotParticipant as e:
                    logger.error(f"Cannot send welcome message to user {user_id} for chat {chat_id}: {e}", exc_info=True)
                except FloodWait as e:
                    logger.warning(f"Flood wait triggered for sending message to user {user_id}, waiting {e.value} seconds")
                    await asyncio.sleep(e.value)
                    await client.send_message(user_id, welcome_message)
                    logger.info(f"Successfully sent welcome message to user {user_id} for chat {chat_id} after flood wait")
                except Exception as e:
                    logger.error(f"Unexpected error sending welcome message to user {user_id} for chat {chat_id}: {e}", exc_info=True)

            # Check if user is new (not in users collection)
            logger.info(f"Checking if user {user_id} exists in database")
            try:
                is_new_user = not self.db.is_user_exists(user_id)
                logger.info(f"User {user_id} is {'new' if is_new_user else 'existing'} for the bot")
            except Exception as e:
                logger.error(f"Failed to check if user {user_id} exists for chat {chat_id}: {e}", exc_info=True)
                return

            if is_new_user:
                # Trigger /start command silently (add to db.users without message)
                try:
                    logger.info(f"Silently triggering /start for user {user_id}")
                    await start_func(client, user_id, silent=True)
                    logger.info(f"Successfully triggered silent /start for user {user_id}")
                except PeerIdInvalid:
                    logger.error(f"Cannot trigger silent /start for user {user_id}: User likely blocked the bot or not interacted", exc_info=True)
                except Exception as e:
                    logger.error(f"Failed to trigger silent /start for user {user_id}: {e}", exc_info=True)

            # Save user ID to accepted_users (for all users)
            try:
                logger.info(f"Saving user {user_id} to accepted_users for chat {chat_id}")
                self.db.update_chat_settings(
                    chat_id,
                    {"$push": {"settings.auto_request.accepted_users": user_id}}
                )
                logger.info(f"Successfully added user {user_id} to accepted_users for chat {chat_id}")
            except Exception as e:
                logger.error(f"Failed to save user {user_id} to accepted_users for chat {chat_id}: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Failed to handle join request for user {user_id} in chat {chat_id}: {e}", exc_info=True)
