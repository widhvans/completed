from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import SPAM_WORDS, EXTRA_SPAM_WORDS
import logging

logger = logging.getLogger(__name__)

class AntiSpam:
    def __init__(self, db):
        self.db = db

    async def check_spam(self, client, message):
        chat_id = message.chat.id
        user_id = message.from_user.id
        logger.info(f"Checking for spam in chat {chat_id} from user {user_id}, text={message.text or message.caption}")
        settings = self.db.get_chat_settings(chat_id)
        mode = settings.get("antispam_mode", "off")
        logger.info(f"Anti-spam mode for chat {chat_id}: {mode}")
        if mode == "off":
            logger.info(f"Anti-spam off for chat {chat_id}")
            return False
        
        text = message.text or message.caption or ""
        is_spam = False
        spam_words = SPAM_WORDS
        if mode == "aggressive":
            spam_words += EXTRA_SPAM_WORDS
        
        # Check for spam words, links, or usernames
        for word in spam_words:
            if word.lower() in text.lower():
                is_spam = True
                logger.info(f"Spam word '{word}' detected in chat {chat_id}")
                break
        if mode in ["normal", "aggressive"] and ("@" in text or "t.me" in text or "http" in text):
            is_spam = True
            logger.info(f"Link or username detected in chat {chat_id}")
        
        if is_spam:
            try:
                await client.delete_messages(chat_id, message.id)
                await client.send_message(
                    chat_id,
                    f"Spam message from {message.from_user.mention} was deleted."
                )
                logger.info(f"Spam detected: Message deleted in chat {chat_id} from user {user_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to handle spam in chat {chat_id}: {e}", exc_info=True)
                return False
        logger.info(f"No spam detected in chat {chat_id}")
        return False

    async def handle_menu(self, client, callback_query):
        chat_id = int(callback_query.data.split("_")[-1])
        logger.info(f"Anti-spam menu requested for chat {chat_id} by user {callback_query.from_user.id}")
        settings = self.db.get_chat_settings(chat_id)
        mode = settings.get("antispam_mode", "off")
        
        buttons = [
            [InlineKeyboardButton(f"Normal: {'✅' if mode == 'normal' else '⬜'}", callback_data=f"antispam_normal_{chat_id}")],
            [InlineKeyboardButton(f"Aggressive: {'✅' if mode == 'aggressive' else '⬜'}", callback_data=f"antispam_aggressive_{chat_id}")],
            [InlineKeyboardButton(f"Off: {'✅' if mode == 'off' else '⬜'}", callback_data=f"antispam_off_{chat_id}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"settings_{chat_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        await callback_query.message.edit(
            "🚨 **Anti-Spam Settings**\n\nChoose a mode for this chat:", reply_markup=reply_markup
        )
        await callback_query.answer("Anti-Spam menu opened")
        logger.info(f"Anti-spam menu sent for chat {chat_id}")

    async def set_mode(self, client, callback_query, mode):
        chat_id = int(callback_query.data.split("_")[-1])
        logger.info(f"Setting anti-spam mode to {mode} for chat {chat_id} by user {callback_query.from_user.id}")
        self.db.update_chat_settings(chat_id, {"antispam_mode": mode})
        await callback_query.message.edit(f"Anti-Spam set to {mode.capitalize()}")
        await self.handle_menu(client, callback_query)
        await callback_query.answer(f"Anti-Spam mode set to {mode}")
        logger.info(f"Anti-spam mode set to {mode} for chat {chat_id}")
