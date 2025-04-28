
import logging
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import API_ID, API_HASH, BOT_TOKEN, ADMIN_IDS
from database import Database
from antispam import AntiSpam
from auto_delete import AutoDelete
from auto_request_accept import AutoRequestAccept
from utils import format_time
import time

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db = Database()
antispam = AntiSpam(db)
auto_delete = AutoDelete(db)
auto_request = AutoRequestAccept(db)

async def preload_chats():
    """Preload all chats from database to verify and refresh session cache."""
    logger.info("Preloading chats from database...")
    chats = db.get_all_chats()
    bot_user = await app.get_me()
    for chat in chats:
        chat_id = chat["chat_id"]
        title = chat.get("title", str(chat_id))
        bot_admin_status = chat.get("bot_admin_status", False)
        retries = 3
        verified = False

        # Check stored bot admin status first
        if bot_admin_status:
            logger.info(f"Chat {chat_id} ({title}) has stored bot_admin_status=True, attempting to verify...")
            for attempt in range(retries):
                try:
                    await app.resolve_peer(chat_id)
                    chat_info = await app.get_chat(chat_id)
                    logger.info(f"Chat {chat_id} ({chat_info.title}) is accessible")
                    if chat_info.title != title:
                        db.update_chat_settings(chat_id, {"title": chat_info.title})
                        logger.info(f"Updated title for chat {chat_id} to {chat_info.title}")
                    chat_member = await app.get_chat_member(chat_id, bot_user.id)
                    if chat_member.status in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]:
                        logger.info(f"Bot is admin in chat {chat_id}, status={chat_member.status}")
                        db.update_chat_settings(chat_id, {"bot_admin_status": True})
                        verified = True
                        break
                    else:
                        logger.warning(f"Bot is not an admin in chat {chat_id}, status={chat_member.status}")
                        db.update_chat_settings(chat_id, {"bot_admin_status": False})
                        logger.info(f"Kept chat {chat_id} in database with bot_admin_status=False")
                        break
                except (KeyError, ValueError) as e:
                    logger.warning(f"Attempt {attempt + 1}/{retries}: Chat {chat_id} is inaccessible: {e}")
                    if attempt < retries - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        logger.error(f"Failed to verify chat {chat_id} after {retries} attempts, keeping in database due to bot_admin_status=True")
                        verified = True  # Keep chat due to stored status
        else:
            # No stored admin status, perform full verification
            for attempt in range(retries):
                try:
                    await app.resolve_peer(chat_id)
                    chat_info = await app.get_chat(chat_id)
                    logger.info(f"Chat {chat_id} ({chat_info.title}) is accessible")
                    if chat_info.title != title:
                        db.update_chat_settings(chat_id, {"title": chat_info.title})
                        logger.info(f"Updated title for chat {chat_id} to {chat_info.title}")
                    chat_member = await app.get_chat_member(chat_id, bot_user.id)
                    if chat_member.status in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]:
                        logger.info(f"Bot is admin in chat {chat_id}, status={chat_member.status}")
                        db.update_chat_settings(chat_id, {"bot_admin_status": True})
                        verified = True
                        break
                    else:
                        logger.warning(f"Bot is not an admin in chat {chat_id}, status={chat_member.status}")
                        db.update_chat_settings(chat_id, {"bot_admin_status": False})
                        logger.info(f"Kept chat {chat_id} in database with bot_admin_status=False")
                        break
                except (KeyError, ValueError) as e:
                    logger.warning(f"Attempt {attempt + 1}/{retries}: Chat {chat_id} is inaccessible: {e}")
                    if attempt < retries - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        logger.error(f"Bot is not a member of chat {chat_id} after {retries} attempts, keeping in database")
                        db.update_chat_settings(chat_id, {"bot_admin_status": False})
                        logger.info(f"Kept chat {chat_id} in database with bot_admin_status=False")
                        break
    logger.info("Chat preloading completed")

