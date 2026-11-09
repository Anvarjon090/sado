# Sado — UI konsepti (neon studiya)

Sado'ni **Sado** nomi bilan qayta chizilgan birinchi ekran. Bu hujjat
konseptni va uning qoidalarini saqlaydi; ilova kodi hali bu dizaynga
o'tkazilmagan.

## Fayllar

| Fayl | Nima |
|---|---|
| `sado-ui.html` | To'liq ishlaydigan maket (bitta fayl, shriftlar `fonts/` ichida) |
| `sado-desktop.png` | 1440×900 ko'rinishi |
| `sado-mobile.png` | 390 px, to'liq sahifa |
| `fonts/` | Onest (matn) va Unbounded (raqam/wordmark) — lokal woff2 |

Ochish: `sado-ui.html` ni brauzerda oching.

## Dunyo

**Neon studiya:** to'q grafit fon, feruza (`#35f0c6`) asosiy aksent, binafsha
(`#8b5cf6`) ikkinchi rol. Dunyo faqat to'rt narsani beradi — **shrift,
palitra, zichlik va bitta imzo harakat**; tartib, navigatsiya va boshqaruvlar
standart bo'lib qoladi.

**Imzo harakat:** jonli monitor — to'lqin chizig'i tanlangan ohang rangiga
bo'yaladi (`--wave-hue`), playhead hozirgi gapni ko'rsatadi. Ohang chipi va
monitor bir-biriga bog'langan: chipni almashtirsangiz, to'lqin rangi ham
almashadi.

## Tokenlar

```
fon        #07090c        panel      #0d1117      panel-2   #111721
chiziq     rgba(233,240,249,.08)     chiziq-2  rgba(233,240,249,.14)
matn       #e9f0f9        ikkilamchi #93a1b5      uchinchi  #7b899c
feruza     #35f0c6        feruza-siyoh #03211b    binafsha  #8b5cf6
ravon      #f5b544
radius     14px (karta) / 10px (kichik) / 99px (chip)
```

**Ohang ranglari (10 preset):** xotirjam `#35f0c6`, xursand `#ffd166`,
g'amgin `#6aa8ff`, jahldor `#ff5d6c`, qo'rqqan `#c084fc`, hayratda `#f472b6`,
pichirlab `#7dd3fc`, mehribon `#ff9f7a`, charchagan `#94a3b8`, kinoyali `#a3e635`.

**Shrift:** Onest — interfeys matni; Unbounded — wordmark va raqamlar
(`4.2s`, `00:01.8`). Ikkisi ham lokal fayl, tashqi so'rov yo'q.

## Ekran tuzilishi

- **Chap rels** — bo'limlar (Ovoz yaratish, Dublyaj, Loyihalar, Ovozlarim,
  Navbat, Sozlamalar) + pastda model kartasi (Navoiy-TTS, VRAM).
- **Asosiy ustun** — matn muharriri; ostida ovoz/til/model/tezlik, 10 ohang
  chipi, `Yaratish` va format tanlovi; pastda joriy loyiha va so'nggi loyihalar.
- **Jonli monitor** — to'lqin, RTF, oxirgi natijalar (ohang teglari bilan),
  navbat, ovoz profili va maslahat.

## Halol chegaralar

- Ism (`Dilnoza Karimova`), loyiha nomlari va davomiyliklar — **namunaviy
  kontent**, haqiqiy foydalanuvchi ma'lumoti emas.
- Raqamlar (`RTF 0.4×`, `VRAM 3.5 GB`) dizayn uchun; ilovada haqiqiy
  o'lchovlardan keladi.
- Bu maket faqat bitta ekranni ko'rsatadi; Dublyaj, Sozlamalar va boshqa
  sahifalar shu tizimda keyin chiziladi.

## Keyingi qadam

1. Tokenlarni `electron/src/renderer/src/styles` ichiga CSS o'zgaruvchilari
   sifatida ko'chirish (mavjud komponentlar bilan).
2. Onest/Unbounded'ni ilova ichiga qo'shish (`@font-face`, lokal).
3. Ekranlarni bosqichma-bosqich almashtirish: Ovoz yaratish → Dublyaj →
   Sozlamalar.
