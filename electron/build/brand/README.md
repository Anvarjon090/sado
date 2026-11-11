# Brend to'plami

Belgi: bir nuqtada tutashgan uchta halqa (ovoz va uning ikki aks-sadosi). Belgida harf yo'q, shuning uchun mahsulot nomi o'zgarsa ham u o'zgarmaydi.

Jonli brend-buk (animatsiyalar bilan): https://claude.ai/artifact/U6jpXtM9H1ag8A3sx98dWV
Maketlar: MEDEO, `sado-indigo.dsai`, «Brend-buk» sahifasi.

## Tuzilishi

- To'r: 140×140 (1 birlik u = 14). Halqa diametrlari 4u, 7u, 10u; chap chetdagi bitta nuqtada tutashadi.
- Chiziq qalinligi: 11 (0,8u). Shaffoflik: 100% / 65% / 35% (ichkaridan tashqariga).
- Himoya maydoni: har tomondan 2u.
- Eng kichik o'lcham: 16 px, har doim uchala halqa bilan (ilova belgisi uchun quyidagi jadval). `logo/mark-small.svg` (ikki halqa, chiziq 18) faqat bir rangli, 16 px dan kichik joylar uchun.

### Ilova belgisi kichik o'lchamlarda

`icon/make-icons.py` (Pillow + numpy) to'plamni `app-icon-*.svg` geometriyasidan yig'adi. 128 px va undan kattada SVG aynan chiziladi; kichikroqda 35 % li tashqi halqa yo'qolib ketmasligi uchun belgi bir oz kattaroq, chiziq qalinroq va tashqi halqalar ravshanroq:

| px | Belgi kengligi | Chiziq | Shaffoflik (ichkaridan tashqariga) |
| --- | --- | --- | --- |
| 64 | 60 % | 12 | 100 / 70 / 42 % |
| 48 | 62 % | 13 | 100 / 72 / 46 % |
| 40 | 63 % | 14 | 100 / 75 / 50 % |
| 32 | 64 % | 14,5 | 100 / 76 / 52 % |
| 24 | 66 % | 16 | 100 / 80 / 58 % |
| 20 | 67 % | 17 | 100 / 82 / 60 % |
| 16 | 68 % | 18 | 100 / 85 / 65 % |

128 px va undan katta: belgi 58 %, chiziq 11, 100 / 65 / 35 %.

## Fayllar

| Jild | Fayl | Qayerda ishlatiladi |
| --- | --- | --- |
| `logo/` | `mark.svg` | Interfeys ichida; rangni `currentColor` dan oladi |
| `logo/` | `mark-on-dark.svg`, `mark-on-light.svg`, `mark-white.svg`, `mark-indigo.svg` | Tayyor rangli variantlar |
| `logo/` | `mark-small.svg` | Bir rangli, 16 px dan kichik joylar; ilova belgisida ishlatilmaydi |
| `logo/png/` | `mark-*-256.png`, `mark-*-1024.png` | SVG ishlamaydigan joylar |
| `icon/` | `app-icon.ico` | Windows (16, 20, 24, 32, 40, 48, 64, 128, 256 px) |
| `icon/` | `app-icon.icns` | macOS (shakl 824/1024 ga kichraytirilgan) |
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
| `processing` | Ishlov berish: ichki halqadan aks-sado halqalari chiqib so'nadi | 1,8 s, takrorlanadi | Generatsiya, model yuklash |
| `speaking` | Gapirish | 520 ms, takrorlanadi | Natijani tinglash |
| `speaking-live` | Gapirish, haqiqiy ovoz bilan | `--mark-amp` (0..1) | Pleyer |
| `success` | Tayyor | 480 ms, bir marta | Jarayon yakuni |
| `muted` | O'chiq | statik | Oflayn, mikrofon o'chiq |

`prefers-reduced-motion` yoqilganda barcha harakat o'chadi.

## Mumkin emas

Cho'zish, aylantirish, shaffoflikni tenglashtirish, halqalarni har xil rangga bo'yash, soya yoki nur qo'shish, ichiga harf yozish.

## Manba

`icon/` dagi barcha fayllar brend-bukdan (`sado logo/brand/icon`) aynan ko'chirilgan, u yerda `icon/make-icons.py` yig'adi;
ilovada boshqa render ishlatilmaydi. Brend-buk yangilansa, papkani qaytadan nusxalang.

## Tekshirilmagan

- `.ico` Windows ish stolida (yorliq) tekshirildi; `.icns` macOS Dock va haqiqiy o'rnatuvchilarda sinab ko'rilmagan.
- Holat ranglari (yashil, sariq, qizil) uchun aniq kodlar berilmagan, shuning uchun bu to'plamga kiritilmadi.