async def start(client, user_id_or_message, silent=False):
    """Handle /start command or programmatic start for a user, with optional silent mode."""
    if hasattr(user_id_or_message, 'from_user'):
        # Called via /start command
        user_id = user_id_or_message.from_user.id
        message = user_id_or_message
    else:
        # Called programmatically with user_id
        user_id = user_id_or_message
        message = None

    logger.info(f"{'Silent ' if silent else ''}Start command triggered for user {user_id}")
    try:
        db.add_user(user_id)
        if not silent:
            chats = db.get_all_chats_for_user(user_id)
            has_chats = bool(chats)
            buttons = []
            if has_chats:
                buttons.append([InlineKeyboardButton("⚙️ Chat Settings", callback_data="help")])
            buttons.extend([
                [InlineKeyboardButton("ℹ️ About Bot", callback_data="about")]
            ])
            reply_markup = InlineKeyboardMarkup(buttons)
            start_message = (
                "🌟 **Welcome to the Ultimate Telegram Bot!** 🌟\n\n"
                "I'm here to manage your groups and channels with powerful features:\n"
                "🚨 **Anti-Spam**: Block spam messages.\n"
                "🗑 **Auto-Delete**: Schedule message deletions.\n"
                "✅ **Auto-Request Accept**: Manage join requests automatically.\n\n"
                f"{'Configure settings once added to a chat!' if not has_chats else 'Use the buttons below to explore and configure!'}"
            )
            if message:
                # Reply to /start command
                await message.reply(start_message, reply_markup=reply_markup)
            else:
                # Send programmatically
                await client.send_message(user_id, start_message, reply_markup=reply_markup)
            logger.info(f"Start menu sent to user {user_id}, has_chats={has_chats}, chats={chats}")
        else:
            logger.info(f"User {user_id} added to database silently, no start message sent")
    except Exception as e:
        logger.error(f"Failed to process start for user {user_id}: {e}", exc_info=True)

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    """Handle /start command."""
    await start(client, message, silent=False)

@app.on_message(filters.command("stats") & filters.private & filters.user(ADMIN_IDS))
async def stats(client, message):
    logger.info(f"Stats command received from admin {message.from_user.id}")
    user_count = db.get_user_count()
    chat_count = db.get_chat_count()
    await message.reply(
        f"📊 **Bot Stats**\n\nTotal Users: {user_count}\nTotal Chats: {chat_count}"
    )
    logger.info(f"Stats sent to admin {message.from_user.id}")

@app.on_message(filters.command("broadcast") & filters.private & filters.user(ADMIN_IDS))
async def broadcast(client, message):
    logger.info(f"Broadcast command received from admin {message.from_user.id}")
    if not message.reply_to_message:
        await message.reply("Please reply to a message to broadcast.")
        logger.warning("Broadcast attempted without reply message")
        return
    users = db.get_all_users()
    success = 0
    for user_id in users:
        try:
            await message.reply_to_message.forward(user_id)
            success += 1
            await asyncio.sleep(0.5)  # Avoid flood
        except Exception as e:
            logger.error(f"Failed to broadcast to {user_id}: {e}", exc_info=True)
    await message.reply(f"Broadcast sent to {success} users.")
    logger.info(f"Broadcast completed, reached {success} users")

@app.on_callback_query(filters.regex("help"))
async def help_menu(client, callback_query):
    user_id = callback_query.from_user.id
    logger.info(f"Chat Settings menu requested by user {user_id}, data={callback_query.data}")
    chats = db.get_all_chats_for_user(user_id)
    if not chats:
        await callback_query.message.edit(
            "You need to be an admin in a connected chat to configure settings.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="start")]])
        )
        await callback_query.answer("No connected chats found")
        logger.info(f"Chat Settings menu denied for user {user_id}: No connected chats")
        return

    if len(chats) == 1:
        # Single chat: show settings directly
        chat = chats[0]
        buttons = [
            [InlineKeyboardButton("🚨 Anti-Spam", callback_data=f"antispam_menu_{chat['chat_id']}")],
            [InlineKeyboardButton("🗑 Auto-Delete", callback_data=f"autodelete_menu_{chat['chat_id']}")],
            [InlineKeyboardButton("✅ Auto-Request Accept", callback_data=f"autorequest_menu_{chat['chat_id']}")],
            [InlineKeyboardButton("🔙 Back", callback_data="start")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        await callback_query.message.edit(
            f"Select a setting to configure for chat {chat['title'] or 'Untitled Chat'}:",
            reply_markup=reply_markup
        )
        await callback_query.answer("Chat Settings menu opened")
        logger.info(f"Chat Settings menu sent to user {user_id}, chat_id={chat['chat_id']}")
    else:
        # Multiple chats: show chat selection
        buttons = [
            [InlineKeyboardButton(f"{chat['title'] or 'Untitled Chat'}", callback_data=f"settings_{chat['chat_id']}")]
            for chat in chats
        ]
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="start")])
        reply_markup = InlineKeyboardMarkup(buttons)
        await callback_query.message.edit(
            "Select a chat to configure its settings:",
            reply_markup=reply_markup
        )
        await callback_query.answer("Chat selection opened")
        logger.info(f"Chat selection menu sent to user {user_id}, chats={chats}")

