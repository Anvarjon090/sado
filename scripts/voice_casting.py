#!/usr/bin/env python3
"""Cast sixteen age-and-gender voices from OmniVoice's voice-design space, by ear and by measurement.

    uv run python scripts/voice_casting.py audition --out D:/casting            # render & rank candidates
    uv run python scripts/voice_casting.py bench    --out D:/casting            # 7 texts × 16 cast voices + listening page
    uv run python scripts/voice_casting.py install  --out D:/casting            # save the cast as Sado voices

What the engine really offers for a designed voice is small and known:
``gender`` × ``age`` (child, teenager, young adult, middle-aged, elderly) ×
``pitch`` (five steps) × ``whisper``, plus the sampling seed, which picks the
speaker inside that box. Nothing in the model takes "soft", "warm" or
"smooth"; those arrive or do not with the seed. So this script does what a
casting director does: for each of the 16 slots it renders several candidates
(seeds × tag variants) on one audition sentence, measures each one — F0 against
the slot's human range, harmonics-to-noise and cepstral peak prominence
(smooth vs rough), 2–5 kHz presence (harsh vs soft), spectral tilt, loudness
range — checks it with the local Uzbek STT, ranks, and keeps the softest
intelligible voice whose pitch sits where a person of that age sits. The pick
is pinned by its audition WAV: installing it stores that clip as the voice's
reference, so every later take clones exactly the voice you heard rather than
re-rolling the design dice.

The ranking is a transparent weighted sum (``score()``), printed per
candidate; it narrows the field, it does not decide. ``bench`` renders the
seven benchmark texts for every cast voice (raw engine output and the natural
output path side by side) and writes ``index.html`` so the age groups can be
heard next to each other. Nothing leaves the machine.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import soundfile as sf
import torch

from services import voice_intake as vi
from services.audio_dsp import finalize_output
from services.speech_metrics import analyze_file

AUDITION_TEXT = (
    "Bugun ob-havo juda yaxshi, shuning uchun biz bolalar bilan bog'ga bordik. "
    "Siz ham biz bilan borasizmi?"
)

#: Benchmark texts shared by every voice (the owner's seven categories).
SUHBAT = (
    "Kecha do'stlarim bilan shahar markazidagi yangi kafega bordik. Choy ichib, uzoq suhbatlashdik "
    "va kelgusi hafta yana uchrashishga kelishib oldik."
)
HIKOYA = (
    "Qadim zamonlarda tog'lar orasidagi kichik bir qishloqda dono bir chol yashar ekan. Har kuni tong "
    "otishi bilan u bog'iga chiqib, daraxtlar bilan gaplashar, qushlarning sayrashiga quloq solar ekan. "
    "[pause 650ms] Bir kuni qishloqqa notanish yo'lovchi kelibdi. U choldan yo'l so'rabdi, chol esa unga "
    "avval choy ichib, dam olishni taklif qilibdi."
)
FONEMA = (
    "Qo'qon, G'ijduvon va Xo'jayli shaharlarida ko'ngilochar tadbirlar o'tkazildi. Shirin choy, chiroyli "
    "gullar, keng ko'cha va tong shabadasi."
)
SONLAR = (
    "2026-yilda kompaniyaning daromadi 150 million so'mga yetdi; bir dona mahsulot 45 000 so'm turadi, "
    "yig'ilish 15-mart, soat 14:30 da."
)
BENCH_TEXTS: list[tuple[str, str]] = [
    ("salom", "Salom! Qalaysiz, ishlaringiz yaxshimi?"),
    ("suhbat", SUHBAT),
    ("savol", "Siz ertaga uchrashuvga kelasizmi, yoki boshqa kunga qoldiramizmi?"),
    ("his", "Vooy, bu ajoyib yangilik! Men juda xursandman, nihoyat orzuimiz ushaldi!"),
    ("hikoya", HIKOYA),
    ("fonema", FONEMA),
    ("sonlar", SONLAR),
]

#: The sixteen slots. ``f0`` is the human median range for that age and sex
#: (Hz); ``tags`` are the engine's own tokens, the first variant preferred.
#: The pitch words are calibrated on what the engine actually renders for a
#: male young adult (2026-11-10, 6 seeds each): moderate ≈ 165 Hz, low ≈ 143,
#: very low ≈ 117 — so an adult man needs "low"/"very low" to land where men
#: speak, and "moderate" is a teenager.
SLOTS: list[dict] = [
    {"id": "05_erkak", "age": 5, "sex": "erkak", "name": "Bola (o'g'il, 5)", "f0": (230, 310),
     "tags": ["male, child, high pitch", "male, child, moderate pitch"]},
    {"id": "05_ayol", "age": 5, "sex": "ayol", "name": "Bola (qiz, 5)", "f0": (240, 330),
     "tags": ["female, child, high pitch", "female, child, moderate pitch"]},
    {"id": "15_erkak", "age": 15, "sex": "erkak", "name": "O'smir (o'g'il, 15)", "f0": (140, 210),
     "tags": ["male, teenager, moderate pitch", "male, teenager, low pitch"]},
    {"id": "15_ayol", "age": 15, "sex": "ayol", "name": "O'smir (qiz, 15)", "f0": (200, 265),
     "tags": ["female, teenager, moderate pitch", "female, teenager, high pitch"]},
    {"id": "20_erkak", "age": 20, "sex": "erkak", "name": "Yigit (20)", "f0": (105, 140),
     "tags": ["male, young adult, low pitch", "male, young adult, very low pitch"]},
    {"id": "20_ayol", "age": 20, "sex": "ayol", "name": "Qiz (20)", "f0": (190, 245),
     "tags": ["female, young adult, moderate pitch", "female, young adult, high pitch"]},
    {"id": "30_erkak", "age": 30, "sex": "erkak", "name": "Erkak (30)", "f0": (100, 132),
     "tags": ["male, young adult, very low pitch", "male, young adult, low pitch"]},
    {"id": "30_ayol", "age": 30, "sex": "ayol", "name": "Ayol (30)", "f0": (180, 230),
     "tags": ["female, young adult, moderate pitch", "female, young adult, low pitch"]},
    {"id": "40_erkak", "age": 40, "sex": "erkak", "name": "Erkak (40)", "f0": (95, 125),
     "tags": ["male, middle-aged, very low pitch", "male, middle-aged, low pitch"]},
    {"id": "40_ayol", "age": 40, "sex": "ayol", "name": "Ayol (40)", "f0": (170, 222),
     "tags": ["female, middle-aged, low pitch", "female, middle-aged, moderate pitch"]},
    {"id": "50_erkak", "age": 50, "sex": "erkak", "name": "Erkak (50)", "f0": (92, 120),
     "tags": ["male, middle-aged, very low pitch", "male, middle-aged, low pitch"]},
    {"id": "50_ayol", "age": 50, "sex": "ayol", "name": "Ayol (50)", "f0": (165, 212),
     "tags": ["female, middle-aged, low pitch", "female, middle-aged, moderate pitch"]},
    {"id": "60_erkak", "age": 60, "sex": "erkak", "name": "Erkak (60)", "f0": (95, 128),
     "tags": ["male, elderly, very low pitch", "male, elderly, low pitch"]},
    {"id": "60_ayol", "age": 60, "sex": "ayol", "name": "Ayol (60)", "f0": (160, 208),
     "tags": ["female, elderly, low pitch", "female, elderly, moderate pitch"]},
    {"id": "70_erkak", "age": 70, "sex": "erkak", "name": "Keksa erkak (70)", "f0": (100, 140),
     "tags": ["male, elderly, low pitch", "male, elderly, very low pitch"]},
    {"id": "70_ayol", "age": 70, "sex": "ayol", "name": "Keksa ayol (70)", "f0": (160, 212),
     "tags": ["female, elderly, low pitch", "female, elderly, moderate pitch"]},
]

DEFAULT_SEEDS = (7, 11, 23, 42, 101, 1234)


# ── HTTP ───────────────────────────────────────────────────────────────────


def _multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
    for name, (filename, data, mime) in files.items():
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                 f"Content-Type: {mime}\r\n\r\n").encode() + data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def _post(url: str, fields: dict[str, str], files: dict[str, tuple[str, bytes, str]] | None = None,
          timeout: int = 900) -> bytes:
    body, content_type = _multipart(fields, files or {})
    request = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": content_type})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def render_raw(args, text: str, instruct: str, seed: int, out: Path) -> Path:
    """One engine call in voice-design mode; the engine's own output, unprocessed."""
    fields = {
        "text": text, "language": args.language, "engine": args.engine, "instruct": instruct,
        "seed": str(seed), "num_step": str(args.steps), "guidance_scale": str(args.cfg),
        "effect_preset": "raw",
    }
    out.write_bytes(_post(args.backend.rstrip("/") + "/generate", fields))
    return out


