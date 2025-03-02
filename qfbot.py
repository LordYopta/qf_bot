import logging
import random
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.error import TelegramError
import os

# Токен бота
TOKEN = os.environ.get('TELEGRAM_TOKEN', '7326557942:AAFjCHJWHq4_mUDDdqjMCrqgC-RzLb4Bo90')

# Список запрещённых слов
BANNED_WORDS = ['спам', 'реклама', 'продам']

# Правила группы
RULES = """
*Правила QF Network* 📜
1. 🚫 Никакого спама!
2. 🔗 Без рекламы стороннего.
3. 🤝 Уважайте других.
4. 🗣️ Без мата.
"""

warnings = {}
spam_count = {}
last_reset = {}
karma = {}
last_karma_update = {}
MAX_SPAM_PER_DAY = 2

DUEL_QUESTIONS = [
    {"question": "Какое правило запрещает спам?", "options": [("A) Правило 1", True), ("B) Правило 2", False), ("C) Правило 3", False)]},
    {"question": "Что нельзя рекламировать в группе?", "options": [("A) QF Network", False), ("B) Сторонние проекты", True), ("C) Свои сообщения", False)]}
]

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Визуальный прогресс-бар для спама
def get_spam_progress(count, max_count):
    filled = "█" * count
    empty = "░" * (max_count - count)
    return f"[{filled}{empty}] {count}/{max_count}"

# Инициализация данных пользователя
def init_user_data(user_id, current_time):
    if user_id not in spam_count:
        spam_count[user_id] = 0
        last_reset[user_id] = current_time
    if user_id not in karma:
        karma[user_id] = 0
        last_karma_update[user_id] = current_time

# Приветствие новых участников
async def greet_new_member(update: Update, context):
    message = update.message
    if message and message.new_chat_members:
        chat_id = update.effective_chat.id
        if 'chat_id' not in context.bot_data:
            context.bot_data['chat_id'] = chat_id
        current_time = int(time.time())
        for user in message.new_chat_members:
            logger.info(f"Новый участник: {user.first_name}")
            init_user_data(user.id, current_time)
            welcome_message = f"👋 *Добро пожаловать, {user.first_name}!* 🎉\nПравила: /rules"
            msg = await context.bot.send_message(chat_id=chat_id, text=welcome_message, parse_mode='Markdown')
            context.job_queue.run_once(delete_message, 300, data={'chat_id': msg.chat_id, 'message_id': msg.message_id})

# Удаление сообщения через время
async def delete_message(context):
    job_data = context.job.data
    try:
        await context.bot.delete_message(chat_id=job_data['chat_id'], message_id=job_data['message_id'])
    except TelegramError as e:
        logger.info(f"Не удалось удалить сообщение: {e}")

# Команда /rules
async def rules(update: Update, context):
    await update.message.reply_text(RULES, parse_mode='Markdown')

