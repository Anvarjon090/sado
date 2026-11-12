#!/usr/bin/env python3
"""Uzbek voice benchmark: the same texts for every voice, measured the same way.

    uv run python scripts/voice_bench.py --voice da62a368 --out D:/bench/aisha-natural
    uv run python scripts/voice_bench.py --voice da62a368 --out D:/bench/aisha-broadcast \
        --preset broadcast --pause-scale 1 --steps 16 --denoise on
    uv run python scripts/voice_bench.py --voice da62a368 --out D:/bench/aisha-v2 \
        --baseline D:/bench/aisha-natural

Eight categories of Uzbek text (short conversational lines, a long paragraph,
questions, emotional sentences, numbers and dates, mixed Uzbek/English/Russian,
two-paragraph narration, hard phonemes) are rendered through the running Sado
backend for each voice, then measured with ``services.speech_metrics`` —
loudness and loudness range, crest factor, pauses, F0 spread, spectral tilt —
and transcribed by the local Uzbek STT for a character error rate.

Every number is a *proxy*: it says how far a take moved in loudness range or
pause length, not whether it sounds human. The report ends where it has to —
with the files to listen to. ``--baseline`` prints each metric's delta against
an earlier run of the same voices, so an A/B of two settings is one command.
Nothing leaves the machine: the backend and the STT are local HTTP services.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services import voice_intake as vi
from services.speech_metrics import SUMMARY_COLUMNS, analyze_file

#: (id, text, check_cer). CER is skipped where the written form and the spoken
#: form legitimately differ (digits, foreign script).
PARAGRAPH = (
    "Toshkent shahrining markazida joylashgan eski bozor har kuni erta tongdan jonlanadi. "
    "Savdogarlar o'z rastalarini yangi meva va sabzavotlar bilan to'ldiradi, non yopuvchilar esa "
    "tandirdan issiq nonlarni chiqaradi. Bozorga kelgan har bir kishi bu yerda nafaqat xarid "
    "qiladi, balki tanishlari bilan suhbatlashib, kunning yangiliklarini ham bilib oladi."
)
QUESTIONS = (
    "Siz ertaga uchrashuvga kelasizmi? Qaysi vaqt sizga qulay bo'ladi? Yoki boshqa kunga qoldiramizmi?"
)
NUMBERS_DATES = (
    "2026-yilda kompaniyaning daromadi 150 million so'mga yetdi. Yig'ilish 15-mart, "
    "soat 14:30 da bo'ladi, qatnashchilar soni 48 nafar."
)
MIXED = (
    "Biz yangi API ni ishga tushirdik: the system is live now. Спасибо всем за поддержку, "
    "keyingi bosqich kelasi haftada."
)
NARRATION = (
    "Qadim zamonlarda tog'lar orasidagi kichik bir qishloqda dono bir chol yashar ekan. Har kuni tong "
    "otishi bilan u bog'iga chiqib, daraxtlar bilan gaplashar, qushlarning sayrashiga quloq solar ekan.\n\n"
    "Bir kuni qishloqqa notanish yo'lovchi kelibdi. U choldan yo'l so'rabdi, chol esa unga avval choy "
    "ichib, dam olishni taklif qilibdi. Shu suhbatdan katta bir do'stlik boshlanibdi."
)
PHONEMES = (
    "Qo'qon, G'ijduvon va Xo'jayli shaharlarida ko'ngilochar tadbirlar o'tkazildi. Shirin choy, "
    "chiroyli gullar, keng ko'cha va tong shabadasi — hammasi yangi bahorning belgisi."
)
CASES: list[tuple[str, str, bool]] = [
    ("short_greeting", "Salom! Qalaysiz?", True),
    ("short_reply", "Rahmat, hammasi joyida. O'zingiz-chi?", True),
    ("paragraph", PARAGRAPH, True),
    ("questions", QUESTIONS, True),
    ("joy", "Vooy, bu ajoyib yangilik! Men juda xursandman, nihoyat orzuimiz ushaldi!", True),
    ("sorrow", "Afsuski, u bugun kela olmadi. Hammamiz uni juda kutgan edik, lekin yo'llar yopilib qoldi.", True),
    ("numbers_dates", NUMBERS_DATES, False),
    ("mixed", MIXED, False),
    ("narration", NARRATION, True),
    ("phonemes", PHONEMES, True),
]


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


def _post(url: str, fields: dict[str, str], files: dict[str, tuple[str, bytes, str]], timeout: int) -> bytes:
    body, content_type = _multipart(fields, files)
    request = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": content_type})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


#: Frames quieter than this are room tone, not speech, when trimming for the STT.
STT_TRIM_FLOOR_DBFS = -45.0
STT_TRIM_MARGIN_S = 0.15
STT_PAD_S = 0.3


def stt_clip_bytes(path: Path) -> bytes:
    """The take trimmed to its speech (with a small margin) and padded with digital
    silence. Whisper-style STT invents words on the room-tone tail of a short
    take — "salom. qalaysiz?" came back three times with "uyoq" and "musiqa" on
    2026-11-12 — and the same take trimmed by 20 ms transcribed cleanly, so the
    CER must be measured on what the model actually said."""
    import io

    import numpy as np
    import soundfile as sf

    x, sr = sf.read(str(path), dtype="float32")
    if x.ndim > 1:
        x = x.mean(axis=1)
    hop = max(1, int(sr * 0.02))
    frames = np.lib.stride_tricks.sliding_window_view(x, hop)[::hop] if len(x) >= hop else x[None, :]
    level = 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9)
    loud = np.where(level > STT_TRIM_FLOOR_DBFS)[0]
    if len(loud):
        start = max(0, loud[0] * hop - int(STT_TRIM_MARGIN_S * sr))
        end = min(len(x), (loud[-1] + 1) * hop + int(STT_TRIM_MARGIN_S * sr))
        x = x[start:end]
    pad = np.zeros(int(STT_PAD_S * sr), dtype=np.float32)
    buf = io.BytesIO()
    sf.write(buf, np.concatenate([pad, x, pad]), sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def transcribe(stt_url: str, path: Path) -> str | None:
    try:
        raw = _post(stt_url.rstrip("/") + "/v1/audio/transcriptions", {"language": "uz"},
                    {"file": (path.name, stt_clip_bytes(path), "audio/wav")}, timeout=300)
        return json.loads(raw.decode("utf-8")).get("text")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"  STT ishlamadi: {exc}", file=sys.stderr)
        return None


def render(args, voice: dict, case_id: str, text: str, out: Path) -> Path:
    fields = {
        "text": text, "language": args.language, "engine": args.engine, "seed": str(args.seed),
        "effect_preset": args.preset, "pause_scale": str(args.pause_scale), "num_step": str(args.steps),
        "guidance_scale": str(args.cfg),
    }
    if args.denoise != "auto":
        fields["denoise"] = "true" if args.denoise == "on" else "false"
    if args.max_chunk_chars is not None:
        fields["max_chunk_chars"] = str(args.max_chunk_chars)
    if args.speed is not None:
        fields["speed"] = str(args.speed)
    files: dict[str, tuple[str, bytes, str]] = {}
    if voice.get("profile_id"):
        fields["profile_id"] = voice["profile_id"]
    elif voice.get("instruct"):
        fields["instruct"] = voice["instruct"]  # voice design: the engine's tag set, no reference
    else:
        fields["ref_text"] = voice["ref_text"]
        files["ref_audio"] = (Path(voice["ref_audio"]).name, Path(voice["ref_audio"]).read_bytes(), "audio/wav")
    audio = _post(args.backend.rstrip("/") + "/generate", fields, files, timeout=900)
    path = out / f"{case_id}.wav"
    path.write_bytes(audio)
    return path


def summarize(rows: list[dict]) -> dict:
    """Mean of each numeric metric across a voice's cases (None-safe)."""
    keys = [k for k in SUMMARY_COLUMNS if k != "duration_s"]
    out = {}
    for key in keys:
        values = [r["metrics"][key] for r in rows if r["metrics"].get(key) is not None]
        out[key] = round(sum(values) / len(values), 3) if values else None
    cers = [r["cer"] for r in rows if r.get("cer") is not None]
    out["cer_mean"] = round(sum(cers) / len(cers), 4) if cers else None
    return out