@app.on_callback_query(filters.regex("about"))
async def about(client, callback_query):
    logger.info(f"About menu requested by user {callback_query.from_user.id}, data={callback_query.data}")
    buttons = [[InlineKeyboardButton("🔙 Back", callback_data="start")]]
    reply_markup = InlineKeyboardMarkup(buttons)
    await callback_query.message.edit(
        "🤖 **About the Bot**\n\n"
        "Built with ❤️ by xAI\n"
        "Features: Anti-Spam, Auto-Delete, Auto-Request Accept\n"
        "Version: 1.0.0\n"
        "Contact: PM the bot for support!",
        reply_markup=reply_markup
    )
    await callback_query.answer("About menu opened")
    logger.info(f"About menu sent to user {callback_query.from_user.id}")

@app.on_callback_query(filters.regex("start"))
async def back_to_start(client, callback_query):
    logger.info(f"Start menu requested by user {callback_query.from_user.id}, data={callback_query.data}")
    chats = db.get_all_chats_for_user(callback_query.from_user.id)
    has_chats = bool(chats)
    buttons = []
    if has_chats:
        buttons.append([InlineKeyboardButton("⚙️ Chat Settings", callback_data="help")])
    buttons.extend([
        [InlineKeyboardButton("ℹ️ About Bot", callback_data="about")]
    ])
    reply_markup = InlineKeyboardMarkup(buttons)
    await callback_query.message.edit(
        "🌟 **Welcome to the Ultimate Telegram Bot!** 🌟\n\n"
        "I'm here to manage your groups and channels with powerful features:\n"
        "🚨 **Anti-Spam**: Block spam messages.\n"
        "🗑 **Auto-Delete**: Schedule message deletions.\n"
        "✅ **Auto-Request Accept**: Manage join requests automatically.\n\n"
        f"{'Configure settings once added to a chat!' if not has_chats else 'Use the buttons below to explore and configure!'}",
        reply_markup=reply_markup
    )
    await callback_query.answer("Back to start menu")
    logger.info(f"Start menu sent to user {callback_query.from_user.id}, has_chats={has_chats}, chats={chats}")

@app.on_callback_query(filters.regex(r"antispam_menu_(-?\d+)"))
async def antispam_menu(client, callback_query):
    logger.info(f"Anti-spam menu callback received from user {callback_query.from_user.id}, data={callback_query.data}")
    try:
        await antispam.handle_menu(client, callback_query)
        logger.info(f"Anti-spam menu processed for user {callback_query.from_user.id}")
    except Exception as e:
        logger.error(f"Error in anti-spam menu for user {callback_query.from_user.id}: {e}", exc_info=True)
        await callback_query.answer("Error processing request", show_alert=True)

@app.on_callback_query(filters.regex(r"antispam_(normal|aggressive|off)_(-?\d+)"))
async def antispam_set_mode(client, callback_query):
    mode = callback_query.data.split("_")[1]
    logger.info(f"Anti-spam mode change requested to {mode} by user {callback_query.from_user.id}, data={callback_query.data}")
    try:
        await antispam.set_mode(client, callback_query, mode)
        logger.info(f"Anti-spam mode change processed for user {callback_query.from_user.id}")
    except Exception as e:
        logger.error(f"Error setting anti-spam mode for user {callback_query.from_user.id}: {e}", exc_info=True)
        await callback_query.answer("Error setting mode", show_alert=True)

@app.on_callback_query(filters.regex(r"autodelete_menu_(-?\d+)"))
async def autodelete_menu(client, callback_query):
    logger.info(f"Auto-delete menu callback received from user {callback_query.from_user.id}, data={callback_query.data}")
    try:
        await auto_delete.handle_menu(client, callback_query)
        logger.info(f"Auto-delete menu processed for user {callback_query.from_user.id}")
    except Exception as e:
        logger.error(f"Error in auto-delete menu for user {callback_query.from_user.id}: {e}", exc_info=True)
        await callback_query.answer("Error processing request", show_alert=True)

