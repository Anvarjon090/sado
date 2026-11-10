"""Numbers are read in the language of their own clause, and Uzbek/Russian
number forms beyond plain integers are verbalized.

Regression for the owner report (2026-11-09): in an Uzbek request, numbers
inside English or Russian sentences were read in Uzbek.
"""

import pytest
from services.number_language import split_by_number_language, word_votes
from services.text_normalization import normalize_text

_MIXED = [
    # (request language, input, expected)
    ("Uzbek", "Men 5 ta olma oldim. I have 5 apples and 20 pears.",
     "Men beshta olma oldim. I have five apples and twenty pears."),
    ("Uzbek", "Narxi 100 so'm. Это стоит 250 рублей.",
     "Narxi yuz so'm. Это стоит двести пятьдесят рублей."),
    ("Uzbek", "Это стоит 15%. Narx 15% oshdi.",
     "Это стоит пятнадцать процентов. Narx o'n besh foiz oshdi."),
    ("Uzbek", "I was born in 1995.", "I was born in nineteen ninety-five."),
    ("Uzbek", "Bugun 5-та китоб, 2025-йилда.",
     "Bugun бешта китоб, икки минг йигирма бешинчи йилда."),
    ("English", "Hello, I have 3 cats. Mening 3 ta mushugim bor.",
     "Hello, I have three cats. Mening uchta mushugim bor."),
    ("Russian", "Встреча в 14:30. Men 5 ta olma oldim.",
     "Встреча в четырнадцать тридцать. Men beshta olma oldim."),
    # Neutral words (names, brands) never outvote the request language.
    ("Uzbek", "iPhone 15 sotib oldim", "iPhone o'n besh sotib oldim"),
]


@pytest.mark.parametrize("language,text,expected", _MIXED)
def test_numbers_follow_their_clause_language(language, text, expected):
    assert normalize_text(text, language) == expected


_UZBEK_FORMS = [
    ("Telefon: +998 90 123 45 67",
     "Telefon: plyus to'qqiz yuz to'qson sakkiz, to'qson, bir yuz yigirma uch, qirq besh, oltmish yetti"),
    ("90 123 45 67 ga yozing", "to'qson, bir yuz yigirma uch, qirq besh, oltmish yetti ga yozing"),
    ("Sana 09.11.2026", "Sana to'qqizinchi noyabr ikki ming yigirma oltinchi yil"),
    ("2026-11-09 kuni", "to'qqizinchi noyabr ikki ming yigirma oltinchi yil kuni"),
    ("Soat 14:30, 9:05 va 14:00", "Soat o'n to'rt o'ttiz, to'qqiz nol besh va o'n to'rt nol nol"),
    ("Narxi $5.50 va 10€", "Narxi besh dollar ellik sent va o'n yevro"),
    ("1500000 so'm", "bir million besh yuz ming so'm"),
    ("Havo -5 °C, kunduzi +25°C", "Havo minus besh daraja, kunduzi plyus yigirma besh daraja"),
    ("3-5 kun", "uch-besh kun"),
    ("2024-2025-yillar", "ikki ming yigirma to'rtinchi – ikki ming yigirma beshinchi yillar"),
    ("1/2 qism", "ikkidan bir qism"),
    ("3,5 foiz, 2,5%", "uch butun o'ndan besh foiz, ikki butun o'ndan besh foiz"),
    ("3-ta olma, 5ta nok, 4 ta behi, 1-ta", "uchta olma, beshta nok, to'rtta behi, bitta"),
    ("5-ga, 10-dan, 50-ga, 40-ga", "beshga, o'ndan, ellikka, qirqqa"),
    ("XXI asr, XIX asrda, II bob", "yigirma birinchi asr, o'n to'qqizinchi asrda, ikkinchi bob"),
]


@pytest.mark.parametrize("text,expected", _UZBEK_FORMS)
def test_uzbek_number_forms(text, expected):
    assert normalize_text(text, "Uzbek") == expected


def test_openai_speech_infers_the_engine_language():
    """A request with no `language` still gets Uzbek number words on Navoiy."""
    from api.routers.openai_compat import _spoken_language

    class UzbekEngine:
        supported_languages = ["uz"]

    class MultiEngine:
        supported_languages = ["en", "ru"]

    assert _spoken_language(UzbekEngine(), None) == "uz"
    assert _spoken_language(MultiEngine(), None) is None
    assert _spoken_language(MultiEngine(), "Uzbek") == "Uzbek"


