#!/usr/bin/env python3
"""Human-likeness scorecard for voice_bench runs: how far is each take from the person?

    uv run python scripts/human_likeness.py --profile da62a368 \\
        --run "Sado Pro=D:/bench/2026-11-12/omnivoice" --run "Navoiy=D:/bench/2026-11-12/navoiy" \\
        --out D:/bench/2026-11-12/scorecard

``voice_bench.py`` measures each take on its own (loudness, pauses, pitch,
CER). This script measures each take *against the human reference recording*
the voice was cloned from, with the proxies that track what listeners hear
once CER is already near zero:

* speaker similarity — ECAPA-TDNN embedding cosine between the take and the
  reference (``speechbrain/spkrec-ecapa-voxceleb``; 1.0 = same voice),
* voicing texture — harmonics-to-noise ratio, cepstral peak prominence and pitch
  micro-variation of the take minus the reference (buzz, over-smoothing, flatness),
* prosody distance — pitch median (semitones), pitch spread, pause length and
  loudness range of the take minus the reference,
* pronunciation — the CER the bench already has, plus the word confusions the
  local STT heard (``xo'jayli`` → ``hojayli`` …), so a fix can target words.

Nothing is downloaded by default (similarity = MFCC signature); ``--with-models``
fetches the ECAPA speaker embedding from Hugging Face once (~80 MB). The
output folder gets ``scorecard.json``, ``scorecard.md`` and ``listen.html`` — a
page with the reference and every run's take side by side, and a 1–5 rating
sheet (pronunciation, intonation, pauses, timbre, artefacts) whose answers
export as JSON. Numbers rank; the ear decides.
"""
from __future__ import annotations

import argparse
import difflib
import html
import json
import math
import re
import shutil
import sys
import urllib.request
from dataclasses import asdict, is_dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from services.speech_metrics import analyze_file  # noqa: E402

ASPECTS = [("talaffuz", "Talaffuz"), ("ohang", "Ohang / urg'u"), ("pauza", "Pauzalar"),
           ("tembr", "Tembr o'xshashligi"), ("artefakt", "Artefaktsiz")]


def metrics_dict(path: Path) -> dict:
    m = analyze_file(str(path))
    return asdict(m) if is_dataclass(m) else dict(m)


def load_16k(path: Path):
    import torch
    import torchaudio

    wav, sr = torchaudio.load(str(path))
    if wav.shape[0] > 1:
        wav = wav.mean(dim=0, keepdim=True)
    if sr != 16000:
        wav = torchaudio.functional.resample(wav, sr, 16000)
    return wav.to(torch.float32)


def mfcc_signature(path: Path):
    """Timbre signature without any downloaded model: mean and spread of 20 MFCCs
    over voiced frames, as one unit vector. Coarser than a speaker-verification
    embedding, but it needs nothing from the network and ranks takes of the same
    text consistently."""
    import torch
    import torchaudio

    wav = load_16k(path)
    mfcc = torchaudio.transforms.MFCC(
        sample_rate=16000, n_mfcc=20,
        melkwargs={"n_fft": 400, "hop_length": 160, "n_mels": 64},
    )(wav)[0]  # (20, frames)
    energy = wav[0].unfold(0, 400, 160).pow(2).mean(dim=1)
    frames = min(energy.shape[0], mfcc.shape[1])
    keep = energy[:frames] > energy[:frames].max() * 0.01
    voiced = mfcc[:, :frames][:, keep] if keep.sum() > 10 else mfcc[:, :frames]
    sig = torch.cat([voiced[1:].mean(dim=1), voiced[1:].std(dim=1)])
    return torch.nn.functional.normalize(sig, dim=0)


