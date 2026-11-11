<div align="center">

<img src="docs/logo.png" alt="Sado" width="96" />

# Sado

**O'zbekcha ovoz studiyasi — to'liq lokal, bulutsiz.**

[![Litsenziya](https://img.shields.io/badge/litsenziya-AGPL--3.0-blue)](LICENSE)
[![Platforma](https://img.shields.io/badge/platforma-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](#boshla)
[![Til](https://img.shields.io/badge/interfeys-o%27zbekcha-35f0c6)](#interfeys)

</div>

Sado — o'z kompyuteringizda ishlaydigan ovoz studiyasi: matnni ovozga
aylantiradi, ovozni klonlaydi, videoni o'zbekcha ovoz bilan qayta ovo
zlaydi va audiokitob yaratadi. Akkaunt, API kalit va internet talab
qilinmaydi — hamma narsa shu kompyuterda qoladi.

## Imkoniyatlar

| Imkoniyat | Tavsif |
|---|---|
| **Matn → ovoz** | O'zbekcha matnni tabiiy ovozga aylantiradi |
| **Ovoz klonlash** | 5–15 soniyalik namunadan ovoz nusxasi |
| **Video dublyaj** | Videoni tarjima qilib, o'zbekcha ovozda qayta chiqaradi |
| **Emotsiya** | Navoiy modelida 10 ohang: xotirjam, xursand, g'amgin, jahldor, qo'rqqan, hayratda, pichirlab, mehribon, charchagan, kinoyali |
| **Audiokitob** | Boblarga bo'lingan, har bir qahramonga alohida ovoz |
| **Hikoyalar** | Ko'p ovozli matn muharriri |
| **Diktovka** | Ovoz bilan yozish va transkripsiya |
| **Ommaviy dublyaj** | Navbat, papkani kuzatish, 50+ video |
| **646 til** | Klonlangan ovoz boshqa tillarda ham gapiradi |

## Boshla

### Talablar

- **Windows 10/11, macOS yoki Linux** (64-bit)
- **Python 3.11** — birinchi ishga tushirishda ilova o'zi tayyorlaydi
- **Node.js 20+** va **Bun**
- **GPU** shart emas: CPU'da ishlaydi, NVIDIA kartada tezroq

### Manbadan o'rnatish

```bash
git clone https://github.com/Anvarjon090/sado.git
cd sado
bun install
bun run dev
```

Birinchi ishga tushirishda ilova Python muhitini tayyorlaydi (bir necha
daqiqa) va kerakli modelni yuklab oladi.

> **Yuklab olinadigan installer hali chiqarilmagan.** Hozircha manbadan
> ishga tushiriladi; tayyor `.exe` / `.dmg` / `.AppImage` keyingi
> nashrlarda [Releases](https://github.com/Anvarjon090/sado/releases)
> bo'limida paydo bo'ladi.

## O'zbekcha ovoz: Navoiy-TTS

Sukut bo'yicha dvigatel — OmniVoice (ko'p tilli). Eng yaxshi o'zbekcha
talaffuz va emotsiyalar uchun **Navoiy-TTS** modelini ulang:

1. Modelni o'rnatish: [`docs/engines/navoiy.md`](docs/engines/navoiy.md)
2. `OMNIVOICE_NAVOIY_DIR` ni o'rnatish papkangizga ko'rsating
3. Ilovani qayta ishga tushiring

Shundan keyin **butun o'zbekcha dublyaj avtomatik Navoiy'da** ishlaydi;
matn → ovoz bo'limida dvigatelni qo'lda tanlaysiz.

## Interfeys

Interfeys o'zbekcha (`uz`) va sukut bo'yicha shu tilda ochiladi. Boshqa
tillar Sozlamalar → Til bo'limida. Tarjima hozircha qismli: asosiy
ekranlar to'liq o'zbekcha, ayrim sozlama sahifalari inglizcha qoladi.

## Loyiha tuzilishi

```
backend/          FastAPI server, dvigatellar, dublyaj quvuri
electron/         Desktop qobiq va React interfeys
omnivoice/        Asosiy model va utilitalar
docs/             O'rnatish, dvigatellar, dizayn hujjatlari
tests/            Backend testlari (pytest)
scripts/          Yig'ish va yordamchi skriptlar
```

## Hujjatlar

- [`docs/engines/navoiy.md`](docs/engines/navoiy.md) — o'zbek modeli
- [`docs/install/`](docs/install/) — platformalar bo'yicha o'rnatish
- [`docs/design/README.md`](docs/design/README.md) — Sado dizayn tizimi
- [`CHANGELOG.md`](CHANGELOG.md) — o'zgarishlar tarixi

## Agent ko'nikmalari

Claude Code, Codex CLI yoki Cursor Sado bilan ishlashi uchun ko'nikmalar to'plamini o'rnating:

```bash
npx skills add Anvarjon090/sado
```

## Hissa qo'shish

Xato topsangiz yoki taklif bo'lsa — [issue](https://github.com/Anvarjon090/sado/issues)
oching. Kod uchun: fork → branch → testlar (`pytest`, `bun run test`) → PR.

## Litsenziya

**AGPL-3.0** — to'liq matn [`LICENSE`](LICENSE) faylida. Asl loyiha
mualliflarining huquqlari [`LICENSE-NOTICE.md`](LICENSE-NOTICE.md) da
saqlangan; o'zbekcha moslashtirish va Sado brendingi shu repozitoriyga
tegishli.
