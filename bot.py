import asyncio
import logging
import sys
import json
from datetime import datetime
from typing import Optional

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    BusinessConnection, 
    BusinessMessagesDeleted,
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    Message,
    CallbackQuery
)
from aiogram.filters import Command
from aiogram.exceptions import TelegramRetryAfter, TelegramAPIError
from aiogram.client.default import DefaultBotProperties

from config import config
from database import db

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format=config.get_logging_config()['format'],
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Инициализация бота с новыми параметрами
bot = Bot(
    token=config.BOT_TOKEN,
    default=DefaultBotProperties(
        parse_mode='HTML',
        link_preview_is_disabled=False
    )
)
dp = Dispatcher()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def get_media_data(message: Message) -> tuple[Optional[str], Optional[str]]:
    """Извлекает информацию о медиа из сообщения"""
    media_type = None
    media_data = None
    
    if not message.media:
        return media_type, media_data
    
    try:
        if message.photo:
            media_type = 'photo'
            media_data = json.dumps({
                'file_id': message.photo[-1].file_id,
                'width': message.photo[-1].width,
                'height': message.photo[-1].height
            })
        elif message.document:
            media_type = 'document'
            media_data = json.dumps({
                'file_name': message.document.file_name,
                'size': message.document.file_size,
                'mime_type': message.document.mime_type
            })
        elif message.video:
            media_type = 'video'
            media_data = json.dumps({
                'duration': message.video.duration,
                'width': message.video.width,
                'height': message.video.height
            })
        elif message.audio:
            media_type = 'audio'
            media_data = json.dumps({
                'duration': message.audio.duration,
                'title': message.audio.title,
                'performer': message.audio.performer
            })
        elif message.voice:
            media_type = 'voice'
            media_data = json.dumps({
                'duration': message.voice.duration
            })
        elif message.sticker:
            media_type = 'sticker'
            media_data = json.dumps({
                'emoji': message.sticker.emoji,
                'file_id': message.sticker.file_id
            })
        elif message.video_note:
            media_type = 'video_note'
            media_data = json.dumps({
                'duration': message.video_note.duration,
                'length': message.video_note.length
            })
        elif message.animation:
            media_type = 'animation'
            media_data = json.dumps({
                'duration': message.animation.duration,
                'width': message.animation.width,
                'height': message.animation.height
            })
    except Exception as e:
        logger.error(f"Ошибка обработки медиа: {e}")
    
    return media_type, media_data

async def safe_send_message(chat_id: int, text: str, **kwargs):
    """Безопасная отправка сообщения с обработкой ошибок"""
    try:
        return await bot.send_message(chat_id, text, **kwargs)
    except TelegramRetryAfter as e:
        logger.warning(f"Flood wait: {e.retry_after} seconds")
        await asyncio.sleep(e.retry_after)
        return await bot.send_message(chat_id, text, **kwargs)
    except TelegramAPIError as e:
        logger.error(f"Ошибка отправки сообщения: {e}")
        return None

# ==================== ОБРАБОТЧИКИ BUSINESS API ====================

@dp.business_connection()
async def handle_business_connection(connection: BusinessConnection):
    """Обработка подключения бизнес-аккаунта"""
    try:
        user_id = connection.user.id
        
        logger.info(f"Business подключение от {user_id}")
        
        # Регистрируем пользователя
        await db.register_user(
            user_id,
            connection.user.username,
            connection.user.first_name,
            connection.user.last_name,
            is_premium=True,
            language_code=getattr(connection.user, 'language_code', 'ru')
        )
        
        # Сохраняем подключение
        await db.save_connection(
            connection.connection_id,
            user_id,
            f"{connection.user.first_name or ''} {connection.user.last_name or ''}".strip(),
            connection.can_reply
        )
        
        # Проверяем настройки
        settings = await db.get_user_settings(user_id)
        
        # Приветственное сообщение
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
        ])
        
        await safe_send_message(
            user_id,
            f"🤖 <b>Бот подключен к вашему бизнес-аккаунту!</b>\n\n"
            f"✅ Я буду сохранять все сообщения из ваших чатов\n"
            f"✏️ Отслеживать изменения\n"
            f"🗑️ Сохранять удаленные сообщения\n\n"
            f"📌 <b>Текущие настройки:</b>\n"
            f"• Уведомления об удалении: {'✅' if settings and settings[0] else '❌'}\n"
            f"• Уведомления об изменениях: {'✅' if settings and settings[1] else '❌'}\n"
            f"• Сохранение медиа: {'✅' if settings and settings[2] else '❌'}\n\n"
            f"Используйте команды для управления:",
            reply_markup=kb
        )
        
    except Exception as e:
        logger.error(f"Ошибка в handle_business_connection: {e}")