@app.on_callback_query(filters.regex(r"autodelete_(text|photo|video|gif)_(-?\d+)"))
async def autodelete_set_time(client, callback_query):
    msg_type = callback_query.data.split("_")[1]
    logger.info(f"Auto-delete time setting requested for {msg_type} by user {callback_query.from_user.id}, data={callback_query.data}")
    try:
        await auto_delete.set_time(client, callback_query, msg_type)
        logger.info(f"Auto-delete time setting processed for user {callback_query.from_user.id}")
    except Exception as e:
        logger.error(f"Error setting auto-delete time for user {callback_query.from_user.id}: {e}", exc_info=True)
        await callback_query.answer("Error setting time", show_alert=True)

@app.on_callback_query(filters.regex(r"autodelete_all_(-?\d+)"))
async def autodelete_set_all_time(client, callback_query):
    logger.info(f"Auto-delete set all time requested by user {callback_query.from_user.id}, data={callback_query.data}")
    try:
        await auto_delete.set_all_time(client, callback_query)
        logger.info(f"Auto-delete set all time processed for user {callback_query.from_user.id}")
    except Exception as e:
        logger.error(f"Error setting auto-delete all time for user {callback_query.from_user.id}: {e}", exc_info=True)
        await callback_query.answer("Error setting all time", show_alert=True)

@app.on_callback_query(filters.regex(r"autodelete_toggle_(-?\d+)"))
async def autodelete_toggle(client, callback_query):
    logger.info(f"Auto-delete toggle requested by user {callback_query.from_user.id}, data={callback_query.data}")
    try:
        await auto_delete.toggle_auto_delete(client, callback_query)
        logger.info(f"Auto-delete toggle processed for user {callback_query.from_user.id}")
    except Exception as e:
        logger.error(f"Error toggling auto-delete for user {callback_query.from_user.id}: {e}", exc_info=True)
        await callback_query.answer("Error toggling auto-delete", show_alert=True)

@app.on_callback_query(filters.regex(r"autodelete_cancel_(-?\d+)"))
async def autodelete_cancel(client, callback_query):
    logger.info(f"Auto-delete cancel requested by user {callback_query.from_user.id}, data={callback_query.data}")
    try:
        await auto_delete.cancel_action(client, callback_query)
        logger.info(f"Auto-delete cancel processed for user {callback_query.from_user.id}")
    except Exception as e:
        logger.error(f"Error canceling auto-delete for user {callback_query.from_user.id}: {e}", exc_info=True)
        await callback_query.answer("Error canceling action", show_alert=True)

@app.on_callback_query(filters.regex(r"autorequest_menu_(-?\d+)"))
async def autorequest_menu(client, callback_query):
    logger.info(f"Auto-request menu callback received from user {callback_query.from_user.id}, data={callback_query.data}")
    try:
        await auto_request.handle_menu(client, callback_query)
        logger.info(f"Auto-request menu processed for user {callback_query.from_user.id}")
    except Exception as e:
        logger.error(f"Error in auto-request menu for user {callback_query.from_user.id}: {e}", exc_info=True)
        await callback_query.answer("Error processing request", show_alert=True)

@app.on_callback_query(filters.regex(r"autorequest_(instant|5min|10min|manual)_(-?\d+)"))
async def autorequest_set_delay(client, callback_query):
    option = callback_query.data.split("_")[1]
    delay = {"instant": 0, "5min": 300, "10min": 600, "manual": -1}[option]
    logger.info(f"Auto-request delay setting requested to {option} by user {callback_query.from_user.id}, data={callback_query.data}")
    try:
        await auto_request.set_delay(client, callback_query, delay)
        logger.info(f"Auto-request delay setting processed for user {callback_query.from_user.id}")
    except Exception as e:
        logger.error(f"Error setting auto-request delay for user {callback_query.from_user.id}: {e}", exc_info=True)
        await callback_query.answer("Error setting delay", show_alert=True)