def write_report(out: Path, report: dict, baseline: dict | None) -> None:
    s = report["settings"]
    title = f"# Voice bench — {s['preset']} / pause {s['pause_scale']} / steps {s['steps']} / denoise {s['denoise']}"
    lines = [title, ""]
    header = "| case | s | LUFS | LRA | crest | pauses | pause s | F0 Hz | F0 st | tilt | CER | heard |"
    for name, voice in report["voices"].items():
        lines += [f"## {name}", "", header, "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in voice["cases"]:
            m = r["metrics"]
            cer = "—" if r.get("cer") is None else f"{r['cer']:.0%}"
            heard = (r.get("transcript") or "")[:60].replace("|", "/")
            lines.append(f"| {r['case']} | {m['duration_s']} | {m['lufs']} | {m['lra_lu']} | {m['crest_db']} | "
                         f"{m['pauses']} | {m['pause_mean_s']} | {m['f0_median_hz']} | {m['f0_std_st']} | "
                         f"{m['tilt_db']} | {cer} | {heard} |")
        lines += ["", "**Mean:** " + ", ".join(f"{k} {v}" for k, v in voice["summary"].items() if v is not None)]
        if baseline and name in baseline.get("voices", {}):
            base = baseline["voices"][name]["summary"]
            deltas = []
            for k, v in voice["summary"].items():
                if v is not None and base.get(k) is not None:
                    deltas.append(f"{k} {v - base[k]:+.3f}")
            lines += ["", "**Δ vs baseline:** " + ", ".join(deltas)]
        lines.append("")
    lines += ["Metrics are proxies (dynamics, pauses, melody, spectrum), not a naturalness score.",
              "Listen to every file before deciding: robotic, ringing or breathless takes fail regardless of the numbers.", ""]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


def rescore(out: Path, stt_url: str) -> int:
    """Measure the CER of an existing run again with the trimmed, padded clips."""
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    check = {case_id: check_cer for case_id, _, check_cer in CASES}
    for name, voice in report["voices"].items():
        print(f"\n== {name}")
        for r in voice["cases"]:
            path = Path(r["file"])
            if not path.is_file() or not check.get(r["case"], True):
                continue
            transcript = transcribe(stt_url, path)
            r["transcript"] = transcript
            r["cer"] = vi.cer(vi.ascii_apostrophes(r["text"]), transcript) if transcript else None
            print(f"  {r['case']:<14} CER {r['cer']:.1%}  {(transcript or '')[:70]}" if r["cer"] is not None
                  else f"  {r['case']:<14} STT yo'q")
        voice["summary"] = summarize(voice["cases"])
    write_report(out, report, None)
    print(f"\nHisobot: {out / 'report.md'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--voice", action="append", default=[], help="profile id (repeatable)")
    parser.add_argument("--ref-audio", type=Path, help="reference WAV instead of a profile")
    parser.add_argument("--ref-text", help="exact transcript of --ref-audio")
    parser.add_argument("--design", action="append", default=[], metavar="NAME=INSTRUCT",
                        help="voice-design voice, e.g. 'diktor=female, middle-aged, moderate pitch' (repeatable)")
    parser.add_argument("--out", type=Path, help="output folder (created)")
    parser.add_argument("--baseline", type=Path, help="an earlier --out folder to diff against")
    parser.add_argument("--compare", type=Path, help="only diff --out against --baseline, render nothing")
    parser.add_argument("--rescore", type=Path, metavar="OUT",
                        help="re-transcribe a finished run's takes (trimmed, padded) and rewrite its CER; render nothing")
    parser.add_argument("--cases", default="all", help="comma-separated case ids, default all")
    parser.add_argument("--preset", default="natural", help="effect preset: natural | broadcast | raw | …")
    parser.add_argument("--pause-scale", type=float, default=1.6)
    parser.add_argument("--steps", type=int, default=32)
    parser.add_argument("--cfg", type=float, default=2.0)
    parser.add_argument("--denoise", choices=("auto", "on", "off"), default="auto")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-chunk-chars", type=int,
                        help="engine call size in characters (backend default 800); ~140 renders sentence by sentence")
    parser.add_argument("--speed", type=float, help="speaking-rate factor (backend default 1.0); below 1 gives more time")
    parser.add_argument("--language", default="Uzbek")
    parser.add_argument("--engine", default="omnivoice")
    parser.add_argument("--backend", default=os.environ.get("SADO_URL", "http://127.0.0.1:3900"))
    parser.add_argument("--stt", default=os.environ.get("UZ_STT_URL", "http://127.0.0.1:3910"))
    parser.add_argument("--no-stt", action="store_true")
    args = parser.parse_args(argv)
    if args.rescore:
        return rescore(args.rescore, args.stt)
    if args.out is None:
        parser.error("--out is required")

    baseline = None
    if args.baseline:
        baseline = json.loads((args.baseline / "report.json").read_text(encoding="utf-8"))
    if args.compare:
        if baseline is None:
            parser.error("--compare needs --baseline")
        report = json.loads((args.compare / "report.json").read_text(encoding="utf-8"))
        write_report(args.compare, report, baseline)
        print((args.compare / "report.md").read_text(encoding="utf-8"))
        return 0

    voices = [{"name": v, "profile_id": v} for v in args.voice]
    for spec in args.design:
        name, _, instruct = spec.partition("=")
        if not instruct.strip():
            parser.error(f"--design expects NAME=INSTRUCT, got {spec!r}")
        voices.append({"name": name.strip(), "instruct": instruct.strip()})
    if args.ref_audio:
        if not args.ref_text:
            parser.error("--ref-text is required with --ref-audio")
        voices.append({"name": args.ref_audio.stem, "ref_audio": str(args.ref_audio), "ref_text": args.ref_text})
    if not voices:
        parser.error("name at least one --voice, --design or a --ref-audio/--ref-text pair")
    wanted = None if args.cases == "all" else set(args.cases.split(","))
    cases = [c for c in CASES if wanted is None or c[0] in wanted]
    args.out.mkdir(parents=True, exist_ok=True)

    report = {"settings": {"preset": args.preset, "pause_scale": args.pause_scale, "steps": args.steps,
                           "cfg": args.cfg, "denoise": args.denoise, "seed": args.seed, "engine": args.engine,
                           "max_chunk_chars": args.max_chunk_chars, "speed": args.speed},
              "voices": {}}
    for voice in voices:
        vdir = args.out / vi.slug(voice["name"])
        vdir.mkdir(parents=True, exist_ok=True)
        rows = []
        print(f"\n== {voice['name']}")
        for case_id, text, check_cer in cases:
            try:
                path = render(args, voice, case_id, text, vdir)
            except urllib.error.HTTPError as exc:
                print(f"  {case_id}: backend {exc.code}: {exc.read().decode('utf-8', 'replace')[:200]}", file=sys.stderr)
                continue
            except urllib.error.URLError as exc:
                print(f"Sado backend'ga ulanib bo'lmadi ({args.backend}): {exc.reason}", file=sys.stderr)
                return 1
            metrics = analyze_file(str(path)).to_dict()
            transcript = None if args.no_stt else transcribe(args.stt, path)
            cer = vi.cer(vi.ascii_apostrophes(text), transcript) if (transcript and check_cer) else None
            rows.append({"case": case_id, "text": text, "file": str(path), "metrics": metrics,
                         "transcript": transcript, "cer": cer})
            print(f"  {case_id:<14} {metrics['duration_s']:>5.1f}s  LRA {metrics['lra_lu']}  pauses {metrics['pauses']}"
                  f" ({metrics['pause_mean_s']}s)  F0 {metrics['f0_median_hz']} Hz ±{metrics['f0_std_st']} st"
                  f"  tilt {metrics['tilt_db']} dB" + (f"  CER {cer:.0%}" if cer is not None else ""))
        report["voices"][voice["name"]] = {"cases": rows, "summary": summarize(rows)}
    write_report(args.out, report, baseline)
    print(f"\nHisobot: {args.out / 'report.md'}")
    print("Endi eshiting — raqamlar tabiiylikni emas, faqat yo'nalishni ko'rsatadi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