@dp.business_message()
async def handle_business_message(message: Message):
    """Обработка новых сообщений"""
    try:
        user_id = message.from_user.id if message.from_user else None
        if not user_id:
            return
        
        # Проверяем, активен ли пользователь
        user = await db.get_user(user_id)
        if not user or user[5] == 0:  # is_active
            return
        
        # Получаем информацию о сообщении
        media_type, media_data = get_media_data(message)
        
        message_data = {
            'message_id': message.message_id,
            'chat_id': message.chat.id,
            'chat_title': message.chat.title or f"Chat {message.chat.id}",
            'chat_type': message.chat.type,
            'sender_id': message.from_user.id if message.from_user else None,
            'sender_name': f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip() if message.from_user else '',
            'text': message.text or message.caption or '',
            'media_type': media_type,
            'media_data': media_data,
            'date': int(message.date.timestamp())
        }
        
        connection_id = getattr(message, 'business_connection_id', None)
        
        # Сохраняем сообщение
        await db.save_message(user_id, message_data, connection_id)
        
        logger.info(f"Сохранено сообщение {message.message_id} от {user_id}")
        
    except Exception as e:
        logger.error(f"Ошибка в handle_business_message: {e}")

@dp.edited_business_message()
async def handle_edited_business_message(message: Message):
    """Обработка измененных сообщений"""
    try:
        user_id = message.from_user.id if message.from_user else None
        if not user_id:
            return
        
        # Проверяем настройки
        settings = await db.get_user_settings(user_id)
        if not settings or settings[1] == 0:  # notify_edited
            return
        
        # Получаем старое сообщение
        old_data = await db.get_message(user_id, message.message_id, message.chat.id)
        
        if old_data:
            old_text = old_data[0] or ''
            sender_name = old_data[1] or 'Неизвестно'
            chat_title = old_data[2] or f"Chat {message.chat.id}"
            
            # Сохраняем изменение
            new_text = message.text or message.caption or ''
            await db.save_edit(user_id, message.message_id, message.chat.id, old_text, new_text)
            
            # Отправляем уведомление
            text = f"✏️ <b>Сообщение изменено</b>\n"
            text += f"Чат: {chat_title}\n"
            text += f"От: {sender_name}\n"
            text += f"Было: {old_text[:200]}{'...' if len(old_text) > 200 else ''}\n"
            text += f"Стало: {new_text[:200]}{'...' if len(new_text) > 200 else ''}\n"
            text += f"ID: {message.message_id}"
            
            await safe_send_message(user_id, text)
            
    except Exception as e:
        logger.error(f"Ошибка в handle_edited_business_message: {e}")

@dp.business_messages_deleted()
async def handle_business_messages_deleted(deleted: BusinessMessagesDeleted):
    """Обработка удаленных сообщений"""
    try:
        # Определяем пользователя
        user_id = deleted.chat.id
        
        # Проверяем настройки
        settings = await db.get_user_settings(user_id)
        if not settings or settings[0] == 0:  # notify_deleted
            return
        
        for msg_id in deleted.message_ids:
            # Получаем информацию о сообщении
            old_data = await db.get_message(user_id, msg_id, deleted.chat.id)
            
            if old_data and old_data[0]:
                await db.mark_deleted(user_id, msg_id, deleted.chat.id)
                
                text = f"🗑️ <b>Сообщение удалено</b>\n"
                text += f"Чат: {old_data[2] or deleted.chat.title or deleted.chat.id}\n"
                text += f"От: {old_data[1] or 'Неизвестно'}\n"
                text += f"Текст: {old_data[0][:300]}{'...' if len(old_data[0]) > 300 else ''}\n"
                text += f"ID: {msg_id}"
                
                await safe_send_message(user_id, text)
                
    except Exception as e:
        logger.error(f"Ошибка в handle_business_messages_deleted: {e}")

