---
name: ai-generate-youtube
description: AI learns from YouTube the way a human does — give it a tutorial URL and it has Gemini watch the full video, extracts a structured build plan, then executes every step with its own tools to replicate the tutorial's product end to end. Use this whenever the user shares a YouTube link and wants to learn from it, follow along, build what the video builds, replicate a demo, "làm theo video", "học từ video này", "build sản phẩm như trong video", or turn any procedural/tutorial video into working code, configuration, or actions — even if they never say the words "skill", "extract", or "build".
---

# AI Generate YouTube — Learn from a video, then build what it teaches

## Goal

Reproduce the flow "agents learn from the same medium humans learn from":

> YouTube URL → Claude cannot watch video natively → Gemini watches the full
> video via its API → Gemini returns numbered, structured steps → Claude
> executes each step using its tools → the tutorial's result is replicated.

This skill covers the **whole loop**, not just extraction. The deliverable is
the working product the video teaches, verified — not just a summary of it.

## Requirements

- `GEMINI_API_KEY` in the environment or in a `.env` file in the current
  working directory (never hardcode or commit keys; `.env` must be gitignored).
- Python packages: `google-genai`, `yt-dlp`, `youtube-transcript-api`,
  `python-dotenv`. Install any that are missing before Phase 1.
  On macOS with Homebrew Python, plain `pip3 install` fails with
  `externally-managed-environment` (PEP 668) — create and use a venv instead
  (`python3 -m venv ~/.venvs/ai-generate-youtube && source ~/.venvs/ai-generate-youtube/bin/activate`),
  and launch Claude Code from the activated venv so the script picks it up.
- `ffmpeg` on PATH is optional (enables audio+video merge and the
  frame-extraction fallback; the script works without it).
- Whatever the *build* itself needs (other API keys, packages) is discovered
  from the extracted plan in Phase 2 — confirm those with the user, don't
  assume.

## Environment limits (verified in practice)

- This skill needs a real machine with open network access (Claude Code on
  desktop). The claude.ai cloud sandbox blocks both youtube.com and the Gemini
  API at the infrastructure level (403 policy denial) — if you see that, stop
  and tell the user to run the skill on a local machine; do not try to bypass
  network policy.
- YouTube sometimes blocks transcript fetching per-IP. That is fine: full mode
  still works because Gemini watches the video itself. Only quick mode
  (`--quick`) depends on the transcript.
- Gemini occasionally returns 503 "high demand" — the script now retries
  automatically (3 attempts, 30s apart). If it still fails, wait a minute and
  rerun rather than switching approach.

## Phase 1 — Watch & extract

Run the bundled script (from the skill directory, `scripts/video_to_action.py`):

```bash
python <skill-dir>/scripts/video_to_action.py "<YOUTUBE_URL>"
```

- Default (full) mode downloads the video at low resolution, uploads it to the
  Gemini File API, and has Gemini watch it. This captures on-screen values
  (filenames, settings, UI text, exact commands) that a transcript misses —
  prefer it whenever possible.
- `--quick` uses the transcript only: faster and cheaper, but blind to
  anything shown on screen. Use it only when download/upload keeps failing or
  the user asks for a cheap pass.
- The script already falls back automatically: full → frames+transcript →
  transcript-only. Let it.
- `--question "..."` appends a specific question to answer about the video.
- Output lands in `output/<video_id>_steps.md` in the working directory, with
  sections: Summary, Prerequisites, Steps (each with Action / Tool / Values /
  Expected result), Verification.

If the default Gemini model is rejected (models rotate availability), the
error message names the replacement — set `GEMINI_MODEL` accordingly and
retry rather than editing the script.

## Phase 2 — Review the plan & confirm scope

Read the generated steps file, then present to the user before building:

1. A short summary of what the video builds and the tech stack it uses.
2. The list of steps at one-line-each granularity.
3. Anything the build needs that isn't available yet (API keys, accounts,
   tools) — ask for these now, not mid-build.
4. Any substitution you propose (e.g. the video uses a provider the user has
   no key for, and an equivalent is available). Architecture, file names, and
   endpoints stay faithful to the video; only swap what the user's environment
   forces, and say so explicitly.

Wait for the user's go-ahead. The extraction is cheap; the build is not.

## Phase 3 — Execute the steps

Work through the plan **in order**, one step at a time:

- Follow each step's Values verbatim where the environment allows (file
  names, ports, endpoints, prompts, UI strings) — that fidelity is what makes
  the result recognizably "the thing from the video".
- Videos show one machine; the user's machine differs. When a step fails,
  diagnose and adapt (missing binary, renamed model, version drift) while
  preserving the step's intent, and record the deviation.
- Check each step's **Expected result** before moving on. A step that
  "probably worked" is a step that will fail three steps later.

## Phase 4 — Verify like the video does

Use the plan's Verification section as the acceptance test:

- Actually run the product (servers, UI, scripts) and exercise the same
  end-to-end flow the video demonstrates, with the user's real input where
  they offer it.
- Show evidence: command output, screenshots, HTTP responses — not claims.
- Report deviations from the video and why they were necessary.

## Notes

- Keep secrets in `.env` (gitignored). If the user pastes a key into chat,
  store it, don't echo it, and recommend rotation.
- Save nothing outside the working directory except the user asks.
- Reference implementation built with this flow:
  https://github.com/NguyenMinhQuan-2A202601478/AI_generate_youtube