@app.on_callback_query(filters.regex(r"autorequest_custom_(-?\d+)"))
async def autorequest_set_custom(client, callback_query):
    logger.info(f"Auto-request custom delay requested by user {callback_query.from_user.id}, data={callback_query.data}")
    try:
        await auto_request.set_custom(client, callback_query)
        logger.info(f"Auto-request custom delay processed for user {callback_query.from_user.id}")
    except Exception as e:
        logger.error(f"Error setting auto-request custom delay for user {callback_query.from_user.id}: {e}", exc_info=True)
        await callback_query.answer("Error setting custom delay", show_alert=True)

@app.on_callback_query(filters.regex(r"autorequest_welcome_(-?\d+)"))
async def autorequest_set_welcome(client, callback_query):
    logger.info(f"Auto-request welcome message setting requested by user {callback_query.from_user.id}, data={callback_query.data}")
    try:
        await auto_request.set_welcome(client, callback_query)
        logger.info(f"Auto-request welcome message setting processed for user {callback_query.from_user.id}")
    except Exception as e:
        logger.error(f"Error setting auto-request welcome message for user {callback_query.from_user.id}: {e}", exc_info=True)
        await callback_query.answer("Error setting welcome message", show_alert=True)

@app.on_callback_query(filters.regex(r"autorequest_cancel_(-?\d+)"))
async def autorequest_cancel(client, callback_query):
    logger.info(f"Auto-request cancel requested by user {callback_query.from_user.id}, data={callback_query.data}")
    try:
        await auto_request.cancel_action(client, callback_query)
        logger.info(f"Auto-request cancel processed for user {callback_query.from_user.id}")
    except Exception as e:
        logger.error(f"Error canceling auto-request for user {callback_query.from_user.id}: {e}", exc_info=True)
        await callback_query.answer("Error canceling action", show_alert=True)

