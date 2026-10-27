"""
Start & Help handlers — welcome message, /start, /help, /ping, /uptime.
Includes: force-join check, referral tracking, 18-day free trial activation.
"""
import time
import logging
from datetime import datetime

import database as db
from config import OWNER_ID, YOUR_USERNAME, UPDATE_CHANNEL, FREE_TRIAL_DAYS, REFERRALS_PER_REWARD
from utils.helpers import get_uptime, get_user_status, get_file_limit, format_limit
from utils.keyboards import reply_keyboard_main, main_menu_inline
from utils.force_join import check_force_join, send_force_join_message

logger = logging.getLogger(__name__)


def register(bot, admin_ids, subscriptions, bot_locked_ref):
    """Register start/help handlers on the bot."""

    @bot.message_handler(commands=['start', 'help'])
    def cmd_start(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        user_name = message.from_user.first_name
        user_username = message.from_user.username

        # Check banned
        if db.is_banned(user_id):
            bot.send_message(chat_id, "🚫 You are banned from using this bot.")
            return

        # Check maintenance
        maint = db.get_maintenance_status()
        if maint['enabled'] and user_id not in admin_ids:
            bot.send_message(chat_id, f"🛠 {maint['message']}")
            return

        if bot_locked_ref[0] and user_id not in admin_ids:
            bot.send_message(chat_id, "🔒 Bot is locked by admin. Try later.")
            return

        # --- Force Join Check ---
        if user_id not in admin_ids:
            not_joined = check_force_join(bot, user_id)
            if not_joined:
                send_force_join_message(bot, chat_id, not_joined)
                return

        # --- Handle referral parameter ---
        ref_code = None
        if message.text and len(message.text.split()) > 1:
            param = message.text.split()[1]
            if param.startswith('ref') and param[3:].isdigit():
                ref_code = int(param[3:])

        # Profile info
        photo_file_id = None
        try:
            photos = bot.get_user_profile_photos(user_id, limit=1)
            if photos.photos:
                photo_file_id = photos.photos[0][-1].file_id
        except Exception:
            pass

        # Track new user
        all_users = db.get_all_active_users()
        is_new_user = user_id not in all_users
        if is_new_user:
            db.add_active_user(user_id)

            # --- Process referral ---
            if ref_code and ref_code != user_id:
                added = db.add_referral(ref_code, user_id)
                if added:
                    # Check and grant rewards to referrer
                    try:
                        bot._check_and_grant_referral_reward(bot, ref_code)
                    except AttributeError:
                        pass  # referral handler not registered yet
                    # Notify referrer
                    try:
                        bot.send_message(
                            ref_code,
                            f"👥 **New Referral!**\n\n"
                            f"Someone joined using your referral link!\n"
                            f"✅ Your referral count increased.\n\n"
                            f"Use /referrals to check your progress.",
                            parse_mode='Markdown'
                        )
                    except Exception:
                        pass

            # --- Activate Free Trial ---
            trial_activated = db.activate_trial(user_id, trial_days=FREE_TRIAL_DAYS)

            # Notify owner of new user
            try:
                user_bio = "N/A"
                try:
                    user_bio = bot.get_chat(user_id).bio or "No bio"
                except Exception:
                    pass
                notification = (
                    f"🆕 **New User Joined!**\n\n"
                    f"👤 Name: {user_name}\n"
                    f"📱 Username: @{user_username or 'N/A'}\n"
                    f"🆔 ID: `{user_id}`\n"
                    f"📝 Bio: {user_bio}\n"
                    f"{'🎁 Free trial activated!' if trial_activated else ''}"
                    f"{'🔗 Referred by: ' + str(ref_code) if ref_code else ''}"
                )
                bot.send_message(OWNER_ID, notification, parse_mode='Markdown')
                if photo_file_id:
                    bot.send_photo(OWNER_ID, photo_file_id, caption=f"Profile pic of {user_id}")
            except Exception as e:
                logger.error(f"Failed to notify owner about new user {user_id}: {e}")

        # Build welcome message
        status, expiry_info = get_user_status(user_id, OWNER_ID, admin_ids, subscriptions)
        limits = {'free': 0, 'subscribed': 15, 'admin': 999}
        file_limit = get_file_limit(user_id, OWNER_ID, admin_ids, subscriptions, limits)
        current_files = db.get_user_file_count(user_id)
        limit_str = format_limit(file_limit)
        pending_count = db.get_pending_count() if user_id in admin_ids else 0

        # Trial info
        trial_info = ""
        trial = db.get_trial(user_id)
        if trial and trial['is_active']:
            try:
                expires = datetime.fromisoformat(trial['expires_at'])
                if expires > datetime.now():
                    days_left = (expires - datetime.now()).days
                    trial_info = f"\n🆓 **Free Trial:** {days_left} days remaining"
            except Exception:
                pass

        # Referral info
        ref_count = db.get_referral_count(user_id)
        ref_progress = ref_count % REFERRALS_PER_REWARD
        ref_info = f"\n👥 **Referrals:** {ref_count} ({ref_progress}/{REFERRALS_PER_REWARD} to next reward)"

        welcome = (
            f"👋 Welcome{'back' if not is_new_user else ''}, **{user_name}**!\n\n"
            f"🆔 User ID: `{user_id}`\n"
            f"📱 Username: `@{user_username or 'Not set'}`\n"
            f"🏷 Status: {status}{expiry_info}\n"
            f"📂 Files: {current_files} / {limit_str}"
            f"{trial_info}"
            f"{ref_info}\n\n"
            f"📤 Upload `.py` / `.js` scripts or `.zip` archives.\n"
            f"⚠️ All files require **admin approval** before running.\n\n"
            f"Use the buttons below or type commands."
        )

        reply_markup = reply_keyboard_main(user_id, admin_ids)
        try:
            if photo_file_id:
                bot.send_photo(chat_id, photo_file_id)
            bot.send_message(chat_id, welcome, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error sending welcome to {user_id}: {e}")
            try:
                bot.send_message(chat_id, welcome, reply_markup=reply_markup, parse_mode='Markdown')
            except Exception:
                pass

    @bot.message_handler(commands=['ping'])
    def cmd_ping(message):
        start_time = time.time()
        msg = bot.reply_to(message, "🏓 Pong!")
        latency = round((time.time() - start_time) * 1000, 2)
        uptime_str = get_uptime()
        bot.edit_message_text(
            f"🏓 **Pong!**\n⚡ Latency: `{latency}ms`\n⏱ Uptime: `{uptime_str}`",
            message.chat.id, msg.message_id, parse_mode='Markdown'
        )

    @bot.message_handler(commands=['uptime'])
    def cmd_uptime(message):
        uptime_str = get_uptime()
        bot.reply_to(message, f"⏱ Bot Uptime: `{uptime_str}`", parse_mode='Markdown')

    @bot.message_handler(commands=['status'])
    def cmd_status(message):
        from services.script_runner import get_running_count, get_user_running_count
        user_id = message.from_user.id
        total_users = db.get_total_user_count()
        total_files = db.get_total_file_count()
        running_count = get_running_count()
        user_running = get_user_running_count(user_id)

        stats = (
            f"📊 **Bot Statistics**\n\n"
            f"👥 Total Users: `{total_users}`\n"
            f"📁 Total Files: `{total_files}`\n"
            f"🟢 Active Scripts: `{running_count}`\n"
            f"📌 Your Running Scripts: `{user_running}`"
        )

        if user_id in admin_ids:
            pending = db.get_pending_count()
            banned = len(db.get_banned_users())
            maint = db.get_maintenance_status()
            trial_count = len(db.get_all_active_trials())
            stats += (
                f"\n\n🔧 **Admin Info**\n"
                f"🔒 Bot Locked: `{'Yes' if bot_locked_ref[0] else 'No'}`\n"
                f"🛠 Maintenance: `{'ON' if maint['enabled'] else 'OFF'}`\n"
                f"📋 Pending Approvals: `{pending}`\n"
                f"🚫 Banned Users: `{banned}`\n"
                f"🆓 Active Trials: `{trial_count}`"
            )

        bot.reply_to(message, stats, parse_mode='Markdown')
