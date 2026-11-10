#!/usr/bin/env python3
"""Add a human-recorded voice to Sado, checked against the owner's rules.

    uv run python scripts/voice_intake.py REC.wav --name Dilnoza --gender ayol \
        --age 34 --region "Toshkent" --ref-text-file ref.txt \
        --source own --consent [--install] [--check]

Steps, in order, each reported:

1. decode the recording (any container ffmpeg reads) and measure it: duration,
   sample rate, clipping, pauses, noise floor, BS.1770 loudness;
2. master it: mono, linear gain to −16 LUFS held under a −3 dBFS peak, edges
   trimmed to 0.25 s, written as 16-bit WAV named ``<ism>_<til>_<jins>.wav``
   next to ``<slug>.ref.txt`` and ``<slug>.json`` (the metadata);
3. transcribe it with the local Uzbek STT (``--stt``) and compare with the
   reference text (CER);
4. ``--install``: create the voice profile in the running Sado backend;
5. ``--check``: generate one Uzbek sentence with the new voice, save it next to
   the metadata and transcribe it — then *listen* before calling it accepted.

Exit status 1 when a rule fails; ``--force`` installs anyway (the report
still records the failures). Nothing leaves the machine: the backend and the
STT are local HTTP services.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import soundfile as sf
from services import voice_intake as vi
from services.ffmpeg_utils import find_ffmpeg

CHECK_SENTENCE = (
    "Assalomu alaykum! Bu Sado uchun yangi ovoz sinovi: men hikoya o'qiyman, "
    "yangilik aytaman yoki do'stona suhbat quraman."
)


def _multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
    for name, (filename, data, mime) in files.items():
        body += (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode() + data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def _post(url: str, fields: dict[str, str], files: dict[str, tuple[str, bytes, str]], timeout: int):
    body, content_type = _multipart(fields, files)
    request = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": content_type})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.headers.get("Content-Type", ""), response.read()


def transcribe(stt_url: str, path: Path) -> str | None:
    try:
        _, raw = _post(stt_url.rstrip("/") + "/v1/audio/transcriptions", {"language": "uz"},
                       {"file": (path.name, path.read_bytes(), "audio/wav")}, timeout=300)
        return json.loads(raw.decode("utf-8")).get("text")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"  STT ishlamadi: {exc}", file=sys.stderr)
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="recording: wav/flac/ogg/m4a/mp3 …")
    parser.add_argument("--name", required=True, help="voice name shown in Sado")
    parser.add_argument("--gender", required=True, choices=sorted(vi.GENDERS), help="erkak | ayol")
    parser.add_argument("--age", type=int, help="speaker's age")
    parser.add_argument("--region", default="", help="dialect / region, e.g. Toshkent, Farg'ona")
    parser.add_argument("--language", default="uz", help="ISO code, default uz")
    text = parser.add_mutually_exclusive_group(required=True)
    text.add_argument("--ref-text", help="exactly what is said")
    text.add_argument("--ref-text-file", type=Path, help="file holding exactly what is said")
    parser.add_argument("--source", required=True, choices=vi.SOURCES, help="where the recording comes from")
    parser.add_argument("--license", default="", help="licence of an open source (CC0, CC-BY-4.0 …)")
    parser.add_argument("--consent", action="store_true", help="the speaker agreed to this use")
    parser.add_argument("--out", type=Path, help="output folder (default: <data dir>/voice_intake/<slug>)")
    parser.add_argument("--backend", default=os.environ.get("SADO_URL", "http://127.0.0.1:3900"))
    parser.add_argument("--stt", default=os.environ.get("UZ_STT_URL", "http://127.0.0.1:3910"))
    parser.add_argument("--no-stt", action="store_true", help="skip the transcript check")
    parser.add_argument("--install", action="store_true", help="create the profile in Sado")
    parser.add_argument("--check", action="store_true", help="generate a test sentence with the new voice")
    parser.add_argument("--engine", default="omnivoice", help="engine for --check (omnivoice, navoiy …)")
    parser.add_argument("--force", action="store_true", help="install even when a rule fails")
    args = parser.parse_args(argv)

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        print("ffmpeg topilmadi", file=sys.stderr)
        return 2
    ref_text = (args.ref_text_file.read_text(encoding="utf-8") if args.ref_text_file else args.ref_text).strip()
    gender = vi.GENDERS[args.gender]
    stem = f"{vi.slug(args.name)}_{args.language}_{gender}"
    if args.out is None:
        from core.config import DATA_DIR
        args.out = Path(DATA_DIR) / "voice_intake" / stem
    args.out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        decoded = Path(tmp) / "decoded.wav"
        vi.decode(ffmpeg, args.input, decoded)
        samples, sample_rate = sf.read(str(decoded), dtype="float32", always_2d=True)
        analysis = vi.analyze(samples, sample_rate)
        measured = vi.measure_lufs(ffmpeg, decoded)
        mastered = vi.normalize(
            vi.to_mono(samples), sample_rate,
            measured.input_i if measured else analysis.peak_dbfs - 13.0, analysis,
        )
        output = args.out / f"{stem}.wav"
        vi.write_pcm16(output, mastered.samples, sample_rate)
        remeasured = vi.measure_lufs(ffmpeg, output)

    clean_text = vi.ascii_apostrophes(ref_text)
    (args.out / f"{stem}.ref.txt").write_text(clean_text + "\n", encoding="utf-8")
    transcript = None if args.no_stt else transcribe(args.stt, output)
    speech_s = max(analysis.speech_seconds, 0.1)
    report = vi.IntakeReport(
        name=args.name, language=args.language, gender=gender, age=args.age, region=args.region,
        ref_text=ref_text, source=args.source, license=args.license, consent=args.consent,
        input_file=str(args.input), output_file=str(output), analysis=analysis,
        measured_lufs=measured.input_i if measured else None,
        measured_true_peak=measured.input_tp if measured else None,
        output_lufs=remeasured.input_i if remeasured else None,
        output_peak_dbfs=vi._db(float(abs(mastered.samples).max())) if len(mastered.samples) else -120.0,
        gain_db=mastered.gain_db, peak_limited=mastered.peak_limited,
        words=vi.count_words(clean_text), syllables=vi.count_syllables(clean_text),
        words_per_second=vi.count_words(clean_text) / speech_s,
        syllables_per_second=vi.count_syllables(clean_text) / speech_s,
        transcript=transcript, cer=None if transcript is None else vi.cer(clean_text, transcript),
    )
    report.ref_text = clean_text
    vi.judge(report)
    report.write(args.out / f"{stem}.json")
    _print(report, output)

    if report.failures and not args.force:
        return 1

    profile_id = None
    try:
        if args.install:
            _, raw = _post(
                args.backend.rstrip("/") + "/profiles",
                {"name": args.name, "ref_text": clean_text,
                 "language": "Uzbek" if args.language == "uz" else args.language, "kind": "clone"},
                {"ref_audio": (output.name, output.read_bytes(), "audio/wav")}, timeout=600,
            )
            profile = json.loads(raw.decode("utf-8"))
            profile_id = profile.get("id") or profile.get("profile_id")
            print(f"\nProfil yaratildi: {args.name} (id {profile_id})")
        if not args.check:
            return 0

        # Listen before you install: without --install the mastered clip itself
        # is the reference, so the test sentence costs no profile.
        fields = {"text": CHECK_SENTENCE, "language": "Uzbek", "engine": args.engine}
        files: dict[str, tuple[str, bytes, str]] = {}
        if profile_id is not None:
            fields["profile_id"] = str(profile_id)
        else:
            fields["ref_text"] = clean_text
            files["ref_audio"] = (output.name, output.read_bytes(), "audio/wav")
        _, audio = _post(args.backend.rstrip("/") + "/generate", fields, files, timeout=900)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        print(f"Sado backend {exc.code} qaytardi: {detail}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Sado backend'ga ulanib bo'lmadi ({args.backend}): {exc.reason}", file=sys.stderr)
        return 1
    check = args.out / f"{stem}_check_{args.engine}.wav"
    check.write_bytes(audio)
    verdict = ""
    if not args.no_stt:
        heard = transcribe(args.stt, check)
        if heard is not None:
            verdict = f" — STT CER {vi.cer(CHECK_SENTENCE, heard):.0%}: {heard}"
    print(f"Sinov namunasi: {check}{verdict}")
    print("Endi eshiting: robotik, jarangli yoki nafassiz bo'lsa — qabul qilmang.")
    return 0


def _print(report: vi.IntakeReport, output: Path) -> None:
    a = report.analysis
    rows = [
        ("Fayl", output.name),
        ("Davomiylik", f"{a.duration_s:.1f} s (nutq {a.speech_seconds:.1f} s)"),
        ("Format", f"{a.channels} kanal → mono, {a.sample_rate} Hz, 16-bit"),
        ("Kirish", f"peak {a.peak_dbfs:.1f} dBFS, "
                   + (f"{report.measured_lufs:.1f} LUFS" if report.measured_lufs is not None else "LUFS yo'q")),
        ("Chiqish", f"peak {report.output_peak_dbfs:.1f} dBFS, "
                    + (f"{report.output_lufs:.1f} LUFS" if report.output_lufs is not None else "LUFS yo'q")
                    + f" (gain {report.gain_db:+.1f} dB)"),
        ("Shovqin", f"SNR {a.snr_db:.0f} dB (nutq {a.speech_db:.0f}, fon {a.noise_db:.0f} dBFS)"),
        ("Pauzalar", f"eng uzuni {a.max_internal_gap_s:.2f} s; boshi {a.lead_silence_s:.2f} s, oxiri {a.trail_silence_s:.2f} s"),
        ("Tezlik", f"{report.words_per_second:.1f} so'z/s, {report.syllables_per_second:.1f} bo'g'in/s ({report.words} so'z)"),
        ("STT", "o'tkazilmadi" if report.cer is None else f"CER {report.cer:.0%}: {report.transcript}"),
    ]
    width = max(len(k) for k, _ in rows)
    for key, value in rows:
        print(f"{key:<{width}}  {value}")
    for line in report.failures:
        print(f"  XATO   {line}")
    for line in report.warnings:
        print(f"  OGOH   {line}")
    print("  QULOQ  " + " · ".join(report.manual_checks))
    print("NATIJA:", "qabul qilish mumkin (eshitib tasdiqlang)" if report.accepted else "rad etildi")


if __name__ == "__main__":
    sys.exit(main())