def natural_copy(raw: Path, out: Path, pause_scale: float) -> Path:
    """The natural output path applied offline to a raw take — identical to
    what the backend returns for ``effect_preset=natural``."""
    x, sr = sf.read(str(raw), dtype="float32")
    y = finalize_output(torch.from_numpy(x)[None, :], sr, "natural", pause_scale=pause_scale)
    sf.write(str(out), y[0].numpy(), sr, subtype="PCM_16")
    return out


def transcribe(stt_url: str, path: Path) -> str | None:
    try:
        raw = _post(stt_url.rstrip("/") + "/v1/audio/transcriptions", {"language": "uz"},
                    {"file": (path.name, path.read_bytes(), "audio/wav")}, timeout=300)
        return json.loads(raw.decode("utf-8")).get("text")
    except (urllib.error.URLError, OSError, ValueError):
        return None


# ── scoring ────────────────────────────────────────────────────────────────


def f0_penalty(f0: float | None, lo: float, hi: float) -> float:
    """Semitones outside the slot's range (0 inside). A male-range voice on a
    female slot lands around 8–10 st and is effectively disqualified."""
    if f0 is None:
        return 12.0
    if lo <= f0 <= hi:
        return 0.0
    edge = lo if f0 < lo else hi
    return abs(12.0 * (torch.log2(torch.tensor(f0 / edge))).item())


