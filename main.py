import requests
import db
from bs4 import BeautifulSoup
from telegram import MessageOriginChannel
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler, CallbackQueryHandler
)
import feedparser
from db import save_bound_chat_id, load_bound_chat_ids, delete_bound_chat_id
import os


db.init_db()


# === Состояние и временное хранилище для выбора чатов ===
SELECT_CHANNELS = range(1)
user_selected_chats = {}

# === Получение статьи ===
def fetch_formatted_article(url, title):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')

        content = soup.find("div", class_="topic-body__content")
        if not content:
            return None, "📝 Текст статьи не найден."

        paragraphs = content.find_all("p")
        all_text = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 40]

        if len(all_text) < 1:
            return None, "📝 Недостаточно данных для пересказа."

        intro = all_text[0]
        details = all_text[1] if len(all_text) > 1 else ""

        # Формируем текст новости
        text = f"<b>📰 {title}</b>\n\n"
        text += f"<b>📍 Кратко:</b>\n{intro}\n\n"
        if details:
            text += f"<b>📌 Подробности:</b>\n{details}\n\n"
        text += f"🔗 <i>Источник: Lenta.ru</i>"

        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            image_url = og_image["content"]
        else:
            img_tag = content.find("img")
            image_url = img_tag['src'] if img_tag and 'src' in img_tag.attrs else None

        if image_url and image_url.startswith("//"):
            image_url = "https:" + image_url

        return image_url, text

    except Exception as e:
        return None, f"⚠️ Ошибка при обработке статьи: {e}"

# === Новости ===
def get_latest_news():
    """Получает самую свежую новость"""
    try:
        feed = feedparser.parse(RSS_URL)
        if not feed.entries:
            print("[DEBUG] Лента пуста или недоступна.")
            return None, None

        entry = feed.entries[0]  # Самая свежая новость
        title = entry.title
        link = entry.link
        image_url, formatted_article = fetch_formatted_article(link, title)
        if formatted_article:
            return formatted_article, image_url
        return None, None

    except Exception as e:
        print(f"[DEBUG] Ошибка загрузки новостей: {e}")
        return None, None

def get_news():
    """Для обратной совместимости - возвращает одну новость в виде списка"""
    text, image = get_latest_news()
    if text:
        return [(text, image)]
    return []

def truncate_text(text, max_len=1024):
    return text[:max_len - 3] + "..." if len(text) > max_len else text

# # === Работа с привязками ===
# def save_bound_chat_id(chat_id):
#     try:
#         chats = load_bound_chat_ids()
#         if chat_id not in chats:
#             chats.append(chat_id)
#             with open(BOUND_CHATS_FILE, "w") as f:
#                 f.write("\n".join(str(c) for c in chats))
#     except Exception as e:
#         print(f"[DEBUG] Ошибка сохранения чата: {e}")

# def load_bound_chat_ids():
#     if not os.path.exists(BOUND_CHATS_FILE):
#         return []
#     try:
#         with open(BOUND_CHATS_FILE, "r") as f:
#             return [int(line.strip()) for line in f if line.strip().lstrip("-").isdigit()]
#     except Exception as e:
#         print(f"[DEBUG] Ошибка загрузки чатов: {e}")
#         return []

# def delete_bound_chat_id(chat_id):
#     try:
#         chats = load_bound_chat_ids()
#         if chat_id in chats:
#             chats.remove(chat_id)
#             with open(BOUND_CHATS_FILE, "w") as f:
#                 f.write("\n".join(str(c) for c in chats))
#     except Exception as e:
#         print(f"[DEBUG] Ошибка удаления чата: {e}")

