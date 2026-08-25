---
name: video-to-action
description: Extract actionable steps from YouTube videos using Gemini video understanding. Use when user provides a YouTube link and wants to learn procedures, extract steps, understand visual tutorials, or turn video content into executable instructions.
allowed-tools: Read, Grep, Glob, Bash
---

# Video-to-Action — Learn from YouTube via Gemini

## Goal

Take a YouTube URL → send the video to Gemini → get back structured, actionable steps that Claude can understand and execute. Works for tutorials, demos, how-to, and any procedural video content.

## How It Works

1. **Full mode** (default): downloads video at low res → uploads to Gemini File API → Gemini watches the video and returns structured analysis
2. **Quick mode** (`--quick`): fetches the transcript/captions only → sends to Gemini → faster and cheaper but no visual context
3. **Fallback chain**: If video upload fails → extracts frames every 30s + transcript → sends as images + text

## Usage

```bash
# Default: full visual analysis (visual + audio)
python .claude/skills/video-to-action/video_to_action.py "https://youtube.com/watch?v=VIDEO_ID"

# Ask a specific question about the video
python .claude/skills/video-to-action/video_to_action.py "https://youtu.be/VIDEO_ID" --question "What settings does the author change in step 3?"

# Quick mode: transcript only (no visual context)
python .claude/skills/video-to-action/video_to_action.py "https://youtu.be/VIDEO_ID" --quick

# Save output to a specific file
python .claude/skills/video-to-action/video_to_action.py "https://youtu.be/VIDEO_ID" --output output/steps.md
```

## Requirements

- `GEMINI_API_KEY` environment variable (or in a `.env` file at project root). Never hardcode the key.
- Python packages: `google-genai`, `yt-dlp`, `youtube-transcript-api`, `python-dotenv` (see `requirements.txt`)
- `ffmpeg` on PATH (only needed for the frame-extraction fallback)

## Output

The script prints and saves (default `output/<video_id>_steps.md`) a structured Markdown document:

- **Summary** — what the video builds/teaches
- **Prerequisites** — tools, accounts, files needed
- **Steps** — numbered list; each step has: action, tool/app used, exact values/settings shown on screen, expected result
- **Verification** — how to check the result matches the video

## Claude Workflow

When the user gives a YouTube URL:

1. Run the script (full mode first; fall back to `--quick` if download/upload fails)
2. Read the generated steps file
3. Present the steps to the user and confirm scope before executing anything
4. Execute steps one-by-one with available tools, verifying each against the "expected result"