def score(metrics: dict, slot: dict, cer: float | None) -> tuple[float, dict]:
    """Higher is better. Terms (each explained in the report):

    * ``-3 × f0 penalty``: the voice must sit in the age's pitch range;
    * ``+0.6 × HNR`` and ``+3 × CPP``: smooth, periodic phonation over rough;
    * ``-0.5 × (presence + 16)``: 2–5 kHz presence above a human reference's
      −16 dB reads as harsh;
    * ``+0.8 × LRA``: dynamics kept;
    * ``-40 × CER``: must say the words (a missing STT counts as 0 % CER).
    """
    lo, hi = slot["f0"]
    pen = f0_penalty(metrics.get("f0_median_hz"), lo, hi)
    hnr = metrics.get("hnr_db") or 0.0
    cpp = metrics.get("cpp_db") or 0.0
    presence = metrics.get("presence_db") if metrics.get("presence_db") is not None else -16.0
    lra = metrics.get("lra_lu") or 0.0
    terms = {
        "f0": -3.0 * pen,
        "hnr": 0.6 * hnr,
        "cpp": 3.0 * cpp,
        "presence": -0.5 * max(0.0, presence + 16.0),
        "lra": 0.8 * lra,
        "cer": -40.0 * (cer or 0.0),
    }
    return round(sum(terms.values()), 2), {k: round(v, 2) for k, v in terms.items()}


# ── modes ──────────────────────────────────────────────────────────────────