class Models:
    """Scorers. By default everything is computed locally with no download;
    ``--with-models`` adds the ECAPA speaker-verification embedding (Hugging
    Face, speechbrain/spkrec-ecapa-voxceleb, ~80 MB) for a sharper similarity."""

    def __init__(self, cache: Path, with_models: bool) -> None:
        self.cache = cache
        self.with_models = with_models
        self._ecapa = None
        self.notes: list[str] = []
        if not with_models:
            self.notes.append("o'xshashlik = MFCC imzo (yuklanmagan); --with-models ECAPA ni qo'shadi")

    def ecapa(self):
        if not self.with_models:
            return None
        if self._ecapa is None:
            try:
                from speechbrain.inference.speaker import EncoderClassifier

                self._ecapa = EncoderClassifier.from_hparams(
                    source="speechbrain/spkrec-ecapa-voxceleb",
                    savedir=str(self.cache / "spkrec-ecapa-voxceleb"),
                    run_opts={"device": "cpu"},
                )
            except Exception as error:  # noqa: BLE001
                self.notes.append(f"ECAPA unavailable, MFCC signature used: {error}")
                self._ecapa = False
        return self._ecapa or None

    def embed(self, path: Path):
        model = self.ecapa()
        if model is None:
            return mfcc_signature(path)
        import torch

        with torch.no_grad():
            emb = model.encode_batch(load_16k(path))
        return torch.nn.functional.normalize(emb.squeeze(0).squeeze(0), dim=0)

    def texture(self, path: Path) -> dict:
        """Voicing texture the ear reads as natural or synthetic: harmonics-to-noise
        ratio, cepstral peak prominence and pitch micro-variation. Reported as
        deltas against the reference recording, not as an absolute score."""
        m = metrics_dict(path)
        return {"hnr_db": m.get("hnr_db"), "cpp_db": m.get("cpp_db"), "f0_micro_st": m.get("f0_micro_st")}


def similarity(a, b) -> float | None:
    if a is None or b is None:
        return None
    return round(float((a * b).sum()), 3)


def semitones(f_take: float | None, f_ref: float | None) -> float | None:
    if not f_take or not f_ref:
        return None
    return round(12 * math.log2(f_take / f_ref), 2)


def delta(a: float | None, b: float | None, digits: int = 2) -> float | None:
    if a is None or b is None:
        return None
    return round(a - b, digits)


WORD = re.compile(r"[^\W\d_]+(?:['’ʻʼ`][^\W\d_]+)*", re.UNICODE)


def confusions(text: str, transcript: str | None) -> list[tuple[str, str]]:
    """Word pairs where the STT heard something else than what was written."""
    if not transcript:
        return []
    want = [w.lower() for w in WORD.findall(text)]
    heard = [w.lower() for w in WORD.findall(transcript)]
    pairs: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=want, b=heard, autojunk=False).get_opcodes():
        if tag == "replace":
            pairs.append((" ".join(want[i1:i2]), " ".join(heard[j1:j2])))
        elif tag == "delete":
            pairs.append((" ".join(want[i1:i2]), "∅"))
        elif tag == "insert":
            pairs.append(("∅", " ".join(heard[j1:j2])))
    return pairs


def fetch_reference(backend: str, profile: str, out: Path) -> tuple[Path, str | None]:
    base = backend.rstrip("/")
    with urllib.request.urlopen(f"{base}/profiles/{profile}", timeout=30) as resp:
        info = json.load(resp)
    with urllib.request.urlopen(f"{base}/profiles/{profile}/audio", timeout=60) as resp:
        data = resp.read()
    path = out / "reference.wav"
    path.write_bytes(data)
    return path, info.get("ref_text") or info.get("reference_text")


