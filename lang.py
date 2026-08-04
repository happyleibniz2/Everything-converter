import json
from pathlib import Path
from utils.paths import RESOURCES
from logger import logger

class LanguageManager:
    def __init__(self, language_code="en_US"):
        self.language_code = language_code
        self.translations = {}
        self.load_language(language_code)

    def load_language(self, language_code):
        lang_dir = RESOURCES / "language"
        lang_file = lang_dir / f"{language_code}.json"
        # Prefer requested language, but fall back to en_US.json if missing.
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
        except Exception as exc:
            logger.exception("Failed to load language file %s: %s", lang_file, exc)
            self.translations = {}
            self.language_code = "en_US"

    def get(self, key, default=None):
        """Return translation for key, or key itself if missing."""
        return self.translations.get(key, default or key)

    def tr(self, key, default=None):
        """Alias for get()."""
        return self.get(key, default)

# Global instance – will be initialised in app.py
lang = LanguageManager("en_US")