@app.on_callback_query(filters.regex(r"settings_(-?\d+)"))
async def settings_menu_callback(client, callback_query):
    chat_id = int(callback_query.data.split("_")[1])
    user_id = callback_query.from_user.id
    logger.info(f"Settings menu requested for chat {chat_id} by user {user_id}, data={callback_query.data}")
    try:
        # Verify chat exists in database
        chat_db = db.get_chat_settings(chat_id)
        if not chat_db:
            logger.warning(f"Chat {chat_id} not found in database")
            await callback_query.message.edit(
                f"Chat {chat_id} is not registered with the bot. Please re-add the bot to the chat.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="help")]])
            )
            await callback_query.answer("Chat not found", show_alert=True)
            return

        title = chat_db.get("title", str(chat_id))
        bot_admin_status = chat_db.get("bot_admin_status", False)
        retries = 3
        verified = False

        # Check stored bot admin status first
        if bot_admin_status:
            logger.info(f"Chat {chat_id} ({title}) has stored bot_admin_status=True, attempting to verify...")
            for attempt in range(retries):
                try:
                    await client.resolve_peer(chat_id)
                    chat_info = await client.get_chat(chat_id)
                    logger.info(f"Chat {chat_id} ({chat_info.title}) is accessible")
                    if chat_info.title != title:
                        db.update_chat_settings(chat_id, {"title": chat_info.title})
                        logger.info(f"Updated title for chat {chat_id} to {chat_info.title}")
                    chat_member = await client.get_chat_member(chat_id, user_id)
                    if chat_member.status not in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]:
                        await callback_query.message.edit(
                            "You are not an admin in this chat.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="help")]])
                        )
                        await callback_query.answer("Access denied: Not an admin")
                        logger.warning(f"User {user_id} attempted to access settings for chat {chat_id} without admin rights")
                        return
                    bot_member = await client.get_chat_member(chat_id, (await client.get_me()).id)
                    if bot_member.status not in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]:
                        logger.warning(f"Bot is not an admin in chat {chat_id}, status={bot_member.status}")
                        db.update_chat_settings(chat_id, {"bot_admin_status": False})
                        logger.info(f"Kept chat {chat_id} in database with bot_admin_status=False")
                        await callback_query.message.edit(
                            f"Bot is no longer an admin in chat {title} ({chat_id}). "
                            f"Please re-add the bot as an admin to restore functionality.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="help")]])
                        )
                        await callback_query.answer("Bot is not an admin", show_alert=True)
                        for admin_id in chat_db.get("admin_ids", []):
                            try:
                                await client.send_message(
                                    admin_id,
                                    f"⚠️ Bot is no longer an admin in chat {title} ({chat_id}). "
                                    f"Please re-add the bot as an admin to restore functionality."
                                )
                                logger.info(f"Notified admin {admin_id} about non-admin status in chat {chat_id}")
                            except Exception as notify_ex:
                                logger.error(f"Failed to notify admin {admin_id}: {notify_ex}")
                        return
                    logger.info(f"Bot is admin in chat {chat_id}, status={bot_member.status}")
                    verified = True
                    break
                except (KeyError, ValueError) as e:
                    logger.warning(f"Attempt {attempt + 1}/{retries}: Cannot verify admin status for user {user_id} in chat {chat_id}: {e}")
                    if attempt < retries - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        logger.error(f"Failed to verify chat {chat_id} after {retries} attempts, keeping in database due to bot_admin_status=True")
                        verified = True  # Keep chat due to stored status
        else:
            # No stored admin status, perform full verification
            for attempt in range(retries):
                try:
                    await client.resolve_peer(chat_id)
                    chat_info = await client.get_chat(chat_id)
                    logger.info(f"Chat {chat_id} ({chat_info.title}) is accessible")
                    if chat_info.title != title:
                        db.update_chat_settings(chat_id, {"title": chat_info.title})
                        logger.info(f"Updated title for chat {chat_id} to {chat_info.title}")
                    chat_member = await client.get_chat_member(chat_id, user_id)
                    if chat_member.status not in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]:
                        await callback_query.message.edit(
                            "You are not an admin in this chat.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="help")]])
                        )
                        await callback_query.answer("Access denied: Not an admin")
                        logger.warning(f"User {user_id} attempted to access settings for chat {chat_id} without admin rights")
                        return
                    bot_member = await client.get_chat_member(chat_id, (await client.get_me()).id)
                    if bot_member.status not in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]:
                        logger.warning(f"Bot is not an admin in chat {chat_id}, status={bot_member.status}")
                        db.update_chat_settings(chat_id, {"bot_admin_status": False})
                        logger.info(f"Kept chat {chat_id} in database with bot_admin_status=False")
                        await callback_query.message.edit(
                            f"Bot is no longer an admin in chat {title} ({chat_id}). "
                            f"Please re-add the bot as an admin to restore functionality.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="help")]])
                        )
                        await callback_query.answer("Bot is not an admin", show_alert=True)
                        for admin_id in chat_db.get("admin_ids", []):
                            try:
                                await client.send_message(
                                    admin_id,
                                    f"⚠️ Bot is no longer an admin in chat {title} ({chat_id}). "
                                    f"Please re-add the bot as an admin to restore functionality."
                                )
                                logger.info(f"Notified admin {admin_id} about non-admin status in chat {chat_id}")
                            except Exception as notify_ex:
                                logger.error(f"Failed to notify admin {admin_id}: {notify_ex}")
                        return
                    logger.info(f"Bot is admin in chat {chat_id}, status={bot_member.status}")
                    verified = True
                    break
                except (KeyError, ValueError) as e:
                    logger.warning(f"Attempt {attempt + 1}/{retries}: Cannot verify admin status for user {user_id} in chat {chat_id}: {e}")
                    if attempt < retries - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        logger.error(f"Bot is not a member of chat {chat_id} after {retries} attempts, keeping in database")
                        db.update_chat_settings(chat_id, {"bot_admin_status": False})
                        logger.info(f"Kept chat {chat_id} in database with bot_admin_status=False")
                        await callback_query.message.edit(
                            f"This chat is not accessible. It may have been deleted or the bot was removed. "
                            f"Please re-add the bot to {title}.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="help")]])
                        )
                        await callback_query.answer("Chat is inaccessible", show_alert=True)
                        for admin_id in chat_db.get("admin_ids", []):
                            try:
                                await client.send_message(
                                    admin_id,
                                    f"⚠️ Bot was removed from chat {title} ({chat_id}). "
                                    f"Please re-add the bot to restore functionality."
                                )
                                logger.info(f"Notified admin {admin_id} about removal from chat {chat_id}")
                            except Exception as notify_ex:
                                logger.error(f"Failed to notify admin {admin_id}: {notify_ex}")
                        return

        if not verified:
            logger.error(f"Failed to verify chat {chat_id}, assuming inaccessible but keeping in database")
            # Skip final accessibility check and proceed if bot_admin_status was True
            if bot_admin_status:
                logger.info(f"Allowing settings menu for chat {chat_id} due to bot_admin_status=True")
            else:
                await callback_query.message.edit(
                    f"This chat is not accessible. It may have been deleted or the bot was removed. "
                    f"Please re-add the bot to {title}.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="help")]])
                )
                await callback_query.answer("Chat is inaccessible", show_alert=True)
                return

        buttons = [
            [InlineKeyboardButton("🚨 Anti-Spam", callback_data=f"antispam_menu_{chat_id}")],
            [InlineKeyboardButton("🗑 Auto-Delete", callback_data=f"autodelete_menu_{chat_id}")],
            [InlineKeyboardButton("✅ Auto-Request Accept", callback_data=f"autorequest_menu_{chat_id}")]
        ]
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="help")])
        reply_markup = InlineKeyboardMarkup(buttons)
        await callback_query.message.edit(
            f"Configure settings for {title}:",
            reply_markup=reply_markup
        )
        await callback_query.answer("Settings menu opened")
        logger.info(f"Settings menu sent for chat {chat_id} to user {user_id}")
    except Exception as e:
        logger.error(f"Error in settings menu for chat {chat_id}, user {user_id}: {e}", exc_info=True)
        await callback_query.answer("Error opening settings", show_alert=True)

