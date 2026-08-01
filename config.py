import os
from dotenv import load_dotenv
from pathlib import Path

# Загружаем переменные окружения
load_dotenv()

class Config:
    """Конфигурация бота"""
    
    # Основные настройки
    BOT_TOKEN: str = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не найден в .env файле!")
    
    # База данных
    DB_PATH: str = os.getenv('DB_PATH', 'bot_database.db')
    
    # Логирование
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE: str = os.getenv('LOG_FILE', 'bot.log')
    
    # Режим разработки
    DEBUG: bool = os.getenv('DEBUG', 'False').lower() == 'true'
    
    # Настройки по умолчанию для пользователей
    DEFAULT_NOTIFY_DELETED: int = int(os.getenv('DEFAULT_NOTIFY_DELETED', 1))
    DEFAULT_NOTIFY_EDITED: int = int(os.getenv('DEFAULT_NOTIFY_EDITED', 1))
    DEFAULT_SAVE_MEDIA: int = int(os.getenv('DEFAULT_SAVE_MEDIA', 1))
    DEFAULT_AUTO_FORWARD: int = int(os.getenv('DEFAULT_AUTO_FORWARD', 0))
    
    # Лимиты
    MAX_HISTORY_MESSAGES: int = int(os.getenv('MAX_HISTORY_MESSAGES', 1000))
    MAX_TEXT_LENGTH: int = int(os.getenv('MAX_TEXT_LENGTH', 4096))
    
    # Информация о боте
    BOT_NAME: str = os.getenv('BOT_NAME', 'BusinessTrackerBot')
    BOT_DESCRIPTION: str = os.getenv('BOT_DESCRIPTION', 'Сохраняет удаленные и измененные сообщения через Business API')
    
    @classmethod
    def get_database_url(cls) -> str:
        """Получить URL базы данных"""
        return f"sqlite:///{cls.DB_PATH}"
    
    @classmethod
    def is_debug(cls) -> bool:
        """Проверка режима отладки"""
        return cls.DEBUG
    
    @classmethod
    def get_logging_config(cls) -> dict:
        """Получить конфигурацию логирования"""
        return {
            'level': cls.LOG_LEVEL,
            'file': cls.LOG_FILE,
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        }

# Создаем объект конфигурации для удобства импорта
config = Config()