# Команда /help
async def help_command(update: Update, context):
    help_text = """
    🤖 *Бот QF Network* 🤖
    👋 Приветствует новичков.
    🚫 Удаляет спам:
      - 1-2 раза: мут + вопрос (✅ снимает).
      - 3-й раз: 🚨 мут на сутки.
    ⚠️ 3 предупреждения = бан.
    ⭐ *Карма*: +1/день без спама, -1 за спам.
    🔧 */warn* (админы): бан или отмена.
    📩 */report*: сообщить о нарушении (для всех).
    📊 */karma*: ваша карма или изменение (админы).
    ℹ️ */rules*: правила группы.
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

# Сброс счётчика спама и обновление кармы
async def reset_spam_count(context):
    current_time = int(time.time())
    chat_id = context.bot_data.get('chat_id')
    for user_id in list(spam_count.keys()):
        if current_time - last_reset.get(user_id, 0) >= 86400:
            spam_count[user_id] = 0
            last_reset[user_id] = current_time
            logger.info(f"Сброс счётчика спама для {user_id}")
    for user_id in list(karma.keys()):
        if current_time - last_karma_update.get(user_id, 0) >= 86400:
            karma[user_id] += 1
            last_karma_update[user_id] = current_time
    if current_time % (7 * 86400) < 86400 and chat_id:
        top_user = max(karma.items(), key=lambda x: x[1], default=(None, 0))
        flop_user = min(karma.items(), key=lambda x: x[1], default=(None, 0))
        if top_user[0] and flop_user[0]:
            top_name = (await context.bot.get_chat_member(chat_id, top_user[0])).user.first_name
            flop_name = (await context.bot.get_chat_member(chat_id, flop_user[0])).user.first_name
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🏆 *Герой недели*: *{top_name}* с кармой *{top_user[1]}* ⭐\n" \
                     f"😔 *Нарушитель недели*: *{flop_name}* с кармой *{flop_user[1]}*",
                parse_mode='Markdown'
            )

# Антиспам с дуэлью и лимитом
async def anti_spam(update: Update, context):
    message = update.message
    user_id = message.from_user.id
    chat_id = message.chat_id
    text = message.text.lower() if message.text else ""
    logger.info(f"Получено сообщение: {text}")
    
    if 'chat_id' not in context.bot_data:
        context.bot_data['chat_id'] = chat_id
    
    for word in BANNED_WORDS:
        if word in text:
            await context.bot.delete_message(chat_id=chat_id, message_id=message.message_id)
            current_time = int(time.time())
            init_user_data(user_id, current_time)

            spam_count[user_id] += 1
            karma[user_id] -= 1
            logger.info(f"Спам от {user_id}, счёт: {spam_count[user_id]}, карма: {karma[user_id]}")

            if spam_count[user_id] > MAX_SPAM_PER_DAY:
                await context.bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions={"can_send_messages": False}, until_date=current_time + 86400)
                msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🚨 *{message.from_user.first_name}* превысил лимит!\n" \
                         f"{get_spam_progress(spam_count[user_id], MAX_SPAM_PER_DAY)}\n" \
                         f"_Мут на 24 часа._ Карма: *{karma[user_id]}* ⭐",
                    parse_mode='Markdown'
                )
                context.job_queue.run_once(delete_message, 300, data={'chat_id': msg.chat_id, 'message_id': msg.message_id})
                warnings[user_id] = 0
                return

            warnings[user_id] = warnings.get(user_id, 0) + 1
            warn_count = warnings[user_id]

            if warn_count == 1:
                await context.bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions={"can_send_messages": False}, until_date=current_time + 3600)
                question_data = random.choice(DUEL_QUESTIONS)
                keyboard = [[InlineKeyboardButton(text, callback_data=f"duel_{user_id}_{'correct' if correct else 'wrong'}")] for text, correct in question_data["options"]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ *{message.from_user.first_name}*, нарушение!\n" \
                         f"{get_spam_progress(spam_count[user_id], MAX_SPAM_PER_DAY)}\n" \
                         f"_Мут на 1 час._ Карма: *{karma[user_id]}* ⭐\n" \
                         f"Ответь:\n*{question_data['question']}*",
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
                context.user_data[user_id] = {'duel_message_id': msg.message_id}
            else:
                msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ *{message.from_user.first_name}*, запрещённые слова!\n" \
                         f"{get_spam_progress(spam_count[user_id], MAX_SPAM_PER_DAY)}\n" \
                         f"_Предупреждение {warn_count}/3._ Карма: *{karma[user_id]}* ⭐",
                    parse_mode='Markdown'
                )
                context.job_queue.run_once(delete_message, 300, data={'chat_id': msg.chat_id, 'message_id': msg.message_id})
                if warn_count >= 3:
                    await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                    msg = await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"🚫 *{message.from_user.first_name}* забанен!\nКарма: *{karma[user_id]}* ⭐",
                        parse_mode='Markdown'
                    )
                    context.job_queue.run_once(delete_message, 300, data={'chat_id': msg.chat_id, 'message_id': msg.message_id})
                    warnings[user_id] = 0
            break

# Команда /report для участников
async def report_command(update: Update, context):
    if not update.message.reply_to_message:
        await update.message.reply_text("📩 Ответьте на сообщение, на которое хотите пожаловаться!", parse_mode='Markdown')
        return
    reporter = update.effective_user
    target_user = update.message.reply_to_message.from_user
    reason = " ".join(context.args) if context.args else "нарушение"
    chat_id = update.effective_chat.id

    keyboard = [
        [InlineKeyboardButton("🚫 Забанить", callback_data=f"report_ban_{target_user.id}"),
         InlineKeyboardButton("✅ Игнорировать", callback_data=f"report_ignore_{target_user.id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"🚨 *Жалоба от {reporter.first_name}* на *{target_user.first_name}*!\n" \
             f"Причина: _{reason}_\nАдмины, что делать?",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.user_data[target_user.id] = {'report_message_id': msg.message_id}

# Команда /karma
async def karma_command(update: Update, context):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    member = await context.bot.get_chat_member(chat_id, user_id)

    if member.status in ['administrator', 'creator'] and len(context.args) >= 2:
        try:
            target_username = context.args[0].lstrip('@')
            change = int(context.args[1])
            target_member = next((m for m in await update.effective_chat.get_members() if m.user.username == target_username), None)
            if not target_member:
                await update.message.reply_text("🚫 Пользователь не найден!", parse_mode='Markdown')
                return
            target_id = target_member.user.id
            karma[target_id] = karma.get(target_id, 0) + change
            await update.message.reply_text(
                f"⭐ Карма *{target_member.user.first_name}* изменена на *{change}*. Теперь: *{karma[target_id]}* ⭐",
                parse_mode='Markdown'
            )
        except ValueError:
            await update.message.reply_text("🔧 Использование: /karma @username +1 или -1", parse_mode='Markdown')
    else:
        karma_value = karma.get(user_id, 0)
        await update.message.reply_text(f"⭐ Твоя карма, *{update.effective_user.first_name}*: *{karma_value}* ⭐", parse_mode='Markdown')

# Команда /warn для администраторов
async def warn_user(update: Update, context):
    member = await update.effective_chat.get_member(update.effective_user.id)
    if member.status not in ['administrator', 'creator']:
        await update.message.reply_text("🔧 Эта команда для админов.", parse_mode='Markdown')
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("📩 Ответьте на сообщение нарушителя.", parse_mode='Markdown')
        return
    target_user = update.message.reply_to_message.from_user
    user_id = target_user.id
    reason = " ".join(context.args) if context.args else "нарушение правил"
    keyboard = [[InlineKeyboardButton("🚫 Заблокировать", callback_data=f"ban_{user_id}"), InlineKeyboardButton("✅ Отменить", callback_data=f"cancel_{user_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await update.message.reply_text(
        f"⚠️ Жалоба на *{target_user.first_name}*.\nПричина: _{reason}_\nЧто делать?",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.user_data[user_id] = {'warn_message_id': msg.message_id}

# Обработка нажатий на кнопки
async def button_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    data_parts = query.data.split('_')
    action = data_parts[0]
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    member = await context.bot.get_chat_member(chat_id, user_id)

    if action in ["ban", "cancel", "report"]:
        target_id = int(data_parts[2]) if action == "report" else int(data_parts[1])
        is_admin = member.status in ['administrator', 'creator']

        if not is_admin:
            # Отправляем личное сообщение не-админу
            await context.bot.send_message(
                chat_id=user_id,
                text="🔧 Эта функция доступна только администраторам!",
                parse_mode='Markdown'
            )
            return

        # Действие админа
        if action == "ban" or (action == "report" and data_parts[1] == "ban"):
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=target_id)
            await query.edit_message_text(f"🚫 Забанен администратором *{query.from_user.first_name}*.", parse_mode='Markdown')
            warnings[target_id] = 0
        elif action == "cancel" or (action == "report" and data_parts[1] == "ignore"):
            await query.edit_message_text("✅ Жалоба отклонена.", parse_mode='Markdown')

        # Удаление сообщения после действия админа
        key = 'report_message_id' if action == "report" else 'warn_message_id'
        if target_id in context.user_data and key in context.user_data[target_id]:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=context.user_data[target_id][key])
            except TelegramError as e:
                logger.info(f"Не удалось удалить сообщение: {e}")
            del context.user_data[target_id]

    elif action == "duel":
        user_id = int(data_parts[1])
        result = data_parts[2]
        if result == "correct":
            warnings[user_id] = 0
            await context.bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions={"can_send_messages": True})
            await query.edit_message_text(f"✅ *{query.from_user.first_name}*, правильно! Мут снят.\nКарма: *{karma[user_id]}* ⭐", parse_mode='Markdown')
        else:
            warnings[user_id] = 2
            await query.edit_message_text(f"❌ Неверно! Мут на 1 час.\nКарма: *{karma[user_id]}* ⭐", parse_mode='Markdown')
        if user_id in context.user_data and 'duel_message_id' in context.user_data[user_id]:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=context.user_data[user_id]['duel_message_id'])
            except TelegramError as e:
                logger.info(f"Не удалось удалить дуэль: {e}")
            del context.user_data[user_id]

# Основная функция
def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, greet_new_member))
    application.add_handler(CommandHandler("rules", rules))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("karma", karma_command))
    application.add_handler(CommandHandler("warn", warn_user))
    application.add_handler(CommandHandler("report", report_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anti_spam))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.job_queue.run_repeating(reset_spam_count, interval=86400, first=0)
    application.run_polling()

if __name__ == '__main__':
    main()