def audition(args) -> int:
    out = args.out / "audition"
    out.mkdir(parents=True, exist_ok=True)
    casting = {"model": args.model_label, "settings": {"steps": args.steps, "cfg": args.cfg,
               "pause_scale": args.pause_scale, "text": AUDITION_TEXT}, "slots": {}}
    slots = [s for s in SLOTS if not args.slots or s["id"] in args.slots]
    for slot in slots:
        sdir = out / slot["id"]
        sdir.mkdir(exist_ok=True)
        print(f"\n== {slot['id']}  {slot['name']}  F0 {slot['f0'][0]}–{slot['f0'][1]} Hz")
        candidates = []
        for variant, instruct in enumerate(slot["tags"][: args.variants]):
            for seed in args.seeds:
                stem = f"v{variant}_s{seed}"
                raw = sdir / f"{stem}.raw.wav"
                try:
                    if not raw.exists() or args.force:
                        render_raw(args, AUDITION_TEXT, instruct, seed, raw)
                except urllib.error.HTTPError as exc:
                    print(f"  {stem}: backend {exc.code}: {exc.read().decode('utf-8', 'replace')[:160]}")
                    continue
                except urllib.error.URLError as exc:
                    print(f"Sado backend'ga ulanib bo'lmadi ({args.backend}): {exc.reason}")
                    return 1
                nat = natural_copy(raw, sdir / f"{stem}.wav", args.pause_scale)
                metrics = analyze_file(str(nat)).to_dict()
                heard = None if args.no_stt else transcribe(args.stt, nat)
                cer = vi.cer(vi.ascii_apostrophes(AUDITION_TEXT), heard) if heard else None
                total, terms = score(metrics, slot, cer)
                candidates.append({"stem": stem, "instruct": instruct, "seed": seed, "file": str(nat),
                                   "raw": str(raw), "metrics": metrics, "transcript": heard, "cer": cer,
                                   "score": total, "terms": terms})
                print(f"  {stem:<10} {instruct:<38} F0 {metrics['f0_median_hz']!s:>6} Hz  HNR {metrics['hnr_db']!s:>5}"
                      f"  CPP {metrics['cpp_db']!s:>5}  pres {metrics['presence_db']!s:>6}  LRA {metrics['lra_lu']!s:>4}"
                      f"  CER {('—' if cer is None else f'{cer:.0%}'):>4}  → {total}")
        candidates.sort(key=lambda c: c["score"], reverse=True)
        casting["slots"][slot["id"]] = {**{k: v for k, v in slot.items()}, "candidates": candidates,
                                        "pick": candidates[0]["stem"] if candidates else None}
        if candidates:
            best = candidates[0]
            print(f"  → tanlov: {best['stem']} ({best['instruct']}, seed {best['seed']}), ball {best['score']}")
    (args.out / "casting.json").write_text(json.dumps(casting, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nKasting yozildi: {args.out / 'casting.json'} — endi har bir tanlovni eshiting; "
          f"boshqa nomzodni afzal ko'rsangiz casting.json dagi 'pick' ni o'zgartiring.")
    return 0


def _load_casting(args) -> dict:
    path = args.out / "casting.json"
    if not path.exists():
        sys.exit(f"{path} topilmadi — avval `audition` ni yurgizing")
    return json.loads(path.read_text(encoding="utf-8"))


def _picked(slot_entry: dict) -> dict | None:
    for c in slot_entry.get("candidates", []):
        if c["stem"] == slot_entry.get("pick"):
            return c
    return None


def bench(args) -> int:
    casting = _load_casting(args)
    out = args.out / "bench"
    out.mkdir(parents=True, exist_ok=True)
    report = {"model": casting.get("model"), "settings": casting.get("settings"), "voices": {}}
    for slot_id, entry in casting["slots"].items():
        pick = _picked(entry)
        if pick is None:
            continue
        vdir = out / slot_id
        (vdir / "raw").mkdir(parents=True, exist_ok=True)
        (vdir / "natural").mkdir(parents=True, exist_ok=True)
        rows = []
        print(f"\n== {slot_id} {entry['name']} — {pick['instruct']} / seed {pick['seed']}")
        for case_id, text in BENCH_TEXTS:
            raw = vdir / "raw" / f"{case_id}.wav"
            try:
                if not raw.exists() or args.force:
                    # The identity is the audition clip: clone it, do not re-roll the design.
                    fields = {"text": text, "language": args.language, "engine": args.engine, "seed": str(pick["seed"]),
                              "num_step": str(args.steps), "guidance_scale": str(args.cfg), "effect_preset": "raw",
                              "ref_text": AUDITION_TEXT}
                    files = {"ref_audio": ("audition.wav", Path(pick["file"]).read_bytes(), "audio/wav")}
                    raw.write_bytes(_post(args.backend.rstrip("/") + "/generate", fields, files))
            except urllib.error.HTTPError as exc:
                print(f"  {case_id}: backend {exc.code}: {exc.read().decode('utf-8', 'replace')[:160]}")
                continue
            except urllib.error.URLError as exc:
                print(f"Sado backend'ga ulanib bo'lmadi ({args.backend}): {exc.reason}")
                return 1
            nat = natural_copy(raw, vdir / "natural" / f"{case_id}.wav", args.pause_scale)
            metrics = analyze_file(str(nat)).to_dict()
            heard = None if args.no_stt else transcribe(args.stt, nat)
            rows.append({"case": case_id, "text": text, "raw": str(raw), "natural": str(nat),
                         "metrics": metrics, "transcript": heard})
            print(f"  {case_id:<8} {metrics['duration_s']:>5.1f}s  F0 {metrics['f0_median_hz']}  HNR {metrics['hnr_db']}"
                  f"  LRA {metrics['lra_lu']}  pauses {metrics['pauses']}")
        config = {"slot": slot_id, "name": entry["name"], "age": entry["age"], "sex": entry["sex"],
                  "instruct": pick["instruct"], "seed": pick["seed"], "audition_clip": pick["file"],
                  "model": casting.get("model"), "generation": {"steps": args.steps, "cfg": args.cfg,
                  "effect_preset": "natural", "pause_scale": args.pause_scale, "language": args.language}}
        (vdir / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=1), encoding="utf-8")
        report["voices"][slot_id] = {"config": config, "cases": rows}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    write_listening_page(args.out, casting, report)
    print(f"\nTinglash sahifasi: {args.out / 'index.html'}")
    return 0