# === Команды ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ['📰 Получить новости', '📡 Отправить в чаты'],
        ['🔗 Привязать чат', '❌ Отвязать чат'],
        ['📋 Список чатов', '📢 Выбрать чаты'],
        ['⚙️ Инструкция', 'ℹ️ О боте', '❓ Помощь']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    welcome_text = (
        "   📰 БОТ НОВОСТЕЙ LENTA.RU   \n\n"

        "👋 <b>Добро пожаловать!</b>\n\n"
        "Я помогу вам получать свежие новости с Lenta.ru и транслировать их в ваши каналы и группы.\n\n"

        "<b>📋 Что я умею:</b>\n\n"
        "📰 <b>Получить новости</b> — показать самую свежую новость\n"
        "📡 <b>Транслировать</b> — отправить новость в привязанные чаты\n"
        "🔗 <b>Привязать чат</b> — добавить канал/группу для трансляции\n"
        "❌ <b>Отвязать чат</b> — убрать канал/группу из трансляции\n"
        "📢 <b>Выбрать чаты</b> — отправить новости в заданные чаты\n\n"

        "💡 <b>Быстрый старт:</b>\n"
        "Используйте команду /setup для подробных инструкций\n\n"
        "ℹ️ Подробнее — /about | ❓ Помощь — /help"
    )
    await update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (

        "        ❓ СПРАВКА            \n\n"

        "<b>📌 Основные команды:</b>\n\n"
        "/start — главное меню с кнопками\n"
        "/setup — подробная инструкция по настройке\n"
        "/latest — отправить самую свежую новость во все привязанные чаты\n"
        "/bind — привязать текущий чат/канал/группу\n"
        "/unbind — отвязать текущий чат от трансляции\n"
        "/list — показать список всех привязанных чатов\n"
        "/broadcast — выбрать чаты и отправить новость\n"
        "/about — информация о боте\n"
        "/help — эта справка\n\n"

        "<b>🔧 Как это работает:</b>\n\n"
        "1️⃣ Добавьте бота в группу/канал (см. /setup)\n"
        "2️⃣ Привяжите чат командой /bind\n"
        "3️⃣ Используйте /latest для отправки новости\n\n"
        "💡 <i>Все команды также доступны через кнопки меню</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (

        "      ⚙️ ИНСТРУКЦИЯ ПО НАСТРОЙКЕ БОТА  \n\n"

        "<b>📋 Пошаговая инструкция:</b>\n\n"

        "<b>Шаг 1️⃣: Добавление бота в группу/канал</b>\n\n"
        "🔸 <b>Для группы:</b>\n"
        "  1. Откройте настройки группы\n"
        "  2. Выберите «Участники»\n"
        "  3. Нажмите «Добавить участников»\n"
        "  4. Найдите бота и добавьте\n"
        "  5. Обязательно сделайте бота <b>администратором</b>\n\n"
        "🔸 <b>Для канала:</b>\n"
        "  1. Откройте настройки канала\n"
        "  2. Выберите «Администраторы»\n"
        "  3. Нажмите «Добавить администратора»\n"
        "  4. Найдите бота и добавьте\n"
        "  5. Дайте боту права на отправку сообщений\n\n"

        "<b>Шаг 2️⃣: Привязка чата к боту</b>\n\n"
        "🔸 <b>Для группы:</b>\n"
        "  1. Откройте группу\n"
        "  2. Напишите команду: <code>/bind</code>\n"
        "  3. Бот подтвердит привязку ✅\n\n"
        "🔸 <b>Для канала:</b>\n"
        "  1. Откройте ваш канал\n"
        "  2. Перешлите любое сообщение из канала этому боту (в личном чате)\n"
        "  3. Бот автоматически привяжет канал ✅\n\n"
        "⚠️ <i>Важно: только администратор группы/канала может привязать чат</i>\n\n"
        "💡 <i>Примечание: команды в каналах не работают из-за ограничений Telegram API</i>\n\n"

        "<b>Шаг 3️⃣: Отправка новостей</b>\n\n"
        "Теперь вы можете отправлять новости:\n\n"
        "• Используйте команду <code>/latest</code> в личном чате с ботом\n"
        "• Или кнопку «📡 Отправить в чаты» в меню\n"
        "• Бот отправит самую свежую новость во все привязанные чаты\n\n"
        "Вы можете отправлять новости только в некоторые чаты:\n"
        "• Используйте команду <code>/broadcast</code> в личном чате с ботом\n\n"

        "<b>🔧 Дополнительно:</b>\n\n"
        "<code>/unbind</code> — отвязать чат от трансляции\n"
        "<code>/help</code> — справка по всем командам\n\n"
        "💡 <i>Нужна помощь? Используйте команду /help</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return
    text = (

        "        ℹ️ О БОТЕ              \n\n"

        "<b>📰 Новостной бот Lenta.ru</b>\n\n"
        "Автоматически собирает и пересказывает самые свежие новости с популярного новостного портала.\n\n"

        "<b>✨ Возможности:</b>\n\n"
        "• 📰 Получение самой свежей новости\n"
        "• 📡 Трансляция в каналы и группы\n"
        "• 🎨 Красивое оформление с изображениями\n"
        "• 📝 Краткий пересказ в удобном формате\n\n"

        "🔗 <b>Источник:</b> https://lenta.ru\n"
        "📚 <b>Инструкция:</b> /setup"
    )
    await message.reply_text(text, parse_mode="HTML")

async def bind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user
    
    if not message or not user:
        return

    # Получаем/создаем пользователя в БД
    user_id = db.get_or_create_user(user)

    # Получаем данные чата
    chat_title = chat.title or f"ID: {chat.id}"
    chat_type = chat.type

    # Сохраняем чат только для этого пользователя
    db.add_chat(user_id, chat.id, chat_title, chat_type)

    if chat.type == "private":
        from telegram import MessageOriginChannel
        if message and hasattr(message, 'forward_origin') and message.forward_origin and isinstance(message.forward_origin, MessageOriginChannel):
            channel_id = message.forward_origin.chat.id
            try:
                channel_chat = await context.bot.get_chat(channel_id)
            # try:
                # Проверяем, что бот - администратор канала
                bot_member = await context.bot.get_chat_member(channel_chat.id, context.bot.id)
                if bot_member.status not in ("administrator", "creator"):
                    text = (

                        "      ⚠️ БОТ НЕ АДМИНИСТРАТОР   \n\n"

                        "Бот должен быть администратором канала.\n\n"
                        "📚 <b>Инструкция:</b> /setup"
                    )
                    await message.reply_text(text, parse_mode="HTML")
                    return
                
                db.add_chat(channel_chat.id)
                text = (

                    "     ✅ КАНАЛ ПРИВЯЗАН          \n\n"

                    f"<b>📌 Канал:</b> {channel_chat.title or f'ID: {channel_chat.id}'}\n\n"
                    "Теперь вы можете отправлять новости в этот канал!\n\n"
                    "💡 <i>Используйте команду /latest для отправки новости</i>"
                )
                await message.reply_text(text, parse_mode="HTML")
                return
            except Exception as e:
                text = (

                    "      ❌ ОШИБКА ПРОВЕРКИ       \n\n"

                    f"Не удалось проверить права доступа.\n\n"
                    f"<i>Ошибка: {e}</i>\n\n"
                    "📚 <b>Инструкция:</b> /setup"
                )
                await message.reply_text(text, parse_mode="HTML")
                return
        
        # Если в личном чате без форварда - показываем инструкцию
        text = (

            "      📌 ПРИВЯЗКА ЧАТА         \n\n"

            "<b>Для групп:</b>\n"
            "  1. Откройте группу\n"
            "  2. Напишите команду: <code>/bind</code>\n"
            "  3. Бот подтвердит привязку \n\n"
            "<b>Для каналов:</b>\n"
            "1. Откройте ваш канал\n"
            "2. Перешлите любое сообщение из канала этому боту\n"
            "3. Бот автоматически привяжет канал\n\n"
            "⚠️ <i>Убедитесь, что бот добавлен как администратор канала!</i>\n\n"
            "📚 <b>Подробная инструкция:</b> /setup"
        )
        await message.reply_text(text, parse_mode="HTML")
        return

    # Для каналов проверяем, что бот - администратор
    # Для групп проверяем, что пользователь - администратор
    if chat.type == "channel":
        try:
            # Проверяем, что бот - администратор канала
            bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
            if bot_member.status not in ("administrator", "creator"):
                text = (

                    "      ⚠️ БОТ НЕ АДМИНИСТРАТОР   \n\n"

                    "Бот должен быть администратором канала.\n\n"
                    "📚 <b>Инструкция:</b> /setup"
                )
                await message.reply_text(text, parse_mode="HTML")
                return
        except Exception as e:
            text = (

                "      ❌ ОШИБКА ПРОВЕРКИ       \n\n"

                f"Не удалось проверить права доступа.\n\n"
                f"<i>Ошибка: {e}</i>"
            )
            await message.reply_text(text, parse_mode="HTML")
            return
    else:
        # Для групп проверяем права пользователя
        user = update.effective_user
        if not user:
            return
        try:
            member = await context.bot.get_chat_member(chat.id, user.id)
            if member.status not in ("administrator", "creator"):
                text = (

                    "      ⚠️ НЕДОСТАТОЧНО ПРАВ     \n\n"

                    "Только администратор группы может привязать чат.\n\n"
                    "📚 <b>Инструкция:</b> /setup"
                )
                await message.reply_text(text, parse_mode="HTML")
                return
        except Exception as e:
            text = (

                "      ❌ ОШИБКА ПРОВЕРКИ       \n\n"

                f"Не удалось проверить права доступа.\n\n"
                f"<i>Ошибка: {e}</i>"
            )
            await message.reply_text(text, parse_mode="HTML")
            return

    db.add_chat(chat.id)
    text = (

        "     ✅ ЧАТ ПРИВЯЗАН          \n\n"

        f"<b>📌 Чат:</b> {chat.title or f'ID: {chat.id}'}\n\n"
        "Теперь вы можете отправлять новости в этот чат!\n\n"
        "💡 <i>Используйте команду /latest в личном чате с ботом для отправки новости</i>\n\n"
        "📚 <b>Инструкция:</b> /setup"
    )
    await message.reply_text(text, parse_mode="HTML")

    user_id = db.get_or_create_user(user)
    db.add_chat(user_id, chat.id, chat.title or f"ID: {chat.id}", chat.type)

async def list_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список всех привязанных чатов с названиями"""
    user = update.effective_user
    message = update.effective_message
    
    if not message or not user:
        return

    chat = update.effective_chat  # добавляем, чтобы можно было проверить тип
    if chat.type != "private":
        text = (
            "      ⚠️ НЕВЕРНОЕ ИСПОЛЬЗОВАНИЕ \n\n"
            "Эта команда работает только в личном чате с ботом."
        )
        await message.reply_text(text, parse_mode="HTML")
        return

    # === Здесь заменяем load_bound_chat_ids() на БД ===
    import db  # убедись, что импортируешь модуль с БД
    user_id = db.get_or_create_user(user)
    user_chats = db.get_user_chats(user_id)

    if not user_chats:
        text = (
            "     ⚠️ НЕТ ПРИВЯЗАННЫХ ЧАТОВ \n\n"
            "У вас пока нет привязанных чатов.\n\n"
            "💡 <i>Используйте команду /bind для привязки чата</i>\n\n"
            "📚 <b>Инструкция:</b> /setup"
        )
        await message.reply_text(text, parse_mode="HTML")
        return

    await message.reply_text("🔄 Загружаю информацию о чатах...")

    chats_info = []
    errors = []

    for chat_id, title, chat_type in user_chats:  # получаем из БД
        try:
            chat_info = await context.bot.get_chat(chat_id)
            chat_type_emoji = "📢" if chat_type == "channel" else "👥" if chat_type == "group" else "💬"
            chat_type_name = "Канал" if chat_type == "channel" else "Группа" if chat_type == "group" else "Чат"
            chat_title = chat_info.title or title or f"ID: {chat_id}"  # если название есть в БД, используем его
            chats_info.append({
                'id': chat_id,
                'title': chat_title,
                'type': chat_type_name,
                'emoji': chat_type_emoji
            })
        except Exception as e:
            errors.append(chat_id)
            print(f"[DEBUG] Ошибка получения информации о чате {chat_id}: {e}")
            chats_info.append({
                'id': chat_id,
                'title': title or f"ID: {chat_id}",
                'type': chat_type,
                'emoji': "❓"
            })

    if not chats_info:
        text = (
            "      ❌ ОШИБКА ЗАГРУЗКИ       \n\n"
            "Не удалось загрузить информацию о чатах.\n"
            "Возможно, бот был удален из некоторых чатов."
        )
        await message.reply_text(text, parse_mode="HTML")
        return

    # Формируем текст со списком чатов
    text = "     📋 ПРИВЯЗАННЫЕ ЧАТЫ       \n\n"

    for i, chat_info in enumerate(chats_info, 1):
        text += f"{i}. {chat_info['emoji']} <b>{chat_info['title']}</b>\n"
        text += f"   📌 Тип: {chat_info['type']}\n"
        text += f"   🔢 ID: <code>{chat_info['id']}</code>\n\n"

    if errors:
        text += f"⚠️ <i>Не удалось загрузить {len(errors)} чат(ов)</i>\n\n"

    text += f"📊 <b>Всего привязано:</b> {len(chats_info)} чат(ов)"

    await message.reply_text(text, parse_mode="HTML")


async def unbind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user

    if not message or not user:
        return

    user_id = db.get_or_create_user(user)
    db.remove_chat(user_id, chat.id)
    
    delete_bound_chat_id(chat.id)
    text = (

        "     ❌ ЧАТ ОТВЯЗАН            \n\n"

        f"<b>📌 Чат:</b> {chat.title or f'ID: {chat.id}'}\n\n"
        "Чат больше не будет получать новости.\n\n"
        "💡 <i>Чтобы привязать снова, используйте команду /bind</i>"
    )
    await message.reply_text(text, parse_mode="HTML")

async def latest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет самую свежую новость во все привязанные чаты"""
    message = update.effective_message
    chat = update.effective_chat
    
    if not message:
        return
    
    if chat.type != "private":
        text = (

            "      ⚠️ НЕВЕРНОЕ ИСПОЛЬЗОВАНИЕ \n\n"

            "Эта команда работает только в личном чате с ботом."
        )
        await message.reply_text(text, parse_mode="HTML")
        return
    
    await message.reply_text("🔄 Загружаю самую свежую новость...")
    
    text_news, image_url = get_latest_news()
    if not text_news:
        text_error = (

            "      ❌ ОШИБКА ЗАГРУЗКИ       \n\n"

            "Не удалось загрузить новость.\nПопробуйте позже."
        )
        await message.reply_text(text_error, parse_mode="HTML")
        return
    
    # Показываем новость пользователю
    if image_url:
        caption = truncate_text(text_news, 1024)
        await message.reply_photo(photo=image_url, caption=caption, parse_mode="HTML")
    else:
        await message.reply_text(text_news, parse_mode="HTML", disable_web_page_preview=True)
    
    # Отправляем во все привязанные чаты
    user = update.effective_user
    user_id = db.get_or_create_user(user)
    user_chats = db.get_user_chats(user_id)
    chat_ids = [c[0] for c in user_chats]

    if not chat_ids:
        text_no_chats = (

            "     ⚠️ НЕТ ПРИВЯЗАННЫХ ЧАТОВ \n\n"

            "Сначала привяжите чаты для трансляции.\n\n"
            "📚 <b>Инструкция:</b> /setup"
        )
        await message.reply_text(text_no_chats, parse_mode="HTML")
        return
    
    sent_count = 0
    for chat_id in chat_ids:
        try:
            if image_url:
                caption = truncate_text(text_news, 1024)
                await context.bot.send_photo(chat_id=chat_id, photo=image_url, caption=caption, parse_mode="HTML")
            else:
                await context.bot.send_message(chat_id=chat_id, text=text_news, parse_mode="HTML", disable_web_page_preview=True)
            sent_count += 1
        except Exception as e:
            print(f"[DEBUG] Ошибка отправки в чат {chat_id}: {e}")
    
    text_success = (

        "     ✅ НОВОСТЬ ОТПРАВЛЕНА     \n\n"

        f"📊 <b>Отправлено в:</b> {sent_count} чат(ов)\n\n"
        f"📌 <b>Всего привязано:</b> {len(chat_ids)} чат(ов)"
    )
    await message.reply_text(text_success, parse_mode="HTML")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await select_channels(update, context)

# === Выбор чатов для трансляции ===
async def select_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = db.get_or_create_user(user)
    user_chats = db.get_user_chats(user_id)
    chats = [c[0] for c in user_chats]

    if not chats:
        text = (

            "     ⚠️ НЕТ ПРИВЯЗАННЫХ ЧАТОВ \n\n"

            "Сначала привяжите чаты для трансляции.\n\n"
            "📚 <b>Инструкция:</b> /setup"
        )
        await update.message.reply_text(text, parse_mode="HTML")
        return ConversationHandler.END

    await update.message.reply_text("🔄 Загружаю информацию о чатах...")
    
    # Получаем названия чатов
    chats_info = {}
    for chat_id in chats:
        try:
            chat_info = await context.bot.get_chat(chat_id)
            chat_type_emoji = "📢" if chat_info.type == "channel" else "👥" if chat_info.type == "group" else "💬"
            chat_title = chat_info.title or f"ID: {chat_id}"
            chats_info[chat_id] = {
                'title': chat_title,
                'emoji': chat_type_emoji
            }
        except Exception as e:
            print(f"[DEBUG] Ошибка получения информации о чате {chat_id}: {e}")
            chats_info[chat_id] = {
                'title': f"ID: {chat_id}",
                'emoji': "❓"
            }
    
    text = (

        "   📡 ВЫБОР ЧАТОВ ДЛЯ ТРАНСЛЯЦИИ               \n\n"

        "Выберите чаты, в которые хотите отправить новость:\n\n"
        "💡 <i>Нажмите на чат, чтобы выбрать/снять выбор</i>"
    )
    
    # Создаем кнопки с названиями
    keyboard = []
    for chat_id in chats:
        chat_info = chats_info.get(chat_id, {'title': f"ID: {chat_id}", 'emoji': '❓'})
        button_text = f"{chat_info['emoji']} {chat_info['title']}"
        # Ограничиваем длину текста кнопки (максимум 64 символа для Telegram)
        if len(button_text) > 60:
            button_text = button_text[:57] + "..."
        keyboard.append([InlineKeyboardButton(button_text, callback_data=str(chat_id))])
    
    keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="done")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    user_selected_chats[update.effective_user.id] = []
    # Сохраняем информацию о чатах для обновления клавиатуры
    if not hasattr(context, 'user_data'):
        context.user_data = {}
    context.user_data['chats_info'] = chats_info
    return SELECT_CHANNELS

