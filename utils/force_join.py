"""
Force Join utility — checks if users are members of required channels/groups.
"""
import logging
import telebot
from config import FORCE_JOIN_CHANNELS

logger = logging.getLogger(__name__)


def check_force_join(bot, user_id):
    """
    Check if a user has joined all required channels/groups.
    Returns list of channels the user hasn't joined yet.
    """
    if not FORCE_JOIN_CHANNELS:
        return []

    not_joined = []
    for channel in FORCE_JOIN_CHANNELS:
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status in ['left', 'kicked', 'banned']:
                not_joined.append(channel)
        except telebot.apihelper.ApiTelegramException as e:
            err = str(e).lower()
            if 'user not found' in err or 'chat not found' in err:
                not_joined.append(channel)
            else:
                logger.warning(f"Force join check error for channel {channel}: {e}")
        except Exception as e:
            logger.warning(f"Force join check error for channel {channel}: {e}")

    return not_joined


def send_force_join_message(bot, chat_id, not_joined_channels):
    """Send force join message with buttons."""
    from telebot import types

    markup = types.InlineKeyboardMarkup(row_width=1)
    for channel in not_joined_channels:
        # Resolve channel invite link
        try:
            chat = bot.get_chat(channel)
            if hasattr(chat, 'invite_link') and chat.invite_link:
                link = chat.invite_link
            elif channel.startswith('@'):
                link = f"https://t.me/{channel.lstrip('@')}"
            else:
                link = f"https://t.me/c/{str(channel).lstrip('-100')}"
            display = chat.title or channel
        except Exception:
            link = f"https://t.me/{channel.lstrip('@')}" if channel.startswith('@') else '#'
            display = channel

        markup.add(types.InlineKeyboardButton(
            f"📣 Join {display}", url=link
        ))

    markup.add(types.InlineKeyboardButton(
        "✅ I've Joined — Verify", callback_data="verify_force_join"
    ))

    text = (
        "⚠️ **Access Required!**\n\n"
        "To use this bot, you must join our official channel(s)/group(s) first.\n\n"
        "1️⃣ Click the join button(s) below\n"
        "2️⃣ Come back and tap **✅ I've Joined — Verify**\n\n"
        "🔒 This ensures you stay updated with bot news & announcements."
    )

    bot.send_message(chat_id, text, reply_markup=markup, parse_mode='Markdown')


def is_force_join_required(bot, user_id, admin_ids):
    """
    Returns True if user needs to join channels first.
    Admins bypass force-join.
    """
    if user_id in admin_ids:
        return False
    if not FORCE_JOIN_CHANNELS:
        return False
    not_joined = check_force_join(bot, user_id)
    return len(not_joined) > 0
