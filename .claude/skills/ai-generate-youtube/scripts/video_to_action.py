#!/usr/bin/env python3
"""video_to_action.py — Extract actionable steps from a YouTube video via Gemini.

Modes:
  full  (default) : download low-res video -> upload to Gemini File API -> analyze
  quick (--quick) : transcript only -> Gemini (no visual context)
  fallback        : frames every 30s + transcript -> Gemini (if upload fails)

The Gemini API key is read from the GEMINI_API_KEY environment variable
(a .env file in the current working directory is also loaded). Never hardcode keys.

Bundled with the ai-generate-youtube skill: paths anchor to the CURRENT WORKING
DIRECTORY (not this file's location) so the skill works in any project.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path.cwd()

# ---------------------------------------------------------------- env / client

def load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        env_file = PROJECT_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get_client():
    from google import genai
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("ERROR: GEMINI_API_KEY is not set (env var or .env at project root).")
    return genai.Client(api_key=api_key)


MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

# ---------------------------------------------------------------- youtube utils

def video_id_from_url(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})", url)
    if not m:
        sys.exit(f"ERROR: could not parse a YouTube video id from: {url}")
    return m.group(1)


def download_video(url: str, workdir: Path) -> Path:
    """Download the video at low resolution (<=480p, small file for upload)."""
    out_tmpl = str(workdir / "video.%(ext)s")
    # Try progressively looser format selectors. Merging video+audio needs
    # ffmpeg; without it, end with a VIDEO-ONLY stream — never separate files,
    # which risk uploading the audio track to Gemini by mistake (narration is
    # covered by the transcript instead).
    import shutil as _shutil
    if _shutil.which("ffmpeg"):
        selectors = ["b[height<=480]", "bv*[height<=480]+ba/bv*+ba", "b"]
    else:
        selectors = ["b[height<=480]", "b", "bv*[height<=480]", "bv*"]
    print(f"[full] downloading video (low-res): {url}")
    last_err = None
    for sel in selectors:
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "-f", sel,
            "--no-playlist",
            "-o", out_tmpl,
            url,
        ]
        try:
            subprocess.run(cmd, check=True)
            break
        except subprocess.CalledProcessError as e:
            print(f"[full] format '{sel}' failed, trying next...")
            last_err = e
    else:
        raise last_err
    files = sorted(workdir.glob("video.*"), key=lambda p: p.stat().st_size, reverse=True)
    if not files:
        raise RuntimeError("yt-dlp reported success but no file was produced")
    # Without ffmpeg, video+audio may land as separate files; prefer the video
    # track (mp4) over an audio-only webm/m4a so Gemini gets the visuals.
    mp4s = [f for f in files if f.suffix.lower() == ".mp4"]
    if mp4s:
        files = mp4s
    print(f"[full] downloaded: {files[0].name} ({files[0].stat().st_size / 1e6:.1f} MB)")
    return files[0]


def fetch_transcript(video_id: str) -> str:
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi()
    try:
        fetched = api.fetch(video_id, languages=["en", "vi"])
        snippets = list(fetched)
    except Exception:
        listing = api.list(video_id)
        transcript = next(iter(listing))
        snippets = list(transcript.fetch())
    lines = []
    for s in snippets:
        start = getattr(s, "start", None) or s.get("start", 0)
        text = getattr(s, "text", None) or s.get("text", "")
        mins, secs = divmod(int(start), 60)
        lines.append(f"[{mins:02d}:{secs:02d}] {text}")
    return "\n".join(lines)


def extract_frames(video_path: Path, workdir: Path, every_s: int = 30) -> list:
    frames_dir = workdir / "frames"
    frames_dir.mkdir(exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"fps=1/{every_s},scale=640:-1",
        str(frames_dir / "frame_%04d.jpg"),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return sorted(frames_dir.glob("frame_*.jpg"))

# ---------------------------------------------------------------- prompts

BASE_PROMPT = """You are analyzing a tutorial/how-to video so an AI coding agent (Claude) can \
replicate what the video demonstrates, step by step, using its own tools.

Return a Markdown document with EXACTLY these sections:

# {title}

## Summary
2-4 sentences: what the video builds or teaches, and the end result.

## Prerequisites
Bullet list of tools, apps, accounts, files, and settings required before starting.

## Steps
A numbered list. For EACH step include:
- **Action**: the precise action performed
- **Tool/App**: the application, menu, or command used
- **Values**: exact values, settings, code, or text shown on screen (verbatim where visible)
- **Expected result**: what the screen/state should look like after the step

