import logging
import asyncio
from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import format_time

logger = logging.getLogger(__name__)

class AutoDelete:
    def __init__(self, db):
        self.db = db
        self.pending = {}  # Store pending time settings: {user_id: {chat_id, msg_type}}

    async def handle_menu(self, client: Client, callback_query):
        chat_id = int(callback_query.data.split("_")[-1])
        user_id = callback_query.from_user.id
        logger.info(f"Auto-delete menu requested for chat {chat_id} by user {user_id}")

        # Prevent new action if pending exists
        if user_id in self.pending:
            logger.warning(f"User {user_id} has a pending action, ignoring menu request")
            await callback_query.answer("Please complete or cancel the pending action first.", show_alert=True)
            return

        settings = self.db.get_chat_settings(chat_id).get("settings", {}).get("auto_delete", {})
        # Determine if auto-delete is enabled (any non-zero time)
        is_enabled = any(settings.get(msg_type, 0) > 0 for msg_type in ["text", "photo", "video", "gif"])
        toggle_button = (
            InlineKeyboardButton("✅ Enable Auto-Delete", callback_data=f"autodelete_toggle_{chat_id}")
            if not is_enabled
            else InlineKeyboardButton("❌ Disable Auto-Delete", callback_data=f"autodelete_toggle_{chat_id}")
        )

        buttons = [
            [InlineKeyboardButton(f"Text: {format_time(settings.get('text', 0))}", callback_data=f"autodelete_text_{chat_id}")],
            [InlineKeyboardButton(f"Photo: {format_time(settings.get('photo', 0))}", callback_data=f"autodelete_photo_{chat_id}")],
            [InlineKeyboardButton(f"Video: {format_time(settings.get('video', 0))}", callback_data=f"autodelete_video_{chat_id}")],
            [InlineKeyboardButton(f"GIF: {format_time(settings.get('gif', 0))}", callback_data=f"autodelete_gif_{chat_id}")],
            [InlineKeyboardButton("Delete All", callback_data=f"autodelete_all_{chat_id}")],
            [toggle_button]
        ]
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="help")])
        reply_markup = InlineKeyboardMarkup(buttons)

        await callback_query.message.edit(
            f"Configure auto-delete settings for chat {chat_id}:",
            reply_markup=reply_markup
        )
        await callback_query.answer("Auto-delete menu opened")
        logger.info(f"Auto-delete menu sent for chat {chat_id} to user {user_id}")

    async def set_time(self, client: Client, callback_query, msg_type: str):
        chat_id = int(callback_query.data.split("_")[-1])
        user_id = callback_query.from_user.id
        logger.info(f"Setting auto-delete time for {msg_type} in chat {chat_id} by user {user_id}")

        # Prevent new action if pending exists
        if user_id in self.pending:
            logger.warning(f"User {user_id} has a pending action, ignoring set_time request")
            await callback_query.answer("Please complete or cancel the pending action first.", show_alert=True)
            return

        self.pending[user_id] = {"chat_id": chat_id, "msg_type": msg_type}
        await callback_query.message.edit(
            f"Please enter the auto-delete time for {msg_type} messages (e.g., 5s for 5 seconds, 1m for 1 minute, 4h for 4 hours, 0 to disable):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data=f"autodelete_cancel_{chat_id}")]])
        )
        await callback_query.answer(f"Enter time for {msg_type}")
        logger.info(f"Prompted user {user_id} to enter auto-delete time for {msg_type} in chat {chat_id}")

    async def set_all_time(self, client: Client, callback_query):
        chat_id = int(callback_query.data.split("_")[-1])
        user_id = callback_query.from_user.id
        logger.info(f"Setting auto-delete time for all message types in chat {chat_id} by user {user_id}")

        # Prevent new action if pending exists
        if user_id in self.pending:
            logger.warning(f"User {user_id} has a pending action, ignoring set_all_time request")
            await callback_query.answer("Please complete or cancel the pending action first.", show_alert=True)
            return

        self.pending[user_id] = {"chat_id": chat_id, "msg_type": "all"}
        await callback_query.message.edit(
            "Please enter the auto-delete time for all message types (text, photo, video, GIF) (e.g., 5s for 5 seconds, 1m for 1 minute, 4h for 4 hours, 0 to disable):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data=f"autodelete_cancel_{chat_id}")]])
        )
        await callback_query.answer("Enter time for all message types")
        logger.info(f"Prompted user {user_id} to enter auto-delete time for all message types in chat {chat_id}")

    async def toggle_auto_delete(self, client: Client, callback_query):
        chat_id = int(callback_query.data.split("_")[-1])
        user_id = callback_query.from_user.id
        logger.info(f"Toggling auto-delete for chat {chat_id} by user {user_id}")

        # Prevent new action if pending exists
        if user_id in self.pending:
            logger.warning(f"User {user_id} has a pending action, ignoring toggle_auto_delete request")
            await callback_query.answer("Please complete or cancel the pending action first.", show_alert=True)
            return

        settings = self.db.get_chat_settings(chat_id).get("settings", {}).get("auto_delete", {})
        is_enabled = any(settings.get(msg_type, 0) > 0 for msg_type in ["text", "photo", "video", "gif"])

        if is_enabled:
            # Disable auto-delete for all message types
            self.db.update_chat_settings(
                chat_id,
                {"settings.auto_delete": {"text": 0, "photo": 0, "video": 0, "gif": 0}}
            )
            await callback_query.message.edit(
                f"Auto-delete turned off for all message types in chat {chat_id}.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"autodelete_menu_{chat_id}")]])
            )
            await callback_query.answer("Auto-delete turned off")
            logger.info(f"Auto-delete turned off for chat {chat_id} by user {user_id}")
        else:
            # Prompt for time to enable auto-delete
            self.pending[user_id] = {"chat_id": chat_id, "msg_type": "all"}
            await callback_query.message.edit(
                "Please enter the auto-delete time for all message types (text, photo, video, GIF) (e.g., 5s for 5 seconds, 1m for 1 minute, 4h for 4 hours, 0 to disable):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data=f"autodelete_cancel_{chat_id}")]])
            )
            await callback_query.answer("Enter time to enable auto-delete")
            logger.info(f"Prompted user {user_id} to enter auto-delete time to enable for chat {chat_id}")

    async def cancel_action(self, client: Client, callback_query):
        chat_id = int(callback_query.data.split("_")[-1])
        user_id = callback_query.from_user.id
        logger.info(f"Canceling auto-delete action for chat {chat_id} by user {user_id}")

        if user_id in self.pending:
            self.pending.pop(user_id)
            await callback_query.message.edit(
                "Action canceled. Returning to auto-delete menu.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"autodelete_menu_{chat_id}")]])
            )
            await callback_query.answer("Action canceled")
            logger.info(f"Canceled pending action for user {user_id} in chat {chat_id}")
        else:
            logger.warning(f"No pending action to cancel for user {user_id} in chat {chat_id}")
            await callback_query.answer("No pending action to cancel.", show_alert=True)

    async def process_time(self, client: Client, message, chat_id: int):
        user_id = message.from_user.id
        if user_id not in self.pending or self.pending[user_id]["chat_id"] != chat_id:
            logger.info(f"No pending auto-delete action for user {user_id} in chat {chat_id}, ignoring message")
            return False

        pending = self.pending[user_id]
        msg_type = pending["msg_type"]
        input_text = message.text.lower().strip()

        # Parse input (e.g., 5s, 1m, 4h)
        try:
            if input_text == "0":
                time_seconds = 0
            else:
                if input_text.endswith("s"):
                    time_seconds = int(input_text[:-1])
                elif input_text.endswith("m"):
                    time_seconds = int(input_text[:-1]) * 60
                elif input_text.endswith("h"):
                    time_seconds = int(input_text[:-1]) * 3600
                else:
                    time_seconds = int(input_text)  # Assume seconds if no suffix
                if time_seconds < 0:
                    raise ValueError("Time cannot be negative")
        except ValueError:
            logger.warning(f"Invalid time input by user {user_id} for chat {chat_id}: {input_text}")
            await message.reply(
                "Invalid input. Please enter a non-negative time (e.g., 5s for 5 seconds, 1m for 1 minute, 4h for 4 hours, 0 to disable).",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data=f"autodelete_cancel_{chat_id}")]])
            )
            return False

        if msg_type == "all":
            # Set the same time for all message types
            settings_update = {
                "settings.auto_delete.text": time_seconds,
                "settings.auto_delete.photo": time_seconds,
                "settings.auto_delete.video": time_seconds,
                "settings.auto_delete.gif": time_seconds
            }
            msg_type_display = "all message types"
        else:
            # Set time for specific message type
            settings_update = {f"settings.auto_delete.{msg_type}": time_seconds}
            msg_type_display = msg_type

        self.db.update_chat_settings(chat_id, settings_update)
        self.pending.pop(user_id, None)  # Clear pending action
        await message.reply(
            f"Auto-delete time for {msg_type_display} set to {format_time(time_seconds)} in chat {chat_id}.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"autodelete_menu_{chat_id}")]])
        )
        logger.info(f"Auto-delete time for {msg_type_display} set to {time_seconds} seconds in chat {chat_id} by user {user_id}")
        return True

    async def check_delete(self, client: Client, message):
        chat_id = message.chat.id
        settings = self.db.get_chat_settings(chat_id).get("settings", {}).get("auto_delete", {})
        msg_type = None
        if message.text:
            msg_type = "text"
        elif message.photo:
            msg_type = "photo"
        elif message.video:
            msg_type = "video"
        elif message.animation:
            msg_type = "gif"

        if msg_type and settings.get(msg_type, 0) > 0:
            delete_after = settings[msg_type]
            logger.info(f"Scheduling deletion of {msg_type} message {message.id} in chat {chat_id} after {delete_after} seconds")
            await asyncio.sleep(delete_after)
            try:
                await client.delete_messages(chat_id, message.id)
                logger.info(f"Deleted {msg_type} message {message.id} in chat {chat_id}")
            except Exception as e:
                logger.error(f"Failed to delete {msg_type} message {message.id} in chat {chat_id}: {e}")