def write_listening_page(root: Path, casting: dict, report: dict) -> None:
    """A static page: one row per age, male and female side by side, every
    benchmark text as a player, raw and natural one above the other."""
    def rel(p: str) -> str:
        return html.escape(os.path.relpath(p, root).replace(os.sep, "/"))

    ages = sorted({s["age"] for s in SLOTS})
    parts = ["<!doctype html><html lang='uz'><head><meta charset='utf-8'><title>Sado — 16 ovoz</title>",
             "<style>body{font:14px/1.4 system-ui,sans-serif;margin:24px;background:#111;color:#eee}",
             "h1,h2{font-weight:600}table{border-collapse:collapse;width:100%}td,th{border:1px solid #333;padding:8px;vertical-align:top}",
             "th{background:#1b1b1b;text-align:left}audio{width:260px;display:block;margin:2px 0}",
             ".meta{color:#9a9;font-size:12px}.cand{color:#aaa;font-size:12px}</style></head><body>",
             (f"<h1>Sado — 16 ta ovoz, yosh bo'yicha</h1><p class='meta'>Model: {html.escape(str(casting.get('model')))} · "
              f"qadamlar {casting['settings']['steps']} · CFG {casting['settings']['cfg']} · pauza {casting['settings']['pause_scale']}× · "
              "har bir ovoz: audition namunasi (identifikatsiya) va 7 ta sinov matni (natural / raw).</p>")]
    for age in ages:
        parts.append(f"<h2>{age} yosh</h2><table><tr><th style='width:50%'>Erkak</th><th>Ayol</th></tr><tr>")
        for sex in ("erkak", "ayol"):
            slot_id = f"{age:02d}_{sex}"
            entry = casting["slots"].get(slot_id)
            pick = _picked(entry) if entry else None
            parts.append("<td>")
            if entry and pick:
                m = pick["metrics"]
                parts.append(f"<b>{html.escape(entry['name'])}</b><div class='meta'>{html.escape(pick['instruct'])} · seed {pick['seed']} · "
                             f"F0 {m['f0_median_hz']} Hz · HNR {m['hnr_db']} dB · CPP {m['cpp_db']} · presence {m['presence_db']} dB · ball {pick['score']}</div>"
                             f"<div class='meta'>Audition:</div><audio controls preload='none' src='{rel(pick['file'])}'></audio>")
                voice = report["voices"].get(slot_id)
                if voice:
                    for row in voice["cases"]:
                        parts.append(f"<div class='meta'>{html.escape(row['case'])} — natural</div><audio controls preload='none' src='{rel(row['natural'])}'></audio>"
                                     f"<div class='cand'>raw</div><audio controls preload='none' src='{rel(row['raw'])}'></audio>")
                others = [c for c in entry["candidates"] if c["stem"] != pick["stem"]][:3]
                if others:
                    parts.append("<div class='cand'>Boshqa nomzodlar: " + " · ".join(
                        f"<a style='color:#8cf' href='{rel(c['file'])}'>{html.escape(c['stem'])} ({c['score']})</a>" for c in others) + "</div>")
            else:
                parts.append("<i>yo'q</i>")
            parts.append("</td>")
        parts.append("</tr></table>")
    parts.append("<p class='meta'>Raqamlar yo'nalishni ko'rsatadi; yakuniy baho — quloq.</p></body></html>")
    (root / "index.html").write_text("".join(parts), encoding="utf-8")


