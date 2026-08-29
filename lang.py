import json
from pathlib import Path
from utils.paths import RESOURCES
from logger import logger


class LanguageManager:
    def __init__(self, language_code="en_US"):
        self.language_code = language_code
        self.translations = {}
        self._load_language(language_code)

    def _load_language(self, language_code):
        """内部加载方法，始终记录日志"""
        # 防御 None 或空字符串
        if not language_code:
            language_code = "en_US"
            logger.warning("Invalid language code, falling back to en_US")

        lang_dir = RESOURCES / "language"
        lang_file = lang_dir / f"{language_code}.json"

        # 始终记录加载尝试
        logger.info(f"Loading language: {language_code} from {lang_file}")
        logger.info(f"Language file exists: {lang_file.exists()}")

        if not lang_file.exists():
            fallback = lang_dir / "en_US.json"
            if fallback.exists():
                lang_file = fallback
                logger.warning("Language file for %s not found, falling back to en_US.json", language_code)
            else:
                logger.error("Neither %s nor en_US.json language files were found in %s", language_code, lang_dir)
                self.translations = {}
                self.language_code = "en_US"
                return

        try:
            with open(lang_file, "r", encoding="utf-8") as f:
                self.translations = json.load(f)
            self.language_code = language_code
            logger.info(f"Successfully loaded {len(self.translations)} translations for {language_code}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in {lang_file}: {e}")
            self.translations = {}
            self.language_code = "en_US"
        except Exception as exc:
            logger.exception("Failed to load language file %s: %s", lang_file, exc)
            self.translations = {}
            self.language_code = "en_US"

    def load_language(self, language_code):
        """公开加载方法，直接调用内部方法"""
        self._load_language(language_code)

    def get(self, key, default=None):
        """Return translation for key, or key itself if missing."""
        return self.translations.get(key, default or key)

    def tr(self, key, default=None):
        """Alias for get()."""
        return self.get(key, default)


# Global instance – will be initialised in app.py
lang = LanguageManager("en_US")