def mean(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def build_page(out: Path, reference: Path, runs: list[dict], ref_metrics: dict) -> None:
    def audio(src: str) -> str:
        return f'<audio controls preload="none" src="{html.escape(src)}"></audio>'

    def num(v, suffix: str = "") -> str:
        return "—" if v is None else f"{v}{suffix}"

    cases = {}
    for run in runs:
        for row in run["rows"]:
            cases.setdefault(row["case"], row["text"])
    head = """<!doctype html><html lang="uz"><meta charset="utf-8"><title>Odamga o'xshashlik — tinglash varag'i</title>
<style>body{font:14px/1.5 system-ui,sans-serif;margin:24px;max-width:1200px;color:#111}h1{font-size:20px}
table{border-collapse:collapse;width:100%;margin:12px 0 28px}th,td{border-top:1px solid #ddd;padding:8px;vertical-align:top;text-align:left}
th{background:#f4f4f6;font-weight:600}.text{color:#333;max-width:360px}.m{font:12px/1.4 ui-monospace,monospace;color:#555;white-space:nowrap}
audio{width:260px;display:block}select{margin:2px 4px 2px 0}.ref{background:#f0f4ff;padding:12px;border-radius:8px}
textarea{width:100%;min-height:40px}button{padding:8px 14px;font-size:14px}.conf{color:#a33;font-size:12px}</style>
<body><h1>Odamga o'xshashlik — tinglash varag'i</h1>"""
    parts = [head, '<div class="ref"><b>Inson yozuvi (referens)</b> ', audio(reference.name),
             f'<div class="m">F0 {num(ref_metrics.get("f0_median_hz"), " Hz")} ±{num(ref_metrics.get("f0_std_st"), " st")} · '
             f'LRA {num(ref_metrics.get("lra_lu"), " LU")} · pauza {num(ref_metrics.get("pause_mean_s"), " s")}</div></div>',
             "<p>Har bir ustun bitta tizim. Har take uchun 1 (yomon) – 5 (odamdek) baho bering, so'ng pastdagi tugma bilan JSON eksport qiling.</p>"]
    for case, text in cases.items():
        parts.append(f'<table><tr><th class="text">{html.escape(case)}</th>' +
                     "".join(f"<th>{html.escape(run['name'])}</th>" for run in runs) + "</tr><tr>")
        parts.append(f'<td class="text">{html.escape(text)}</td>')
        for run in runs:
            row = next((r for r in run["rows"] if r["case"] == case), None)
            if row is None:
                parts.append("<td>—</td>")
                continue
            conf = ", ".join(f"{a}→{b}" for a, b in row["confusions"][:6])
            selects = "".join(
                f'<label>{label} <select data-run="{html.escape(run["name"])}" data-case="{html.escape(case)}" data-aspect="{key}">'
                + "".join(f'<option value="{i}">{i}</option>' for i in range(5, 0, -1)) + "</select></label>"
                for key, label in ASPECTS)
            src = f"{run['slug']}/{case}.wav"
            parts.append(
                f'<td>{audio(src)}'
                f'<div class="m">o\'xshashlik {num(row["sim"])} · CER {num(row["cer_pct"], "%")} · ΔHNR {num(row["d_hnr"], " dB")} · ΔCPP {num(row["d_cpp"], " dB")}<br>'
                f'ΔF0 {num(row["d_f0_st"], " st")} · ΔF0 yoyilma {num(row["d_f0_std"], " st")} · Δpauza {num(row["d_pause_s"], " s")} · ΔLRA {num(row["d_lra"], " LU")}</div>'
                + (f'<div class="conf">STT: {html.escape(conf)}</div>' if conf else "")
                + f'<div>{selects}</div>'
                f'<textarea data-run="{html.escape(run["name"])}" data-case="{html.escape(case)}" placeholder="Izoh"></textarea></td>')
        parts.append("</tr></table>")
    parts.append("""<button id="export">Baholarni JSON qilib saqlash</button>
<script>document.getElementById('export').onclick=()=>{const rows=[];document.querySelectorAll('select').forEach(s=>rows.push({run:s.dataset.run,case:s.dataset.case,aspect:s.dataset.aspect,score:Number(s.value)}));
document.querySelectorAll('textarea').forEach(t=>{if(t.value.trim())rows.push({run:t.dataset.run,case:t.dataset.case,note:t.value.trim()})});
const blob=new Blob([JSON.stringify(rows,null,1)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='baholar.json';a.click();};</script></body></html>""")
    (out / "listen.html").write_text("\n".join(parts), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", action="append", required=True, metavar="NAME=DIR",
                        help="a voice_bench --out folder (repeatable)")
    parser.add_argument("--profile", help="profile id whose reference recording is the human")
    parser.add_argument("--ref-audio", type=Path, help="reference WAV instead of --profile")
    parser.add_argument("--backend", default="http://127.0.0.1:3900")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--models", type=Path, default=Path("D:/Cache/human-likeness"),
                        help="download cache for the scorer models")
    parser.add_argument("--with-models", action="store_true",
                        help="download and use the ECAPA speaker embedding (Hugging Face, ~80 MB)")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.ref_audio:
        reference = args.out / "reference.wav"
        shutil.copyfile(args.ref_audio, reference)
    elif args.profile:
        reference, _ = fetch_reference(args.backend, args.profile, args.out)
    else:
        parser.error("give --profile or --ref-audio")

    models = Models(args.models, args.with_models)
    ref_metrics = metrics_dict(reference)
    ref_embedding = models.embed(reference)
    ref_texture = models.texture(reference)
    runs = []
    for spec in args.run:
        name, _, folder = spec.partition("=")
        folder_path = Path(folder)
        reports = list(folder_path.rglob("report.json"))
        if not reports:
            parser.error(f"{folder}: no report.json (a voice_bench --out folder?)")
        report = json.loads(reports[0].read_text(encoding="utf-8"))
        voice_dir = reports[0].parent
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        (args.out / slug).mkdir(exist_ok=True)
        rows = []
        voices = report.get("voices") or {"": report}
        if isinstance(voices, list):
            voices = {voice.get("slug", str(index)): voice for index, voice in enumerate(voices)}
        for voice_slug, voice in voices.items():
            for item in voice.get("cases") or voice.get("rows") or []:
                case = item.get("case") or item.get("id")
                wav = Path(item["file"]) if item.get("file") else voice_dir / voice_slug / f"{case}.wav"
                if not wav.is_file():
                    wav = next(voice_dir.rglob(f"{case}.wav"), None)
                if wav is None:
                    continue
                shutil.copyfile(wav, args.out / slug / f"{case}.wav")
                m = item.get("metrics") or metrics_dict(wav)
                cer = item.get("cer")
                rows.append({
                    "case": case, "text": item.get("text", ""),
                    "sim": similarity(models.embed(wav), ref_embedding),
                    "d_hnr": delta(m.get("hnr_db"), ref_texture.get("hnr_db"), 1),
                    "d_cpp": delta(m.get("cpp_db"), ref_texture.get("cpp_db"), 1),
                    "d_micro": delta(m.get("f0_micro_st"), ref_texture.get("f0_micro_st"), 2),
                    "cer_pct": None if cer is None else round(cer * 100, 1),
                    "d_f0_st": semitones(m.get("f0_median_hz"), ref_metrics.get("f0_median_hz")),
                    "d_f0_std": delta(m.get("f0_std_st"), ref_metrics.get("f0_std_st")),
                    "d_pause_s": delta(m.get("pause_mean_s"), ref_metrics.get("pause_mean_s")),
                    "d_lra": delta(m.get("lra_lu"), ref_metrics.get("lra_lu")),
                    "confusions": confusions(item.get("text", ""), item.get("transcript")),
                })
                print(f"  {name:<10} {case:<14} sim {rows[-1]['sim']}  ΔHNR {rows[-1]['d_hnr']}  ΔCPP {rows[-1]['d_cpp']}  CER {rows[-1]['cer_pct']}%")
        summary = {key: mean([r[key] for r in rows]) for key in ("sim", "cer_pct", "d_f0_st", "d_f0_std", "d_pause_s", "d_lra", "d_hnr", "d_cpp", "d_micro")}
        summary["abs_d_f0_st"] = mean([abs(r["d_f0_st"]) for r in rows if r["d_f0_st"] is not None])
        runs.append({"name": name, "slug": slug, "source": str(folder_path), "rows": rows, "summary": summary})

    scorecard = {"reference": {"path": str(reference), "metrics": ref_metrics, "texture": ref_texture},
                 "runs": runs, "notes": models.notes}
    (args.out / "scorecard.json").write_text(json.dumps(scorecard, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["# Odamga o'xshashlik", "",
             f"Referens: `{reference.name}` — F0 {ref_metrics.get('f0_median_hz')} Hz, LRA {ref_metrics.get('lra_lu')} LU, pauza {ref_metrics.get('pause_mean_s')} s, HNR {ref_texture.get('hnr_db')} dB, CPP {ref_texture.get('cpp_db')} dB", "",
             "Δ = take − referens; nolga yaqin = odamga yaqin.", "",
             "| Tizim | O'xshashlik (1=o'zi) | CER % | \\|ΔF0\\| st | ΔF0 yoyilma st | Δpauza s | ΔLRA LU | ΔHNR dB | ΔCPP dB | Δmikro st |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for run in runs:
        s = run["summary"]
        lines.append(f"| {run['name']} | {s['sim']} | {s['cer_pct']} | {s['abs_d_f0_st']} | {s['d_f0_std']} | {s['d_pause_s']} | {s['d_lra']} | {s['d_hnr']} | {s['d_cpp']} | {s['d_micro']} |")
    lines += ["", "## Eng ko'p STT chalkashuvlari", ""]
    for run in runs:
        counter: dict[tuple[str, str], int] = {}
        for row in run["rows"]:
            for pair in row["confusions"]:
                counter[pair] = counter.get(pair, 0) + 1
        top = sorted(counter.items(), key=lambda kv: -kv[1])[:12]
        lines.append(f"- **{run['name']}**: " + (", ".join(f"{a}→{b}" + (f" ×{n}" if n > 1 else "") for (a, b), n in top) or "yo'q"))
    if models.notes:
        lines += ["", "Eslatmalar: " + "; ".join(models.notes)]
    (args.out / "scorecard.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    build_page(args.out, reference, runs, ref_metrics)
    print(f"\nScorecard: {args.out / 'scorecard.md'}\nTinglash: {args.out / 'listen.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