@pytest.mark.parametrize("text,expected", [
    # A bare 7–12 digit run reads as a cardinal, a 13+ digit one digit by
    # digit: Navoiy-TTS babbles on raw digit runs instead of speaking them.
    ("1234567 raqami", "bir million ikki yuz o'ttiz to'rt ming besh yuz oltmish yetti raqami"),
    ("4111111111111111", "qirq bir, o'n bir, o'n bir, o'n bir, o'n bir, o'n bir, o'n bir, o'n bir"),
])
def test_uzbek_long_numbers_leave_no_digits(text, expected):
    assert normalize_text(text, "Uzbek") == expected


@pytest.mark.parametrize("text", [
    "kod 007",
    "1990-larda",
    "Men I harfini yozdim",    # a lone I is a letter, not a Roman numeral
])
def test_uzbek_ambiguous_forms_keep_digits(text):
    assert normalize_text(text, "Uzbek") == text


def test_russian_forms():
    assert normalize_text(
        "Встреча в 14:30, скидка 15%, 5-й этаж, 3,5 кг, 23-го мая, 3-я глава, 21% и 2%",
        "Russian",
    ) == (
        "Встреча в четырнадцать тридцать, скидка пятнадцать процентов, пятый этаж, "
        "три целых пять десятых кг, двадцать третьего мая, третья глава, "
        "двадцать один процент и два процента"
    )


def test_split_is_lossless_and_idempotent():
    text = "Men 5 ta olma oldim.\nI have 5 apples; это 250 рублей!"
    parts = split_by_number_language(text, "uz")
    assert "".join(piece for piece, _ in parts) == text
    once = normalize_text(text, "Uzbek")
    assert normalize_text(once, "Uzbek") == once


def test_word_votes():
    assert word_votes("the") == {"en": 1.0}
    assert "ru" in word_votes("рублей")
    assert word_votes("қишлоқ") == {"uzc": 1.0}
    assert word_votes("o'qiganman") == {"uz": 0.9}
    assert word_votes("iPhone") == {}


@pytest.mark.parametrize(
    ("raw", "spoken"),
    [
        (
            "Hisob raqam: 20208000900123456001",
            ("Hisob raqam: ikki ming yigirma, sakkiz ming, to'qqiz ming bir, "
            "ikki ming uch yuz qirq besh, olti ming bir"),
        ),
        (
            "20208000900123456001",
            ("ikki ming yigirma, sakkiz ming, to'qqiz ming bir, ikki ming uch yuz qirq besh, "
            "olti ming bir"),
        ),
        (
            "Karta raqami: 8600 1234 5678 9012",
            ("Karta raqami: sakson olti, nol nol, o'n ikki, o'ttiz to'rt, ellik olti, "
            "yetmish sakkiz, to'qson, o'n ikki"),
        ),
        (
            "JSHSHIR 31234567890123",
            ("JSHSHIR uch ming yuz yigirma uch, to'rt ming besh yuz oltmish yetti, "
            "sakkiz ming to'qqiz yuz bir, yigirma uch"),
        ),
        ("Aholisi 8000000000000 kishi", "Aholisi sakkiz trillion kishi"),
        (
            "Karta 8600 1234 5678 9012",
            ("Karta sakson olti, nol nol, o'n ikki, o'ttiz to'rt, ellik olti, yetmish sakkiz, "
            "to'qson, o'n ikki"),
        ),
        (
            "Karta 5614 6828 0512 9000",
            ("Karta ellik olti, o'n to'rt, oltmish sakkiz, yigirma sakkiz, nol besh, o'n ikki, "
            "to'qson, nol nol"),
        ),
        ("INN 302456789", "INN uch yuz ikki, to'rt yuz ellik olti, yetti yuz sakson to'qqiz"),
        ("MFO 00014", "MFO nol nol nol, o'n to'rt"),
        ("Xona raqami 305", "Xona raqami uch yuz besh"),
        ("Narxi 1500000", "Narxi bir million besh yuz ming"),
    ],
)
def test_uzbek_account_numbers_read_in_groups(raw, spoken):
    assert normalize_text(raw, "Uzbek") == spoken


def test_uzbek_bare_long_numbers_read_as_quantities():
    spoken = normalize_text("465465654625624562456425645", "Uzbek")
    assert spoken.startswith("to'rt yuz oltmish besh septillion")
    assert spoken.endswith("olti yuz qirq besh")
    assert not any(c.isdigit() for c in spoken)
    # Beyond the scale table (10**36) a run falls back to blocks of four.
    assert normalize_text("1" * 40, "Uzbek").startswith("bir ming yuz o'n bir, bir ming yuz o'n bir")
