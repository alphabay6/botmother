"""
File handlers — upload, check files, document handler.
Includes: Smart ZIP file picker, free-user restrictions, trial enforcement.
All uploads go through admin approval workflow.
"""
import os
import logging
import telebot

import database as db
from config import OWNER_ID, MAX_FILE_SIZE, ALLOWED_EXTENSIONS
from utils.helpers import get_file_limit, format_limit
from utils.force_join import check_force_join, send_force_join_message
from services.approval import submit_for_approval
from services.file_manager import get_user_folder, save_file_to_pending, handle_git_clone, extract_zip_and_list_files
from services.script_runner import is_running

logger = logging.getLogger(__name__)


def register(bot, admin_ids, subscriptions, bot_locked_ref):
    """Register file-related handlers."""

    def _check_access(message):
        """Check if user can access the bot."""
        user_id = message.from_user.id
        chat_id = message.chat.id
        if db.is_banned(user_id):
            bot.reply_to(message, "🚫 You are banned.")
            return False
        maint = db.get_maintenance_status()
        if maint['enabled'] and user_id not in admin_ids:
            bot.reply_to(message, f"🛠 {maint['message']}")
            return False
        if bot_locked_ref[0] and user_id not in admin_ids:
            bot.reply_to(message, "🔒 Bot is locked.")
            return False
        # Force join check
        if user_id not in admin_ids:
            not_joined = check_force_join(bot, user_id)
            if not_joined:
                send_force_join_message(bot, chat_id, not_joined)
                return False
        return True

    def _check_hosting_access(message):
        """Check if user has hosting rights (trial, subscription, or admin)."""
        user_id = message.from_user.id
        if user_id in admin_ids or user_id == OWNER_ID:
            return True, None
        # Check subscription
        if user_id in subscriptions and subscriptions[user_id] > __import__('datetime').datetime.now():
            return True, None
        # Check trial
        if db.is_trial_active(user_id):
            return True, None
        # Check if they have referral-based slots
        extra = db.get_referral_extra_slots(user_id)
        if extra > 0:
            return True, None
        # No access
        return False, (
            "❌ **No Hosting Access**\n\n"
            "You need one of the following to host scripts:\n\n"
            "🆓 **Free Trial** — You may have used your 18-day trial already\n"
            "⭐ **Premium Subscription** — Contact admin to subscribe\n"
            "👥 **Referrals** — Refer 5 friends to earn 1 free hosting slot\n\n"
            "Use /referrals to get your referral link!"
        )

    @bot.message_handler(commands=['uploadfile'])
    def cmd_upload(message):
        if not _check_access(message):
            return
        user_id = message.from_user.id

        # Check hosting access
        has_access, deny_msg = _check_hosting_access(message)
        if not has_access:
            bot.reply_to(message, deny_msg, parse_mode='Markdown')
            return

        limits = {'free': 0, 'subscribed': 15, 'admin': 999}
        file_limit = get_file_limit(user_id, OWNER_ID, admin_ids, subscriptions, limits)
        current = db.get_user_file_count(user_id)
        if file_limit == 0:
            bot.reply_to(message, "❌ You have no file hosting slots.\nGet a subscription or earn slots via referrals!")
            return
        if current >= file_limit:
            bot.reply_to(message, f"📁 File limit reached ({current}/{format_limit(file_limit)}). Delete files first or earn more slots via /referrals.")
            return
        bot.reply_to(message, "📤 Send your Python (`.py`), JS (`.js`), or ZIP (`.zip`) file.\n⚠️ Files require admin approval before they can run.")

    @bot.message_handler(commands=['checkfiles'])
    def cmd_check_files(message):
        if not _check_access(message):
            return
        _show_user_files(message.from_user.id, message.chat.id, bot, reply_to=message)

    @bot.message_handler(commands=['clone'])
    def cmd_clone(message):
        if not _check_access(message):
            return

        has_access, deny_msg = _check_hosting_access(message)
        if not has_access:
            bot.reply_to(message, deny_msg, parse_mode='Markdown')
            return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            bot.reply_to(message, "Usage: `/clone <github_repo_url>`", parse_mode='Markdown')
            return

        git_url = args[1]
        if not git_url.startswith("http"):
            bot.reply_to(message, "❌ Invalid URL format.")
            return

        user_id = message.from_user.id
        chat_id = message.chat.id

        limits = {'free': 0, 'subscribed': 15, 'admin': 999}
        file_limit = get_file_limit(user_id, OWNER_ID, admin_ids, subscriptions, limits)
        current = db.get_user_file_count(user_id)
        if current >= file_limit:
            bot.reply_to(message, f"📁 File limit reached ({current}/{format_limit(file_limit)}).")
            return

        result = handle_git_clone(git_url, user_id, bot, chat_id)
        if result:
            main_script, file_type = result
            approval_id = submit_for_approval(user_id, main_script, file_type, None, bot, admin_ids)
            if approval_id:
                bot.send_message(chat_id,
                                 f"📋 Repository cloned! Main script: `{main_script}`\n"
                                 f"⏳ Submitted for admin approval (ID: #{approval_id}).\n"
                                 f"You'll be notified when approved.",
                                 parse_mode='Markdown')
            else:
                bot.send_message(chat_id, "❌ Error submitting repo for approval.")

    @bot.message_handler(content_types=['document'])
    def handle_document(message):
        if not _check_access(message):
            return

        user_id = message.from_user.id
        chat_id = message.chat.id
        doc = message.document

        logger.info(f"Doc from {user_id}: {doc.file_name} ({doc.mime_type}), Size: {doc.file_size}")

        # Check hosting access
        has_access, deny_msg = _check_hosting_access(message)
        if not has_access:
            bot.reply_to(message, deny_msg, parse_mode='Markdown')
            return

        # Check file limit
        limits = {'free': 0, 'subscribed': 15, 'admin': 999}
        file_limit = get_file_limit(user_id, OWNER_ID, admin_ids, subscriptions, limits)
        current = db.get_user_file_count(user_id)
        if file_limit == 0 or current >= file_limit:
            bot.reply_to(message, f"📁 File limit reached ({current}/{format_limit(file_limit)}). Use /referrals to earn more slots.")
            return

        file_name = doc.file_name
        if not file_name:
            bot.reply_to(message, "❌ File has no name.")
            return

        file_ext = os.path.splitext(file_name)[1].lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            bot.reply_to(message, f"❌ Only `.py`, `.js`, `.zip` files allowed.")
            return

        if doc.file_size > MAX_FILE_SIZE:
            bot.reply_to(message, f"❌ File too large (Max: {MAX_FILE_SIZE // 1024 // 1024} MB).")
            return

        try:
            # Forward to owner for record
            try:
                bot.forward_message(OWNER_ID, chat_id, message.message_id)
                bot.send_message(OWNER_ID,
                                 f"📥 File `{file_name}` from {message.from_user.first_name} (`{user_id}`)",
                                 parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Failed to forward to owner: {e}")

            # Download file
            wait_msg = bot.reply_to(message, f"⬇️ Downloading `{file_name}`...", parse_mode='Markdown')
            file_info = bot.get_file(doc.file_id)
            file_content = bot.download_file(file_info.file_path)

            if file_content is None:
                bot.edit_message_text(f"❌ Error: Failed to download `{file_name}`.",
                                      chat_id, wait_msg.message_id, parse_mode='Markdown')
                return

            bot.edit_message_text(f"✅ Downloaded `{file_name}`. Processing...",
                                  chat_id, wait_msg.message_id, parse_mode='Markdown')

            if file_ext == '.zip':
                # --- Smart ZIP File Picker ---
                result = extract_zip_and_list_files(file_content, file_name, user_id, bot, chat_id)
                if result:
                    files_list, extracted_path = result
                    if len(files_list) == 1:
                        # Only one runnable file — auto select
                        selected_file = files_list[0]
                        file_type = 'py' if selected_file.endswith('.py') else 'js'
                        _submit_zip_file(bot, user_id, chat_id, extracted_path, selected_file, file_type, admin_ids)
                    else:
                        # Multiple files — ask user to pick
                        from utils.keyboards import zip_file_picker_keyboard
                        db.save_zip_selection(user_id, file_name, extracted_path, files_list)
                        markup = zip_file_picker_keyboard(user_id, files_list)
                        bot.send_message(
                            chat_id,
                            f"📦 **ZIP Extracted!** Found **{len(files_list)}** runnable files.\n\n"
                            f"👇 **Select which file to run as the main script:**",
                            reply_markup=markup,
                            parse_mode='Markdown'
                        )
            else:
                # Single file — save to pending and submit for approval
                file_type = 'py' if file_ext == '.py' else 'js'
                save_file_to_pending(user_id, file_name, file_content)
                approval_id = submit_for_approval(user_id, file_name, file_type, None, bot, admin_ids)
                if approval_id:
                    bot.send_message(chat_id,
                                     f"📋 File `{file_name}` received!\n"
                                     f"⏳ Submitted for admin approval (ID: #{approval_id}).\n"
                                     f"You'll be notified when approved.",
                                     parse_mode='Markdown')
                else:
                    bot.send_message(chat_id, "❌ Error submitting for approval.")

        except telebot.apihelper.ApiTelegramException as e:
            logger.error(f"Telegram API error handling file for {user_id}: {e}")
            if "file is too big" in str(e).lower():
                bot.reply_to(message, "❌ File too large for Telegram API (~20MB limit).")
            else:
                bot.reply_to(message, f"❌ Telegram API Error: {str(e)}")
        except Exception as e:
            logger.error(f"Error handling file for {user_id}: {e}", exc_info=True)
            bot.reply_to(message, f"❌ Error: {str(e)}")


def _submit_zip_file(bot, user_id, chat_id, extracted_path, selected_file, file_type, admin_ids):
    """Submit selected file from ZIP for admin approval."""
    import shutil
    import os
    from services.file_manager import get_pending_folder

    try:
        # Copy selected file to pending folder
        source_path = os.path.join(extracted_path, selected_file)
        pending_folder = get_pending_folder(user_id)
        dest_path = os.path.join(pending_folder, selected_file)

        if not os.path.exists(source_path):
            bot.send_message(chat_id, f"❌ File `{selected_file}` not found in extracted ZIP.")
            return

        os.makedirs(pending_folder, exist_ok=True)
        shutil.copy2(source_path, dest_path)

        from services.approval import submit_for_approval
        approval_id = submit_for_approval(user_id, selected_file, file_type, None, bot, admin_ids)
        if approval_id:
            bot.send_message(
                chat_id,
                f"✅ **File Selected!**\n\n"
                f"📄 Script: `{selected_file}`\n"
                f"⏳ Submitted for admin approval (ID: #{approval_id}).\n"
                f"You'll be notified when approved.",
                parse_mode='Markdown'
            )
        else:
            bot.send_message(chat_id, "❌ Error submitting file for approval.")

        # Cleanup extracted folder
        try:
            shutil.rmtree(extracted_path, ignore_errors=True)
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Error submitting ZIP file: {e}", exc_info=True)
        bot.send_message(chat_id, f"❌ Error: {str(e)}")


def _show_user_files(user_id, chat_id, bot, reply_to=None, message_id=None):
    """Show user's files with status indicators."""
    from telebot import types

    files = db.get_user_files(user_id)
    if not files:
        text = "📂 **Your Files**\n\n_(No files uploaded yet)_"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📤 Upload File", callback_data='upload'))
        if reply_to:
            bot.reply_to(reply_to, text, reply_markup=markup, parse_mode='Markdown')
        elif message_id:
            try:
                bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode='Markdown')
            except Exception:
                bot.send_message(chat_id, text, reply_markup=markup, parse_mode='Markdown')
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for file_name, file_type in sorted(files):
        running = is_running(user_id, file_name)
        status = "🟢 Running" if running else "🔴 Stopped"
        btn_text = f"{file_name} ({file_type}) — {status}"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f'file_{user_id}_{file_name}'))

    markup.add(types.InlineKeyboardButton("🔙 Back to Main", callback_data='back_to_main'))

    text = "📂 **Your Files**\nTap a file to manage it."
    if reply_to:
        bot.reply_to(reply_to, text, reply_markup=markup, parse_mode='Markdown')
    elif message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode='Markdown')
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" not in str(e):
                logger.error(f"Error editing file list: {e}")
