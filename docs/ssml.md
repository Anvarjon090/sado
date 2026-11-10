# SSML

Sado speaks SSML (Speech Synthesis Markup Language, W3C) on `POST /generate`
and `POST /v1/audio/speech`: when the text starts with `<speak>`, it is parsed
as an SSML document instead of plain text. The Voice page needs no switch —
paste the document into the script box.

```xml
<speak>
  <p>Assalomu alaykum! <break time="400ms"/> Bugun uchta yangilik bor.</p>
  <s>Birinchisi <emphasis>juda</emphasis> muhim.</s>
  <prosody rate="slow" volume="-3dB">Ikkinchisini sekin o'qiyman.</prosody>
  <lang xml:lang="ru">Третья новость — по-русски.</lang>
  <voice name="Aisha">Uchinchisini Aisha aytadi.</voice>
  Telefon: <say-as interpret-as="telephone">+998 90 123 45 67</say-as>.
</speak>
```

## What each element does

The engine clones a voice from a reference clip and takes a speed and a
language per call; it has no pitch, emphasis or phoneme input. The subset
below maps onto exactly those controls and nothing is faked beyond what the
table says. Anything else is spoken plainly and reported.

| Element | Effect |
| --- | --- |
| `<speak>` | Root. The SSML namespace is accepted and ignored. |
| `<p>` | A 650 ms breath after the paragraph. |
| `<s>` | A sentence; a full stop is added when the text has no terminal punctuation. |
| `<break time="500ms"/>`, `<break strength="strong"/>` | Silence after the preceding text. Strengths: none 0, x-weak 100, weak 200, medium 350 (the default), strong 650, x-strong 1000 ms. Capped at 10 s. |
| `<prosody rate>` | Speed for the span: `x-slow` 0.6, `slow` 0.8, `medium` 1, `fast` 1.25, `x-fast` 1.5, `80%`, `1.2`, or relative `+10%`; clamped to 0.5–2. |
| `<prosody volume>` | Gain for the span: `silent` −40, `x-soft` −12, `soft` −6, `medium` 0, `loud` +6, `x-loud` +9 dB, `+3dB`, `50%`; clamped to −40…+12 dB. Applied before the output preset's loudness match. |
| `<prosody pitch range contour>` | Not controllable on a cloned voice. Spoken with the voice's own pitch; warned. |
| `<emphasis>` | 8 % slower and +1.5 dB (`level="none"` changes nothing). The engine has no emphasis of its own. |
| `<say-as interpret-as="characters">` (or `spell-out`) | Spelled letter by letter: `UZB 12` → `U Z B 1 2`. |
| `<say-as interpret-as="date|time|cardinal|ordinal|telephone|…">` | Left to the text normalizer, which already reads numbers, dates, prices and phone numbers in the span's language. |
| `<sub alias="Toshkent">TSH</sub>` | The alias is spoken. |
| `<lang xml:lang="ru-RU">` | The span's language for the engine and the number reader (`ru-RU` → `ru`). |
| `<voice name="Aisha">` | The span is rendered with that saved voice (id or name, case-insensitive). An unknown name keeps the request's voice and warns. Not available on remote workers. |
| `<phoneme>`, `<audio>`, `<mark>` | Not supported: the text inside `<phoneme>` and `<audio>` is spoken, `<mark>` is ignored; each warns once. |

Warnings come back in the `X-SSML-Warnings` response header (a JSON array)
and in the streaming `start` event; the app shows them as a notice. A
document with a `DOCTYPE` or entity declaration, malformed XML, or no text at
all is refused with HTTP 400 and a message that says why.

## How it is rendered

Each span is one engine call with its own speed, language and (for
`<voice>`) reference. The engine pads every render with about 200 ms of
silence per side; that padding is trimmed to a word gap before the spans are
joined, so a `<break time="500ms"/>` is the 500 ms the listener hears and
two spans joined without a break part like words, not by a hole. Silences are
stitched between spans exactly as for `[pause 300ms]` markers, and paragraph breaks are the same 650 ms breath a
blank line gets in plain text. Spans longer than the chunk limit are split at
sentence boundaries as usual. The take guard (re-render when a span comes
back as another voice) runs on spans in the request's voice; a `<voice>` span
is judged against its own reference.

Plain-text markers keep working: `[pause 300ms]`, `[[respelling]]`, the
pronunciation dictionary, and — in Audiobook and Stories — the longform
dialect (`[voice:NAME]`, `[slow]`, `[spell]`, see
[expressive-speech.md](expressive-speech.md)). Inside an SSML document use
the SSML elements instead; `[pause]` inside SSML text is read as text.