async def handle_channel_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        print("[DEBUG] Нет callback_query в update")
        return ConversationHandler.END
    
    if not query.data:
        print(f"[DEBUG] Нет данных в callback_query: {query}")
        await query.answer("Ошибка: нет данных", show_alert=True)
        return ConversationHandler.END
    
    user_id = query.from_user.id
    print(f"[DEBUG] Обработка callback_query: data={query.data}, user_id={user_id}")
    
    # Отвечаем на callback сразу
    await query.answer()
    
    if query.data == "done":
        selected = user_selected_chats.get(user_id, [])
        print(f"[DEBUG] Нажата кнопка 'Готово', выбранные чаты для пользователя {user_id}: {selected}")

        # Сохраняем выбранные чаты в БД / файл
        for chat_id in selected:
            try:
                db.add_chat(chat_id)
                print(f"[DEBUG] Сохранён чат {chat_id} в привязанные чаты")
            except Exception as e:
                print(f"[DEBUG] Ошибка сохранения чата {chat_id}: {e}")

        if not selected:
            text = (

                "      ⚠️ НИЧЕГО НЕ ВЫБРАНО     \n\n"

                "Выберите хотя бы один чат для отправки новости."
            )
            await query.edit_message_text(text, parse_mode="HTML")
        else:
            text_status = (
                f"✅ <b>Выбраны чаты:</b> {', '.join(map(str, selected))}\n\n"
                f"🔄 Отправляю самую свежую новость..."
            )
            await query.edit_message_text(text_status, parse_mode="HTML")
            text_news, image_url = get_latest_news()
            if text_news:
                sent_count = 0
                for chat_id in selected:
                    try:
                        if image_url:
                            caption = truncate_text(text_news, 1024)
                            await context.bot.send_photo(chat_id=chat_id, photo=image_url, caption=caption, parse_mode="HTML")
                        else:
                            await context.bot.send_message(chat_id=chat_id, text=text_news, parse_mode="HTML", disable_web_page_preview=True)
                        sent_count += 1
                    except Exception as e:
                        print(f"[DEBUG] Ошибка отправки в чат {chat_id}: {e}")
                text_success = (

                    "      ✅ НОВОСТЬ ОТПРАВЛЕНА     \n\n"

                    f"📊 <b>Отправлено в:</b> {sent_count} чат(ов)\n\n"
                    f"📌 <b>Чаты:</b> {', '.join(map(str, selected))}"
                )
                await query.edit_message_text(text_success, parse_mode="HTML")
            else:
                text_error = (

                    "      ❌ ОШИБКА ЗАГРУЗКИ       \n\n"

                    "Не удалось загрузить новость.\nПопробуйте позже."
                )
                await query.edit_message_text(text_error, parse_mode="HTML")
        return ConversationHandler.END

    try:
        chat_id = int(query.data)
    except (ValueError, TypeError) as e:
        print(f"[DEBUG] Ошибка парсинга chat_id: {e}, data: {query.data}, type: {type(query.data)}")
        await query.answer("Ошибка: неверный формат данных", show_alert=True)
        return ConversationHandler.END
    
    selected = user_selected_chats.get(user_id, [])
    if not selected:
        selected = []
    if chat_id not in selected:
        selected.append(chat_id)
        print(f"[DEBUG] Добавлен чат {chat_id} в выбор пользователя {user_id}, текущий выбор: {selected}")
    else:
        selected.remove(chat_id)
        print(f"[DEBUG] Удален чат {chat_id} из выбора пользователя {user_id}, текущий выбор: {selected}")
    user_selected_chats[user_id] = selected
    
    # Обновляем клавиатуру с отметками выбранных чатов
    user = update.effective_user
    user_id = db.get_or_create_user(user)
    user_chats = db.get_user_chats(user_id)
    chats = user_selected_chats.get(user_id, [])
    chat_ids = [c[0] for c in user_chats]
    chats_info = context.user_data.get('chats_info', {})
    
    # Если информации о чатах нет, получаем её
    if not chats_info:
        for chat_id in chat:
            try:
                chat_info = await context.bot.get_chat(chat_id)
                chat_type_emoji = "📢" if chat_info.type == "channel" else "👥" if chat_info.type == "group" else "💬"
                chat_title = chat_info.title or f"ID: {chat_id}"
                chats_info[chat_id] = {
                    'title': chat_title,
                    'emoji': chat_type_emoji
                }
            except Exception as e:
                print(f"[DEBUG] Ошибка получения информации о чате {chat_id}: {e}")
                chats_info[chat_id] = {
                    'title': f"ID: {chat_id}",
                    'emoji': "❓"
                }
        context.user_data['chats_info'] = chats_info
    
    keyboard = []
    for cid in chats:
        marker = "✅ " if cid in selected else ""
        chat_info = chats_info.get(cid, {'title': f"ID: {cid}", 'emoji': '❓'})
        button_text = f"{marker}{chat_info['emoji']} {chat_info['title']}"
        # Ограничиваем длину текста кнопки (максимум 64 символа для Telegram)
        if len(button_text) > 60:
            button_text = button_text[:57] + "..."
        keyboard.append([InlineKeyboardButton(button_text, callback_data=str(cid))])
    keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="done")])
    
    try:
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        print(f"[DEBUG] Клавиатура успешно обновлена для пользователя {user_id}, выбранные чаты: {selected}")
    except Exception as e:
        print(f"[DEBUG] Ошибка обновления клавиатуры: {e}")
        import traceback
        traceback.print_exc()
        try:
            await query.answer(f"Ошибка обновления", show_alert=True)
        except:
            pass
        return SELECT_CHANNELS
    
    return SELECT_CHANNELS