# ==================== КОМАНДЫ ПОЛЬЗОВАТЕЛЕЙ ====================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Команда /start"""
    user_id = message.from_user.id
    
    # Регистрируем пользователя
    await db.register_user(
        user_id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton(text="❓ Как подключить", callback_data="how_to_connect")]
    ])
    
    await safe_send_message(
        user_id,
        "🤖 <b>Business Bot</b>\n\n"
        "Бот сохраняет все сообщения в ваших чатах!\n\n"
        "📌 <b>Что умеет:</b>\n"
        "✅ Сохранять все сообщения (текст, фото, видео, документы)\n"
        "✏️ Отслеживать изменения сообщений\n"
        "🗑️ Сохранять удаленные сообщения\n"
        "📱 Работает через Business API (официально!)\n\n"
        "🔥 <b>Требуется Telegram Premium</b>\n\n"
        "Чтобы подключить бота, перейдите в:\n"
        "Настройки → Telegram Business → Боты",
        reply_markup=kb
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Команда /help"""
    await safe_send_message(
        message.from_user.id,
        "❓ <b>Помощь по Business Bot</b>\n\n"
        "📌 <b>Основные команды:</b>\n"
        "/start - главное меню\n"
        "/stats - статистика\n"
        "/settings - настройки\n"
        "/history <id> - история сообщения\n"
        "/help - помощь\n\n"
        "🔌 <b>Как подключить:</b>\n"
        "1. Купите Telegram Premium\n"
        "2. Перейдите в Настройки → Telegram Business\n"
        "3. В разделе \"Боты\" добавьте этого бота\n"
        "4. Дайте доступ к чатам\n\n"
        "📱 <b>Где посмотреть сохраненные сообщения?</b>\n"
        "Все сообщения хранятся локально на сервере.\n"
        "Используйте /history <id> для просмотра истории."
    )

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    """Команда /stats"""
    user_id = message.from_user.id
    
    stats = await db.get_stats(user_id)
    active_connections = await db.get_active_connections_count(user_id)
    
    if not stats:
        await safe_send_message(user_id, "📊 Статистика пока пуста")
        return
    
    text = f"📊 <b>Ваша статистика:</b>\n\n"
    text += f"📩 Всего сообщений: {stats[0]}\n"
    text += f"🗑️ Удалено: {stats[1]}\n"
    text += f"✏️ Изменений: {stats[2]}\n"
    text += f"📎 Медиа: {stats[3]}\n"
    text += f"🔗 Активных чатов: {active_connections}\n"
    
    if stats[4]:
        last_update = datetime.fromtimestamp(stats[4]).strftime('%Y-%m-%d %H:%M')
        text += f"📅 Последнее обновление: {last_update}"
    
    await safe_send_message(user_id, text)

@dp.message(Command("settings"))
async def cmd_settings(message: Message):
    """Команда /settings"""
    user_id = message.from_user.id
    settings = await db.get_user_settings(user_id)
    
    if not settings:
        settings = (1, 1, 1, 0, None)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"{'✅' if settings[0] else '❌'} Уведомления об удалении",
                callback_data="toggle_deleted"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{'✅' if settings[1] else '❌'} Уведомления об изменениях",
                callback_data="toggle_edited"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{'✅' if settings[2] else '❌'} Сохранять медиа",
                callback_data="toggle_media"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{'✅' if settings[3] else '❌'} Авто-пересылка",
                callback_data="toggle_forward"
            )
        ]
    ])
    
    await safe_send_message(
        user_id,
        "⚙️ <b>Настройки</b>\n\n"
        "Настройте уведомления под себя:",
        reply_markup=kb
    )

@dp.message(Command("history"))
async def cmd_history(message: Message):
    """Команда /history <id>"""
    user_id = message.from_user.id
    
    args = message.text.split()
    if len(args) < 2:
        await safe_send_message(user_id, "Использование: /history <id_сообщения>")
        return
    
    try:
        msg_id = int(args[1])
        
        # Получаем сообщение
        msg = await db.get_message(user_id, msg_id, message.chat.id)
        if not msg:
            await safe_send_message(user_id, f"❌ Сообщение {msg_id} не найдено")
            return
        
        # Получаем изменения
        edits = await db.get_message_edits(user_id, msg_id, message.chat.id)
        
        text = f"📜 <b>История сообщения</b>\n"
        text += f"ID: {msg_id}\n"
        text += f"Чат: {msg[2] or 'Неизвестно'}\n"
        text += f"От: {msg[1] or 'Неизвестно'}\n"
        text += f"Текст: {msg[0] or 'Нет текста'}\n"
        text += f"Дата: {datetime.fromtimestamp(msg[3]).strftime('%Y-%m-%d %H:%M:%S') if msg[3] else 'Неизвестно'}\n"
        
        if msg[6] == 1:
            text += f"❌ Удалено: {datetime.fromtimestamp(msg[5]).strftime('%Y-%m-%d %H:%M:%S') if msg[5] else 'Неизвестно'}\n"
        
        if edits:
            text += f"\n📝 <b>Изменения ({len(edits)}):</b>\n"
            for i, (old_t, new_t, edit_d) in enumerate(edits[:5], 1):
                text += f"{i}. {datetime.fromtimestamp(edit_d).strftime('%Y-%m-%d %H:%M:%S')}\n"
                text += f"   Было: {old_t[:50]}{'...' if len(old_t) > 50 else ''}\n"
                text += f"   Стало: {new_t[:50]}{'...' if len(new_t) > 50 else ''}\n\n"
        
        if len(text) > config.MAX_TEXT_LENGTH:
            text = text[:config.MAX_TEXT_LENGTH] + "\n\n... (обрезано)"
        
        await safe_send_message(user_id, text)
        
    except ValueError:
        await safe_send_message(user_id, "❌ ID должен быть числом")
    except Exception as e:
        await safe_send_message(user_id, f"❌ Ошибка: {e}")

# ==================== CALLBACK HANDLERS ====================

@dp.callback_query()
async def handle_callbacks(callback: CallbackQuery):
    """Обработка callback-запросов"""
    user_id = callback.from_user.id
    
    if callback.data == "stats":
        await cmd_stats(callback.message)
        await callback.answer()
    
    elif callback.data == "settings":
        await cmd_settings(callback.message)
        await callback.answer()
    
    elif callback.data == "how_to_connect":
        await safe_send_message(
            user_id,
            "🔌 <b>Как подключить бота:</b>\n\n"
            "1️⃣ <b>Купите Telegram Premium</b>\n"
            "   (Business API доступен только для Premium)\n\n"
            "2️⃣ <b>Откройте настройки Telegram</b>\n"
            "   Настройки → Telegram Business\n\n"
            "3️⃣ <b>Добавьте бота</b>\n"
            "   В разделе \"Боты\" нажмите \"Добавить бота\"\n"
            "   Введите имя бота: @ваш_бот\n\n"
            "4️⃣ <b>Дайте доступ</b>\n"
            "   Разрешите боту доступ к чатам\n\n"
            "5️⃣ <b>Готово!</b> 🎉\n"
            "   Бот начнет сохранять все сообщения"
        )
        await callback.answer()
    
    elif callback.data.startswith("toggle_"):
        setting = callback.data.replace("toggle_", "")
        
        settings = await db.get_user_settings(user_id)
        if not settings:
            settings = [1, 1, 1, 0]
        
        setting_map = {
            "deleted": (0, "notify_deleted"),
            "edited": (1, "notify_edited"),
            "media": (2, "save_media"),
            "forward": (3, "auto_forward")
        }
        
        if setting in setting_map:
            index, db_field = setting_map[setting]
            new_value = 0 if settings[index] == 1 else 1
            
            await db.update_user_settings(user_id, **{db_field: new_value})
            
            await callback.answer("✅ Настройка обновлена!")
            await cmd_settings(callback.message)
        
        await callback.answer()
    
    elif callback.data == "help":
        await cmd_help(callback.message)
        await callback.answer()

# ==================== ЗАПУСК ====================

async def main():
    """Запуск бота"""
    logger.info("🚀 Запуск Business Bot...")
    
    # Инициализация БД
    await db.init_database()
    
    bot_info = await bot.get_me()
    logger.info(f"Бот: @{bot_info.username}")
    logger.info("")
    logger.info("📌 Инструкция для пользователей:")
    logger.info("1. Купить Telegram Premium")
    logger.info("2. Настройки → Telegram Business → Добавить бота")
    logger.info("3. Ввести имя бота")
    logger.info("")
    logger.info("Бот запущен и ждет подключений!")
    
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    except Exception as e:
        logger.error(f"Ошибка при работе бота: {e}")
        raise

if __name__ == '__main__':
    asyncio.run(main())