def install(args) -> int:
    casting = _load_casting(args)
    installed = []
    for slot_id, entry in casting["slots"].items():
        pick = _picked(entry)
        if pick is None:
            continue
        personality = f"design:{pick['instruct']}|seed:{pick['seed']}|model:{casting.get('model')}"
        fields = {"name": entry["name"], "ref_text": AUDITION_TEXT, "language": "Uzbek", "kind": "clone",
                  "personality": personality}
        files = {"ref_audio": (f"{slot_id}.wav", Path(pick["file"]).read_bytes(), "audio/wav")}
        try:
            profile = json.loads(_post(args.backend.rstrip("/") + "/profiles", fields, files).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            print(f"{slot_id}: backend {exc.code}: {exc.read().decode('utf-8', 'replace')[:200]}")
            continue
        installed.append((slot_id, profile.get("id")))
        print(f"{slot_id:<10} → profil {profile.get('id')}  {entry['name']}")
    (args.out / "installed.json").write_text(json.dumps(installed, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=("audition", "bench", "install"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--slots", nargs="*", help="slot ids to limit to (default all 16)")
    parser.add_argument("--seeds", nargs="*", type=int, default=list(DEFAULT_SEEDS))
    parser.add_argument("--variants", type=int, default=2, help="tag variants per slot to audition")
    parser.add_argument("--steps", type=int, default=32)
    parser.add_argument("--cfg", type=float, default=3.0,
                        help="guidance; 3.0 held the gender/age tags where 2.0 drifted (see docs)")
    parser.add_argument("--pause-scale", type=float, default=1.6)
    parser.add_argument("--language", default="Uzbek")
    parser.add_argument("--engine", default="omnivoice")
    parser.add_argument("--model-label", default=os.environ.get("OMNIVOICE_MODEL", "active"))
    parser.add_argument("--backend", default=os.environ.get("SADO_URL", "http://127.0.0.1:3900"))
    parser.add_argument("--stt", default=os.environ.get("UZ_STT_URL", "http://127.0.0.1:3910"))
    parser.add_argument("--no-stt", action="store_true")
    parser.add_argument("--force", action="store_true", help="re-render clips that already exist")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    return {"audition": audition, "bench": bench, "install": install}[args.mode](args)


if __name__ == "__main__":
    sys.exit(main())