## Verification
How to confirm the final result matches the video.

Be concrete and exhaustive — capture on-screen values, filenames, menu paths, and \
keyboard shortcuts. If audio and visuals disagree, trust the visuals and note the conflict.
"""


def build_prompt(question: str | None) -> str:
    prompt = BASE_PROMPT.replace("{title}", "Video Action Plan")
    if question:
        prompt += (
            "\n\nADDITIONALLY, answer this specific question in a final section "
            f"'## Question'. Question: {question}"
        )
    return prompt

# ---------------------------------------------------------------- gemini modes

def analyze_full(client, url: str, question: str | None, workdir: Path) -> str:
    video_path = download_video(url, workdir)
    # The uploaded file may be video-only (no ffmpeg to merge audio), so also
    # attach the transcript when available to cover narration.
    transcript_note = ""
    try:
        transcript = fetch_transcript(video_id_from_url(url))
        transcript_note = (
            "\n\nThe video file may lack an audio track. Use this TRANSCRIPT "
            "for narration:\n" + transcript
        )
    except Exception as e:
        print(f"[full] transcript unavailable ({e}); continuing with video only")
    print("[full] uploading to Gemini File API...")
    uploaded = client.files.upload(file=str(video_path))
    while uploaded.state and uploaded.state.name == "PROCESSING":
        print("[full] Gemini is processing the video...")
        time.sleep(5)
        uploaded = client.files.get(name=uploaded.name)
    if uploaded.state and uploaded.state.name == "FAILED":
        raise RuntimeError("Gemini File API failed to process the video")
    print("[full] Gemini is watching the video...")
    resp = client.models.generate_content(
        model=MODEL,
        contents=[uploaded, build_prompt(question) + transcript_note],
    )
    return resp.text


def analyze_quick(client, video_id: str, question: str | None) -> str:
    print("[quick] fetching transcript...")
    transcript = fetch_transcript(video_id)
    print(f"[quick] transcript: {len(transcript)} chars. Sending to Gemini...")
    prompt = (
        build_prompt(question)
        + "\n\nYou only have the TRANSCRIPT (no visuals). Note visual details you "
        "cannot verify.\n\nTRANSCRIPT:\n" + transcript
    )
    resp = client.models.generate_content(model=MODEL, contents=prompt)
    return resp.text


def analyze_fallback(client, url: str, video_id: str, question: str | None, workdir: Path) -> str:
    print("[fallback] frames every 30s + transcript...")
    video_path = download_video(url, workdir)
    frames = extract_frames(video_path, workdir)
    print(f"[fallback] extracted {len(frames)} frames")
    try:
        transcript = fetch_transcript(video_id)
    except Exception as e:
        print(f"[fallback] transcript unavailable: {e}")
        transcript = "(transcript unavailable)"
    parts = []
    for f in frames[:60]:
        parts.append(client.files.upload(file=str(f)))
    parts.append(
        build_prompt(question)
        + "\n\nThe images are frames sampled every 30 seconds, in order.\n\nTRANSCRIPT:\n"
        + transcript
    )
    resp = client.models.generate_content(model=MODEL, contents=parts)
    return resp.text

# ---------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description="Extract actionable steps from a YouTube video via Gemini")
    ap.add_argument("url", help="YouTube video URL")
    ap.add_argument("--quick", action="store_true", help="transcript-only mode (faster, no visuals)")
    ap.add_argument("--question", help="specific question to answer about the video")
    ap.add_argument("--output", help="output markdown path (default: output/<video_id>_steps.md)")
    args = ap.parse_args()

    load_env()
    client = get_client()
    vid = video_id_from_url(args.url)

    out_path = Path(args.output) if args.output else PROJECT_ROOT / "output" / f"{vid}_steps.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    result = None
    if args.quick:
        result = analyze_quick(client, vid, args.question)
    else:
        with tempfile.TemporaryDirectory(prefix="v2a_") as td:
            workdir = Path(td)
            try:
                result = analyze_full(client, args.url, args.question, workdir)
            except Exception as e:
                print(f"[full] failed ({e}); trying fallback (frames + transcript)...")
                try:
                    result = analyze_fallback(client, args.url, vid, args.question, workdir)
                except Exception as e2:
                    print(f"[fallback] failed ({e2}); trying quick mode (transcript only)...")
                    result = analyze_quick(client, vid, args.question)

    out_path.write_text(result, encoding="utf-8")
    print(f"\n=== saved: {out_path} ===\n")
    print(result)


if __name__ == "__main__":
    main()
