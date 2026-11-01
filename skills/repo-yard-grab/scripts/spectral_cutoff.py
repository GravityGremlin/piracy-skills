#!/usr/bin/env python3
"""Spectral cutoff check: is a file's audio ANCESTRY lossless, or a lossy transcode?

Usage:
    python3 spectral_cutoff.py FILE [FILE ...] [--calibrate KNOWN_LOSSLESS] [--json]

Decodes each file to mono f32 @48 kHz via ffmpeg (mp3/opus/flac/m4a/wav all
work — the PCM history is measured, not the container) and prints band
energies relative to the 200 Hz-5 kHz median, plus the -45 dB cutoff.

--calibrate encodes a known-lossless SOURCE to LAME 128k and to the fake
128k->FLAC->opus160 chain, measured in the same run, so verdicts compare
against same-session numbers instead of absolute lore.

Requires: ffmpeg, numpy.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import json as _json

import numpy as np

SR = 48000
NFFT = 8192


def decode(path: str) -> np.ndarray:
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1",
         "-ar", str(SR), "pipe:1"],
        capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed on {path}: {r.stderr.decode()[:200]}")
    return np.frombuffer(r.stdout, dtype=np.float32)


def bands(path: str) -> dict:
    x = decode(path)
    if len(x) < NFFT * 4:
        raise RuntimeError(f"{path}: too short to measure")
    win = np.hanning(NFFT).astype(np.float32)
    hop = NFFT // 2
    frames, rms = [], []
    n = (len(x) - NFFT) // hop
    for i in range(0, n, 2):
        seg = x[i * hop:i * hop + NFFT]
        rms.append(float(np.sqrt(np.mean(seg ** 2))))
        frames.append(np.abs(np.fft.rfft(seg * win)) ** 2)
    frames = np.asarray(frames)
    rms = np.asarray(rms)
    keep = rms >= np.percentile(rms, 50)
    spec = frames[keep].mean(axis=0)
    freqs = np.fft.rfftfreq(NFFT, 1.0 / SR)
    ref = np.median(spec[(freqs >= 200) & (freqs <= 5000)])

    def band(f0, f1):
        return float(np.mean(spec[(freqs >= f0) & (freqs < f1)]))

    def db(e):
        return 10 * np.log10(max(e, 1e-30) / max(ref, 1e-30))

    above = np.where(spec >= ref * 10 ** (-45 / 10))[0]
    return {
        "dur_s": round(len(x) / SR, 1),
        "cutoff_45db_hz": int(freqs[above[-1]]) if len(above) else 0,
        "e12_14k_db": round(db(band(12_000, 14_000)), 1),
        "e15p5_16p5_db": round(db(band(15_500, 16_500)), 1),
        "e17p5_18p5_db": round(db(band(17_500, 18_500)), 1),
        "e19p5_20_db": round(db(band(19_500, 20_000)), 1),
    }


def classify(row: dict, fake_e: float | None) -> str:
    e = row["e17p5_18p5_db"]
    if e <= -80:
        return "lossy ancestry - 128k-class dead wall above ~16 kHz"
    if fake_e is not None and e < -40 and abs(e - fake_e) < 8:
        return "suspect - matches the 128k->FLAC fake-lossless chain"
    if e >= -45:
        return "better-than-128k ancestry - real content to ~20 kHz"
    return "ambiguous - calibrate in-session and compare"


def calibrate(source: str) -> tuple[dict, dict]:
    with tempfile.TemporaryDirectory(prefix="spectral-") as td:
        mp3 = os.path.join(td, "cal128.mp3")
        flac = os.path.join(td, "cal128.flac")
        opus = os.path.join(td, "cal128.opus")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", source,
                        "-c:a", "libmp3lame", "-b:a", "128k", mp3], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mp3, flac], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", flac, "-c:a",
                        "libopus", "-b:a", "160k", "-ac", "2", opus], check=True)
        return bands(mp3), bands(opus)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--calibrate", metavar="KNOWN_LOSSLESS",
                    help="known-lossless source to encode + measure in-session")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    fake_e = None
    out = {"calibration": None, "files": {}}
    if args.calibrate:
        cal_mp3, cal_fake = calibrate(args.calibrate)
        fake_e = cal_fake["e17p5_18p5_db"]
        out["calibration"] = {"lame128": cal_mp3, "fake_chain": cal_fake}
        print(f"== calibration from {args.calibrate}")
        print(f"  LAME 128k:  17.5-18.5k {cal_mp3['e17p5_18p5_db']} dB | cut {cal_mp3['cutoff_45db_hz']} Hz")
        print(f"  fake chain: 17.5-18.5k {cal_fake['e17p5_18p5_db']} dB")
        print()

    rc = 0
    for f in args.files:
        try:
            row = bands(f)
            verdict = classify(row, fake_e)
            out["files"][f] = {"bands": row, "verdict": verdict}
            print(f"{f}")
            print(f"  dur {row['dur_s']}s | cutoff@-45dB {row['cutoff_45db_hz']} Hz")
            print(f"  12-14k {row['e12_14k_db']} dB | 15.5-16.5k {row['e15p5_16p5_db']} dB"
                  f" | 17.5-18.5k {row['e17p5_18p5_db']} dB | 19.5-20k {row['e19p5_20_db']} dB")
            print(f"  -> {verdict}\n")
        except Exception as e:
            print(f"{f}: FAILED: {e}", file=sys.stderr)
            rc = 1
    if args.json:
        print(_json.dumps(out, indent=1))
    return rc


if __name__ == "__main__":
    sys.exit(main())
