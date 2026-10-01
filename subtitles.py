"""
Auto-Subtitles Engine for TikTok / Shorts
Generates high-energy, stylish ASS subtitles from speech using faster-whisper.

Rules:
- Strictly ONE word per subtitle event for viral TikTok / Shorts aesthetic (Hormozi / CapCut style).
- Negative acoustic lead-in (-140ms) to ensure words appear the moment mouth articulates (zero perceived lag).
- Precise timeline compensation for banner pauses (pause_on_banner) so subtitles remain 100% synchronized
  across the entire video after all banner freezes.
- Clean uppercase styling with bold black outline and vibrant highlight colors.
"""
import os
import re
import asyncio
from typing import List, Dict, Any, Optional

FFMPEG_BIN = os.path.join(os.path.dirname(__file__), ".venv", "bin", "ffmpeg")
if not os.path.exists(FFMPEG_BIN):
    FFMPEG_BIN = "ffmpeg"


def format_ass_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


COLOR_PRESETS = {
    # ASS format: &HAABBGGRR
    "yellow": "&H0000F6FF",  # Bright TikTok Gold / Yellow
    "green":  "&H0033FF33",  # Neon Green
    "cyan":   "&H00FFFF00",  # Electric Cyan
    "white":  "&H00FFFFFF",  # Pure Clean White
    "fire":   "&H000055FF",  # Fiery Orange / Red
}


def clean_single_word(text: str) -> str:
    """Cleans a single word for TikTok ASS subtitles."""
    if not text:
        return ""
    w = text.strip().upper()
    # Strip ASS formatting characters
    w = w.replace("{", "(").replace("}", ")").replace("\\", "/")
    # Strip enclosing quotes and brackets
    w = w.strip("\"'«»“”„`()[]")
    # Strip trailing punctuation (commas, periods, semicolons, colons)
    # Keep expressive '!' or '?' if at end
    w = re.sub(r"[,;:\.]+$", "", w)
    return w.strip()


def generate_ass_content(
    words: List[Dict[str, Any]],
    canvas_w: int = 1080,
    canvas_h: int = 1920,
    font_name: str = "Arial Black",
    font_size: int = 62,
    color_preset: str = "yellow",
    outline_width: float = 6.0,
    margin_v: int = 1040,
) -> str:
    """Generates ASS script content with strictly 1 word per dialogue event."""
    primary_col = COLOR_PRESETS.get(str(color_preset).lower(), COLOR_PRESETS["yellow"])
    outline_col = "&H00000000"   # Solid pitch black outline
    back_col = "&H80000000"      # Subtle shadow

    header = f"""[Script Info]
Title: TikTok 1-Word Viral Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None
PlayResX: {canvas_w}
PlayResY: {canvas_h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TikTokWord,{font_name},{font_size},{primary_col},&H0000FFFF,{outline_col},{back_col},-1,0,0,0,100,100,1,0,1,{outline_width},2.5,2,30,30,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for item in words:
        start_t = format_ass_time(item["start"])
        end_t = format_ass_time(item["end"])
        text = item["text"]
        if not text:
            continue
        events.append(f"Dialogue: 0,{start_t},{end_t},TikTokWord,,0,0,0,,{text}")

    return header + "\n".join(events) + "\n"


async def extract_audio_chunk(
    video_path: str,
    start_time: float,
    duration: float,
    output_wav: str
) -> bool:
    """Extracts raw mono 16kHz WAV audio for Whisper transcription."""
    cmd = [
        FFMPEG_BIN, "-y",
        "-ss", str(start_time),
        "-t", str(duration),
        "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        output_wav
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await proc.wait()
    return proc.returncode == 0 and os.path.exists(output_wav)


def transcribe_raw_words(
    audio_path: str,
    model_size: str = "base",
    language: str = "ru"
) -> List[Dict[str, Any]]:
    """Transcribes audio using faster-whisper and extracts every single word with timestamps."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return []

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(
        audio_path,
        language=language,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=300)
    )

    raw_words = []
    for seg in segments:
        if seg.words:
            for w in seg.words:
                cleaned = clean_single_word(w.word)
                if cleaned:
                    raw_words.append({
                        "start": float(w.start),
                        "end": float(w.end),
                        "word": cleaned
                    })
        else:
            # Fallback if words not populated: divide segment by words
            text_words = seg.text.strip().split()
            if text_words and seg.end > seg.start:
                step = (seg.end - seg.start) / len(text_words)
                for idx, tw in enumerate(text_words):
                    cleaned = clean_single_word(tw)
                    if cleaned:
                        raw_words.append({
                            "start": float(seg.start + idx * step),
                            "end": float(seg.start + (idx + 1) * step),
                            "word": cleaned
                        })

    return raw_words


