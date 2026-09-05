# Source Ingestion

Read this for YouTube sources or when ordinary extraction is insufficient. Set `SKILL_DIR` to the absolute directory containing this skill's `SKILL.md`; run helpers from the session project.

## Documents and Websites

- Text or Markdown: read directly, separating content from metadata.
- PDF: extract text; inspect rendered pages or use OCR if text extraction is unreliable.
- Website: fetch the current body and remove navigation, ads, comments, related links, and other page furniture.

Keep source identity and factual uncertainty in working evidence notes so the evaluator can verify the script.

## YouTube

Try captions first:

```bash
uv run --script "$SKILL_DIR/scripts/fetch_youtube_transcript.py" '<youtube-url-or-video-id>' --format text
```

The helper accepts watch, short, embed, and live URLs. Quote URLs for shell safety. Music cues and lyrics may remain in its output; select relevant source content during preprocessing.

If captions are unavailable or unusable, use local GPU transcription:

```bash
uv run --script "$SKILL_DIR/scripts/transcribe_youtube_gpu.py" '<youtube-url-or-video-id>' --format text
```

The fallback downloads audio with `yt-dlp` and uses `faster-whisper` on CUDA with its default `turbo` model. Preserve the GPU-only contract: if CUDA is unavailable or transcription fails, report the inaccessible source instead of switching to CPU or inventing its content.

Both scripts declare their own dependencies for `uv`. If execution is blocked, report the actual error. Track downloaded audio and transcripts for cleanup after the script passes review.