@app.on_callback_query()
async def catch_all_callbacks(client, callback_query):
    logger.warning(f"Unhandled callback query received from user {callback_query.from_user.id}: {callback_query.data}")
    await callback_query.answer("Unknown action", show_alert=True)

@app.on_chat_join_request(filters.group | filters.channel)
async def handle_join_request(client, join_request):
    chat_id = join_request.chat.id
    user_id = join_request.from_user.id
    logger.info(f"Join request received for chat {chat_id} from user {user_id}")
    try:
        await auto_request.handle_request(client, chat_id, user_id, start)
        logger.info(f"Join request processed for chat {chat_id}, user {user_id}")
    except Exception as e:
        logger.error(f"Error processing join request for chat {chat_id}, user {user_id}: {e}", exc_info=True)

@app.on_message(filters.group & ~filters.service)
async def handle_group_message(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    logger.info(f"Group message received in chat {chat_id} from user {user_id}, text={message.text or message.caption}")
    try:
        chat_member = await client.get_chat_member(chat_id, user_id)
        is_admin = chat_member.status in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]
        # Anti-spam check
        if not is_admin:
            action_taken = await antispam.check_spam(client, message)
            if action_taken:
                logger.info(f"Spam detected and handled in chat {chat_id} from user {user_id}")
                return
        # Auto-delete check
        await auto_delete.check_delete(client, message)
        logger.info(f"Message processed for auto-delete in chat {chat_id}")
    except Exception as e:
        logger.error(f"Error processing group message in chat {chat_id}, user {user_id}: {e}", exc_info=True)