def align_words_to_timeline(
    raw_words: List[Dict[str, Any]],
    clip_duration: float,
    banner_timestamps: Optional[List[float]] = None,
    pause_duration: float = 0.0,
    pause_enabled: bool = False,
    lead_in: float = 0.14  # 140ms acoustic lead-in to prevent lag
) -> List[Dict[str, Any]]:
    """
    Transforms raw word timestamps into synchronized single-word ASS events:
    1. Subtracts 140ms lead-in so subtitles appear instantaneously with speech articulation.
    2. Adjusts word display length (smooth continuous speech vs. clear gaps on pauses).
    3. Exactly shifts timings for banner pause freezes so subtitles are 100% in sync after banners.
    4. Ensures subtitles never show up during banner freezes.
    """
    if not raw_words:
        return []

    # Segment boundaries in original video time
    if pause_enabled and banner_timestamps and pause_duration > 0:
        valid_ts = sorted([float(ts) for ts in banner_timestamps if 0.0 < float(ts) < clip_duration])
        points = [0.0] + valid_ts + [clip_duration]
    else:
        points = [0.0, clip_duration]
        pause_duration = 0.0

    num_segments = len(points) - 1
    final_words = []
    n = len(raw_words)

    for i in range(n):
        w = raw_words[i]
        r_start = w["start"]
        r_end = w["end"]

        # Identify which segment this word belongs to
        seg_idx = 0
        for s in range(num_segments):
            if points[s] <= r_start < points[s + 1]:
                seg_idx = s
                break
            elif r_start >= points[s + 1]:
                seg_idx = min(s + 1, num_segments - 1)

        seg_start = points[seg_idx]
        seg_end = points[seg_idx + 1]

        # Apply lead-in anticipation, bounded by segment start
        s_time = max(seg_start, r_start - lead_in)

        # Check next word in same segment
        next_w = raw_words[i + 1] if i + 1 < n else None
        if next_w and (seg_start <= next_w["start"] < seg_end):
            next_s = max(seg_start, next_w["start"] - lead_in)
            # Continuous speech vs silence pause
            if (next_w["start"] - r_end) < 0.25:
                e_time = min(next_s, max(r_end, s_time + 0.18))
                if e_time <= s_time:
                    e_time = next_s
            else:
                e_time = min(next_s - 0.02, max(r_end, s_time + 0.20))
        else:
            # End of segment or clip: clamp to segment boundary
            e_time = min(seg_end - 0.02, max(r_end, s_time + 0.20))

        # Clamp within segment
        e_time = min(seg_end - 0.01, max(s_time + 0.12, e_time))

        if e_time <= s_time:
            continue

        # Shift timeline by accumulated banner pause durations for this segment
        shift = seg_idx * pause_duration
        final_start = round(s_time + shift, 3)
        final_end = round(e_time + shift, 3)

        final_words.append({
            "start": final_start,
            "end": final_end,
            "text": w["word"]
        })

    return final_words


async def generate_subtitles_file(
    video_path: str,
    start_time: float,
    duration: float,
    output_ass_path: str,
    banner_timestamps: Optional[List[float]] = None,
    pause_duration: float = 0.0,
    pause_enabled: bool = False,
    font_name: str = "Arial Black",
    font_size: int = 62,
    color_preset: str = "yellow",
    outline_width: float = 6.0,
    margin_v: int = 1040,
    language: str = "ru"
) -> bool:
    """
    Main entry point: extracts audio, runs Whisper word extraction,
    applies single-word timing + pause shift compensation, and writes ASS.
    """
    temp_wav = output_ass_path + ".temp.wav"
    try:
        ok = await extract_audio_chunk(video_path, start_time, duration, temp_wav)
        if not ok:
            return False

        loop = asyncio.get_event_loop()
        raw_words = await loop.run_in_executor(
            None,
            transcribe_raw_words,
            temp_wav,
            "base",
            language
        )

        if not raw_words:
            # Output empty ASS file so ffmpeg doesn't fail
            with open(output_ass_path, "w", encoding="utf-8") as f:
                f.write(generate_ass_content([], font_name=font_name, font_size=font_size, color_preset=color_preset, outline_width=outline_width, margin_v=margin_v))
            return True

        # Align to final video timeline (strictly 1 word at a time + pause shift)
        final_words = align_words_to_timeline(
            raw_words=raw_words,
            clip_duration=duration,
            banner_timestamps=banner_timestamps,
            pause_duration=pause_duration,
            pause_enabled=pause_enabled,
            lead_in=0.14
        )

        ass_content = generate_ass_content(
            words=final_words,
            font_name=font_name,
            font_size=font_size,
            color_preset=color_preset,
            outline_width=outline_width,
            margin_v=margin_v
        )
        with open(output_ass_path, "w", encoding="utf-8") as f:
            f.write(ass_content)

        return True
    except Exception as e:
        print(f"Subtitles generation error: {e}")
        return False
    finally:
        if os.path.exists(temp_wav):
            try:
                os.remove(temp_wav)
            except Exception:
                pass
