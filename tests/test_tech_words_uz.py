"""Uzbek reading of technical tokens (services/tech_words_uz.py).

A file name, a folder path, a web or IP address, a version string or a unit
used to reach the engine as written and was chewed. Each must leave the
normalizer as speakable words, with ordinary prose left alone.
"""
import re

import pytest

from services.text_normalization import normalize_text

_SPOKEN_CASES = [
    # File names: "_" and "-" are silent, the dot is spoken, an extension
    # without a vowel is spelled.
    ("index.html", "index nuqta ha te em el"),
    ("server.py va report.json", "server nuqta pay va report nuqta jeyson"),
    ("make_kids.py fayli", "make kids nuqta pay fayli"),
    ("ISSAI_USC.tar.gz arxivi", "ISSAI USC nuqta tar nuqta ge zet arxivi"),
    ("qo'shiq.mp3", "qo'shiq nuqta em pe uch"),
    # Windows paths: every folder is its own phrase; a file name with a space
    # is finished by the file-name rule.
    (r"D:\sado-ovoz-ustaxonasi\Ovoz ustaxonasi.bat faylini bosing",
     "de disk, sado ovoz ustaxonasi, Ovoz ustaxonasi nuqta bat faylini bosing"),
    (r"C:\Users\AIBA\scripts\voice_casting.py ichida",
     "se disk, Users, AIBA, scripts, voice casting nuqta pay ichida"),
    ("scripts/voice_casting.py", "scripts, voice casting nuqta pay"),
    ("/home/user/a.txt", "home, user, a nuqta te iks te"),
    # Addresses.
    ("127.0.0.1:3955 da ishlaydi",
     "yuz yigirma yetti nuqta nol nuqta nol nuqta bir, port uch ming to'qqiz yuz ellik besh da ishlaydi"),
    ("(127.0.0.1:3955)",
     "(yuz yigirma yetti nuqta nol nuqta nol nuqta bir, port uch ming to'qqiz yuz ellik besh)"),
    ("http://127.0.0.1:3955/index.html.",
     "yuz yigirma yetti nuqta nol nuqta nol nuqta bir, port uch ming to'qqiz yuz ellik besh slesh index nuqta "
     "ha te em el."),
    ("https://sado.uz/yuklab-olish", "sado nuqta uz slesh yuklab olish"),
    ("www.sado.uz saytida", "sado nuqta uz saytida"),
    ("sado.uz, t.me/sado_kanal", "sado nuqta uz, te nuqta me slesh sado kanal"),
    ("localhost:3900", "localhost, port uch ming to'qqiz yuz"),
    ("info@sado.uz", "info kuchukcha sado nuqta uz"),
    # Versions.
    ("Sado v0.5.8 chiqdi", "Sado versiya nol nuqta besh nuqta sakkiz chiqdi"),
    ("Python 3.11.17", "Python uch nuqta o'n bir nuqta o'n yetti"),
    # Units keep their number for the number rules.
    ("9,5 GB, 2,3 MB/s", "to'qqiz butun o'ndan besh gigabayt, ikki butun o'ndan uch megabayt sekundiga"),
    ("16 kHz va 24000 Hz", "o'n olti kilogers va yigirma to'rt ming gers"),
    ("90 km/soat", "to'qson kilometr soatiga"),
    ("Ekran 1920x1080, 60 fps", "Ekran bir ming to'qqiz yuz yigirma ga bir ming sakson, oltmish kadr sekundiga"),
    # Bracket grammar is masked, the rest is still read.
    ("[pause 300ms] server.py [voice:Ali]", "[pause 300ms] server nuqta pay [voice:Ali]"),
]


@pytest.mark.parametrize("raw,spoken", _SPOKEN_CASES)
def test_technical_token_is_spoken(raw, spoken):
    out = normalize_text(raw, "Uzbek")
    assert out == spoken
    assert not re.search(r"\d", re.sub(r"\[[^\]]*\]", "", out)), "a digit reached the engine"
    assert normalize_text(out, "Uzbek") == out, "a second pass must change nothing"


_PROSE = [
    "U keldi.Men ketdim.",                    # a missing space is not a file name
    "A.Navoiy ko'chasi",                      # an initial
    "10.000 so'm",                            # thousands grouped by a dot
    "va/yoki, h/r",                           # a slash between two words
    "Bu juda yaxshi kun bo'ldi, rahmat!",
]


@pytest.mark.parametrize("raw", _PROSE)
def test_prose_is_left_alone(raw):
    assert normalize_text(raw, "Uzbek") == raw


def test_dates_amounts_and_clock_keep_their_own_rules():
    """A dotted date or amount is not a version, and a clock time is not a port."""
    assert normalize_text("05.09.2025", "Uzbek") == "beshinchi sentabr ikki ming yigirma beshinchi yil"
    assert normalize_text("1.500.000 so'm", "Uzbek") == "1.500.000 so'm"
    assert normalize_text("soat 12:30", "Uzbek") == "soat o'n ikki o'ttiz"
    assert normalize_text("3.5 km", "Uzbek") == "uch butun o'ndan besh kilometr"


def test_path_does_not_drag_numbers_into_english():
    """A path is full of English-looking words; the number beside it stays Uzbek."""
    out = normalize_text(r"C:\Users\Desktop\the\new\file.txt ichida 42 qator bor", "Uzbek")
    assert out.endswith("ichida qirq ikki qator bor")
    assert "forty" not in out


def test_other_languages_are_untouched():
    for language in ("English", "Russian", None):
        assert "nuqta" not in normalize_text("server.py at 127.0.0.1:3955", language)


def test_cyrillic_uzbek_reads_tokens_and_survives_a_second_pass():
    out = normalize_text("Файл server.py, манзил 127.0.0.1", "uzc")
    assert out == "Файл сервер нуқта пай, манзил юз йигирма етти нуқта нол нуқта нол нуқта бир"
    assert normalize_text(out, "uzc") == out


def test_cyrillic_round_trip_keeps_word_initial_ye():
    from services.number_words_uz import to_cyrillic, to_latin

    assert to_latin("етти") == "yetti"
    assert to_cyrillic(to_latin("юз йигирма етти")) == "юз йигирма етти"
    assert to_latin("кейин") == "keyin"