# === Отправка новостей ===
async def send_news_to_all_channels(application, news_items, selected_ids=None):
    if selected_ids:
        chat_ids = selected_ids
    else:
        # получаем чаты текущего пользователя
        # нужно передать user_id в функцию, если она вызывается из контекста update
        user_id = application.user_id  # если user_id нет, передавать его параметром
        user_chats = db.get_user_chats(user_id)
        chat_ids = [c[0] for c in user_chats]
        if not chat_ids:
            return False

    for chat_id in chat_ids:
        for article_text, image_url in news_items:
            try:
                if image_url:
                    caption = truncate_text(article_text, 1024)
                    await application.bot.send_photo(chat_id=chat_id, photo=image_url, caption=caption, parse_mode="HTML")
                else:
                    await application.bot.send_message(chat_id=chat_id, text=article_text, parse_mode="HTML", disable_web_page_preview=True)
            except Exception as e:
                print(f"[DEBUG] Ошибка отправки в чат {chat_id}: {e}")
    return True

# === Обработка сообщений ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    
    # Обрабатываем форварды из каналов (для привязки каналов)
    if chat.type == "private" and message and hasattr(message, 'forward_origin') and message.forward_origin:
        from telegram import MessageOriginChannel
        if isinstance(message.forward_origin, MessageOriginChannel):
            await bind_command(update, context)
            return
    
    if not message or not message.text:
        return
    
    text = message.text.strip()

    if text == "📰 Получить новости":
        await message.reply_text("🔄 Загружаю самую свежую новость...")
        text_news, image_url = get_latest_news()
        if not text_news:
            await message.reply_text("❌ Не удалось загрузить новость. Попробуйте позже.")
            return
        if image_url:
            caption = truncate_text(text_news, 1024)
            await message.reply_photo(photo=image_url, caption=caption, parse_mode="HTML")
        else:
            await message.reply_text(text_news, parse_mode="HTML", disable_web_page_preview=True)

    elif text == "📡 Отправить в чаты":
        await latest_command(update, context)
    
    elif text == "📢 Выбрать чаты":
        await broadcast_command(update, context)

    elif text == "🔗 Привязать чат":
        await bind_command(update, context)

    elif text == "❌ Отвязать чат":
        if chat.type == "private":
            text_unbind = (

                "      📌 ОТВЯЗКА ЧАТА          \n\n"

                "<b>Для групп:</b> Используйте команду /unbind в группе\n\n"
                "<b>Для каналов:</b> Используйте команду /unbind, указав ID канала\n\n"
                "📚 <b>Инструкция:</b> /setup"
            )
            await message.reply_text(text_unbind, parse_mode="HTML")
        else:
            await unbind_command(update, context)

    elif text == "📋 Список чатов":
        await list_chats_command(update, context)

    elif text == "⚙️ Инструкция":
        await setup_command(update, context)

    elif text == "ℹ️ О боте":
        await about_command(update, context)

    elif text == "❓ Помощь":
        await help_command(update, context)

    else:
        await message.reply_text("❗ Неизвестная команда. Используйте /help.")

# === Main ===
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("broadcast", broadcast_command),
            MessageHandler(filters.Regex("^📢 Выбрать чаты$"), broadcast_command)
        ],
        states={SELECT_CHANNELS: [CallbackQueryHandler(handle_channel_selection)]},
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("setup", setup_command))
    app.add_handler(CommandHandler("about", about_command))
    # Обрабатываем команды в сообщениях и постах каналов
    app.add_handler(CommandHandler("bind", bind_command, filters=filters.UpdateType.MESSAGES))
    app.add_handler(CommandHandler("unbind", unbind_command, filters=filters.UpdateType.MESSAGES))
    app.add_handler(CommandHandler("list", list_chats_command))
    app.add_handler(CommandHandler("latest", latest_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Бот запущен...")
    app.run_polling()

if __name__ == '__main__':
    main()
