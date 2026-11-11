# Brend to'plami

Belgi: bir nuqtada tutashgan uchta halqa (ovoz va uning ikki aks-sadosi). Belgida harf yo'q, shuning uchun mahsulot nomi o'zgarsa ham u o'zgarmaydi.

Jonli brend-buk (animatsiyalar bilan): https://claude.ai/artifact/U6jpXtM9H1ag8A3sx98dWV
Maketlar: MEDEO, `sado-indigo.dsai`, «Brend-buk» sahifasi.

## Tuzilishi

- To'r: 140×140 (1 birlik u = 14). Halqa diametrlari 4u, 7u, 10u; chap chetdagi bitta nuqtada tutashadi.
- Chiziq qalinligi: 11 (0,8u). Shaffoflik: 100% / 65% / 35% (ichkaridan tashqariga).
- Himoya maydoni: har tomondan 2u.
- Eng kichik o'lcham: to'liq belgi 32 px. 16–31 px uchun `logo/mark-small.svg` (ikki halqa, chiziq 18).

## Fayllar

| Jild | Fayl | Qayerda ishlatiladi |
| --- | --- | --- |
| `logo/` | `mark.svg` | Interfeys ichida; rangni `currentColor` dan oladi |
| `logo/` | `mark-on-dark.svg`, `mark-on-light.svg`, `mark-white.svg`, `mark-indigo.svg` | Tayyor rangli variantlar |
| `logo/` | `mark-small.svg` | 16–31 px |
| `logo/png/` | `mark-*-256.png`, `mark-*-1024.png` | SVG ishlamaydigan joylar |
| `icon/` | `app-icon.ico` | Windows: 16, 20, 24, 32, 40, 48, 64, 256 px (32 dan kichigi — ikki halqali belgi) |
| `icon/` | `app-icon.icns` | macOS: 16–1024, @1x va @2x; shakl 824/1024 ga kichraytirilgan, ostida yumshoq soya |
| `icon/png/` | `app-icon-indigo-*.png` | Linux va boshqa o'lchamlar; `dark` va `light` muqobil variantlar |
| `icon/` | `favicon.svg`, `favicon-32.png` | Veb |
| `tray/` | `trayTemplate.png`, `trayTemplate@2x.png` | macOS tray (tizim o'zi bo'yaydi) |
| `tray/` | `tray-white-*.png`, `tray-dark-*.png` | Windows va Linux: to'q va och panel |
| `motion/` | `mark-motion.css` | Belgi animatsiyalari |
| `motion/` | `mark-*.svg` | Har holatning mustaqil namunasi |
| | `tokens.css` | Ilova ranglari |

## Electron'ga ulash

```js
// main process
new BrowserWindow({ icon: path.join(__dirname, "brand/icon/png/app-icon-indigo-512.png") })
new Tray(path.join(__dirname, process.platform === "darwin" ? "brand/tray/trayTemplate.png" : "brand/tray/tray-white-16.png"))
```

`electron-builder`: `mac.icon = brand/icon/app-icon.icns`, `win.icon = brand/icon/app-icon.ico`, `linux.icon = brand/icon/png`.

## Animatsiya

```html
<svg class="mark" data-state="idle" viewBox="0 0 140 140" aria-hidden="true">
  <circle class="mark__r3" cx="70" cy="70" r="64.5"/>
  <circle class="mark__r2" cx="49" cy="70" r="43.5"/>
  <circle class="mark__r1" cx="28" cy="70" r="22.5"/>
</svg>
```

| `data-state` | Ma'nosi | Davomiyligi | Qayerda |
| --- | --- | --- | --- |
| `reveal` | Paydo bo'lish | 700 ms + 220 ms, bir marta | Ilova ochilishi, o'rnatish ekrani |
| `listening` | Tinglash | 1,6 s, takrorlanadi | Diktovka oynasi, yozish |
| `processing` | Ishlov berish | 1,1 s, takrorlanadi | Generatsiya, model yuklash |
| `speaking` | Gapirish | 520 ms, takrorlanadi | Natijani tinglash |
| `speaking-live` | Gapirish, haqiqiy ovoz bilan | `--mark-amp` (0..1) | Pleyer |
| `success` | Tayyor | 480 ms, bir marta | Jarayon yakuni |
| `muted` | O'chiq | statik | Oflayn, mikrofon o'chiq |

`prefers-reduced-motion` yoqilganda barcha harakat o'chadi.

## Mumkin emas

Cho'zish, aylantirish, shaffoflikni tenglashtirish, halqalarni har xil rangga bo'yash, soya yoki nur qo'shish, ichiga harf yozish.

## Qayta yig'ish

`icon/` dagi PNG, ICO va ICNS fayllari `scripts/brand_icons.py` dan chiqadi
(`uv run python scripts/brand_icons.py`): belgi geometriyasi va plita ranglari
skriptda shu README bilan bir xil; SVG manbalar qo'lda saqlanadi. Har o'lcham
4–8× supersampling bilan alohida chiziladi, kichraytirilgan nusxa emas.

## Tekshirilmagan

- `.icns` va `.ico` fayllari Windows ish stolida tekshirildi (yorliq ikonkasi); macOS Dock va haqiqiy o'rnatuvchilarda sinab ko'rilmagan.
- Holat ranglari (yashil, sariq, qizil) uchun aniq kodlar berilmagan, shuning uchun bu to'plamga kiritilmadi.
