# Sado — o'zbek ovozi studiyasi

**Sado** — Sado (AGPL-3.0) asosidagi, o'zbek tiliga moslangan lokal ovoz
studiyasi. Hammasi shu kompyuterda ishlaydi: bulut, akkaunt va API kalit talab
qilinmaydi.

## Nima qila oladi

| Imkoniyat | Qanday |
|---|---|
| Matn → ovoz | O'zbekcha matnni ovozga aylantiradi |
| Ovoz klonlash | 5–15 soniyalik namunadan ovoz nusxasi |
| Video dublyaj | Videoni o'zbekcha ovoz bilan qayta ovozlash |
| Emotsiya | Navoiy modelida 10 ohang: xotirjam, xursand, g'amgin, jahldor, qo'rqqan, hayratda, pichirlab, mehribon, charchagan, kinoyali |
| Audiokitob | Boblarga bo'lingan, har bir qahramonga alohida ovoz |
| Diktovka | Ovoz bilan yozish va transkripsiya |

Interfeys o'zbekcha (`uz`), kerak bo'lsa boshqa 21 tilga o'tish mumkin.

## Talablar

- **Windows 10/11, macOS yoki Linux** (64-bit)
- **Python 3.11** — birinchi ishga tushirishda ilova o'zi tayyorlaydi
- **Node.js 20+ va Bun** — faqat manbadan ishga tushirish uchun
- **GPU** shart emas (CPU'da ishlaydi, lekin sekinroq). NVIDIA kartada tezroq.

## O'rnatish (manbadan)

```bash
git clone https://github.com/Anvarjon090/sado.git
cd sado
bun install
bun run dev
```

Birinchi ishga tushirishda ilova Python muhitini tayyorlaydi (bir necha daqiqa).

## O'zbekcha model (Navoiy-TTS)

Ilova sukut bo'yicha OmniVoice'da ishlaydi. Eng yaxshi o'zbekcha talaffuz uchun
**Navoiy-TTS** modelini ulang:

1. Modelni o'rnating — to'liq qo'llanma: [`docs/engines/navoiy.md`](docs/engines/navoiy.md)
2. `OMNIVOICE_NAVOIY_DIR` ni o'rnatish papkangizga ko'rsating
3. Ilovani qayta ishga tushiring

Shundan keyin **butun o'zbekcha dublyaj avtomatik Navoiy'da** ishlaydi, matn →
ovoz bo'limida esa dvigatelni qo'lda tanlaysiz.

## Hujjatlar

- [`docs/engines/navoiy.md`](docs/engines/navoiy.md) — o'zbek modeli
- [`docs/design/README.md`](docs/design/README.md) — Sado dizayn tizimi
- [`docs/install/`](docs/install/) — platformalar bo'yicha o'rnatish

## Litsenziya

AGPL-3.0 — asl loyiha [Anvarjon090/sado](https://github.com/Anvarjon090/sado).
O'zbekcha moslashtirish va Sado brendingi shu repozitoriyda.
