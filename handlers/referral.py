"""
Referral system handlers — /referrals command, referral stats, leaderboard.
"""
import logging
from datetime import datetime

import database as db
from config import REFERRALS_PER_REWARD, REFERRAL_REWARD_SLOTS, YOUR_USERNAME

logger = logging.getLogger(__name__)


def register(bot, admin_ids, subscriptions, bot_locked_ref):
    """Register referral-related command handlers."""

    @bot.message_handler(commands=['referrals', 'ref', 'invite'])
    def cmd_referrals(message):
        user_id = message.from_user.id
        if db.is_banned(user_id):
            bot.reply_to(message, "🚫 You are banned.")
            return

        _send_referral_info(bot, user_id, message.chat.id)

    @bot.message_handler(commands=['leaderboard'])
    def cmd_leaderboard(message):
        _send_leaderboard(bot, message.chat.id)

    # Store functions for callback use
    bot._send_referral_info = _send_referral_info
    bot._send_leaderboard = _send_leaderboard
    bot._check_and_grant_referral_reward = _check_and_grant_referral_reward


def _send_referral_info(bot, user_id, chat_id):
    """Send referral stats and share link to user."""
    from utils.keyboards import referral_keyboard
    try:
        bot_info = bot.get_me()
        bot_username = bot_info.username
    except Exception:
        bot_username = YOUR_USERNAME.lstrip('@')

    ref_count = db.get_referral_count(user_id)
    rewards_earned = db.get_referral_extra_slots(user_id)
    next_reward_at = REFERRALS_PER_REWARD - (ref_count % REFERRALS_PER_REWARD)
    if ref_count > 0 and ref_count % REFERRALS_PER_REWARD == 0:
        next_reward_at = REFERRALS_PER_REWARD

    ref_link = f"https://t.me/{bot_username}?start=ref{user_id}"
    progress_bar = _make_progress_bar(ref_count % REFERRALS_PER_REWARD, REFERRALS_PER_REWARD)

    text = (
        f"👥 **Your Referral Stats**\n\n"
        f"🔗 Your Referral Link:\n`{ref_link}`\n\n"
        f"📊 **Progress**\n"
        f"✅ Total Referrals: `{ref_count}`\n"
        f"🎁 Extra Slots Earned: `{rewards_earned}`\n"
        f"🎯 Next Reward in: `{next_reward_at}` more referrals\n\n"
        f"Progress: {progress_bar} `{ref_count % REFERRALS_PER_REWARD}/{REFERRALS_PER_REWARD}`\n\n"
        f"💡 **How it works:**\n"
        f"• Share your referral link with friends\n"
        f"• Every **{REFERRALS_PER_REWARD} valid referrals** = **+{REFERRAL_REWARD_SLOTS} extra bot slot**\n"
        f"• Referred users must be new to this bot\n"
        f"• Self-referrals do not count"
    )

    markup = referral_keyboard(user_id, bot_username)
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode='Markdown')


def _send_leaderboard(bot, chat_id, limit=10):
    """Send referral leaderboard."""
    leaders = db.get_referral_leaderboard(limit=limit)
    if not leaders:
        bot.send_message(chat_id, "🏆 **Referral Leaderboard**\n\nNo referrals yet. Be the first!", parse_mode='Markdown')
        return

    text = "🏆 **Top Referrers**\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, entry in enumerate(leaders):
        medal = medals[i] if i < 3 else f"{i+1}."
        text += f"{medal} `{entry['user_id']}` — **{entry['referral_count']}** referrals\n"

    bot.send_message(chat_id, text, parse_mode='Markdown')


def _check_and_grant_referral_reward(bot, referrer_id):
    """
    Check if referrer has earned a new reward after their latest referral.
    Grants reward and notifies user if milestone is reached.
    """
    ref_count = db.get_referral_count(referrer_id)
    rewards_earned = db.get_referral_rewards_count(referrer_id)

    # Calculate how many rewards should have been earned
    rewards_due = ref_count // REFERRALS_PER_REWARD
    rewards_to_grant = rewards_due - rewards_earned

    for _ in range(rewards_to_grant):
        db.grant_referral_reward(referrer_id, reward_type='slot', reward_value=REFERRAL_REWARD_SLOTS)
        try:
            bot.send_message(
                referrer_id,
                f"🎉 **Referral Reward Unlocked!**\n\n"
                f"You've reached **{ref_count} referrals** milestone!\n"
                f"✅ **+{REFERRAL_REWARD_SLOTS} extra bot hosting slot** added to your account!\n\n"
                f"Use /referrals to see your updated stats.",
                parse_mode='Markdown'
            )
            logger.info(f"Granted referral reward to {referrer_id}")
        except Exception as e:
            logger.warning(f"Could not notify {referrer_id} about referral reward: {e}")


def _make_progress_bar(current, total, length=10):
    """Create a text progress bar."""
    filled = int((current / total) * length) if total > 0 else 0
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}]"