@app.on_message(filters.command("settings") & (filters.group | filters.channel))
async def settings_menu(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    logger.info(f"Settings command received in chat {chat_id} from user {user_id}")
    try:
        chat_member = await client.get_chat_member(chat_id, user_id)
        if chat_member.status not in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]:
            await message.reply("Only admins can configure settings.")
            logger.warning(f"Non-admin {user_id} attempted to access settings in chat {chat_id}")
            return
        buttons = [
            [InlineKeyboardButton("🚨 Anti-Spam", callback_data=f"antispam_menu_{chat_id}")],
            [InlineKeyboardButton("🗑 Auto-Delete", callback_data=f"autodelete_menu_{chat_id}")],
            [InlineKeyboardButton("✅ Auto-Request Accept", callback_data=f"autorequest_menu_{chat_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        await message.reply("Select a setting to configure:", reply_markup=reply_markup)
        logger.info(f"Settings menu sent to chat {chat_id} for user {user_id}")
    except Exception as e:
        logger.error(f"Error in settings command for chat {chat_id}, user {user_id}: {e}", exc_info=True)
        await message.reply("Error opening settings menu.")

@app.on_message(filters.private & filters.text)
async def handle_private_message(client, message):
    user_id = message.from_user.id
    logger.info(f"Private message received from user {user_id}: {message.text}")
    # Skip if the message is a command
    if message.text.startswith("/"):
        logger.info(f"Ignoring command in private message from user {user_id}")
        return
    # Check for pending actions
    try:
        # Auto-delete time input
        if user_id in auto_delete.pending:
            chat_id = auto_delete.pending[user_id]["chat_id"]
            if await auto_delete.process_time(client, message, chat_id):
                logger.info(f"Auto-delete time processed for user {user_id} in chat {chat_id}")
                return
        # Auto-request custom delay or welcome message
        if user_id in auto_request.pending:
            chat_id = auto_request.pending[user_id]
            if await auto_request.process_custom(client, message, chat_id):
                logger.info(f"Auto-request custom delay processed for user {user_id} in chat {chat_id}")
                return
        if user_id in auto_request.pending_welcome:
            chat_id = auto_request.pending_welcome[user_id]
            if await auto_request.process_welcome(client, message, chat_id):
                logger.info(f"Auto-request welcome message processed for user {user_id} in chat {chat_id}")
                return
        logger.info(f"No relevant pending actions for user {user_id}, ignoring message")
        # Do not send a reply for unrelated messages
    except Exception as e:
        logger.error(f"Error processing private message from user {user_id}: {e}", exc_info=True)
        await message.reply("Error processing your input.")

@app.on_chat_member_updated(filters.group | filters.channel)
async def on_bot_added(client, chat_member_updated):
    chat_id = chat_member_updated.chat.id
    chat_title = chat_member_updated.chat.title
    new_member = chat_member_updated.new_chat_member
    old_member = chat_member_updated.old_chat_member
    added_by = chat_member_updated.from_user.id
    bot_user = await client.get_me()
    
    # Check if new_member exists and if the bot itself was added or promoted
    if new_member is None or new_member.user.id != bot_user.id:
        logger.info(f"Ignoring chat member update in chat {chat_id}: Not bot or no new member")
        return
    
    # Check if bot was added (old_member is None) or promoted to admin
    if (old_member is None or old_member.status != enums.ChatMemberStatus.ADMINISTRATOR) and \
       new_member.status == enums.ChatMemberStatus.ADMINISTRATOR:
        logger.info(f"Bot added/promoted to admin in chat {chat_id} ({chat_title}) by user {added_by}")
        
        # Add chat to database with admin ID, title, bot ID, and admin status
        db.add_chat(chat_id, admin_ids=[added_by], title=chat_title, bot_id=bot_user.id, bot_admin_status=True)
        
        # Preload chats to update session cache
        await preload_chats()
        
        # Send message in chat with "Go to Settings" button
        buttons = [[InlineKeyboardButton("⚙️ Chat Settings", url=f"t.me/{bot_user.username}")]]
        reply_markup = InlineKeyboardMarkup(buttons)
        try:
            await client.send_message(
                chat_id,
                f"✅ **I'm connected to {chat_title}!**\nConfigure my settings using the button below:",
                reply_markup=reply_markup
            )
            logger.info(f"Connected message with settings button sent to chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to send connected message to chat {chat_id}: {e}", exc_info=True)
        
        # Message the admin who added the bot
        buttons = [
            [InlineKeyboardButton("🚨 Anti-Spam", callback_data=f"antispam_menu_{chat_id}")],
            [InlineKeyboardButton("🗑 Auto-Delete", callback_data=f"autodelete_menu_{chat_id}")],
            [InlineKeyboardButton("✅ Auto-Request Accept", callback_data=f"autorequest_menu_{chat_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        try:
            await client.send_message(
                added_by,
                f"🤖 **Bot Connected to {chat_title}!**\n\n"
                f"I've been added to {chat_title}. Configure my settings below:",
                reply_markup=reply_markup
            )
            logger.info(f"Connected message sent to admin {added_by} for chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to message admin {added_by}: {e}", exc_info=True)

@app.on_message(filters.command("start") & filters.private)
async def initial_preload(client, message):
    """Run preload_chats on the first /start command to ensure chats are verified."""
    await preload_chats()
    await start(client, message, silent=False)

if __name__ == "__main__":
    logger.info("Starting bot...")
    try:
        app.run()
    except Exception as e:
        logger.error(f"Bot crashed: {e}", exc_info=True)
        raise
