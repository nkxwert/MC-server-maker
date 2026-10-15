"""Translations. Source strings are English; Korean lives in i18n_ko.py.

    t("Server created")            -> current language
    t("Java {v} required", v=21)   -> with formatting
"""

LANGUAGES = {"en": "English", "ko": "한국어"}
_lang = "en"


def set_language(lang: str) -> None:
    global _lang
    _lang = lang if lang in LANGUAGES else "en"


def language() -> str:
    return _lang


def t(text: str, **kwargs) -> str:
    if _lang == "ko":
        from mc_server_maker.i18n_ko import KO

        text = KO.get(text, text)
    return text.format(**kwargs) if kwargs else text
