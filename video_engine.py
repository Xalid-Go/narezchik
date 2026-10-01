"""
BubaClipper Video Rendering & FFmpeg Pipeline Engine
Optimized for Apple Silicon (h264_videotoolbox) with fallback to libx264.
Features:
- Split-screen compilation (top: main video/speaker, bottom: background video/Subway Surfers)
- Banner insertion with exact BUBA MEDIA Rule 3.4 timings
- Edge-to-edge full width display (1220x530, 27.6% screen area)
- Video & audio freezing (pause) during banner presentation
- Blue screen removal (chromakey / colorkey) for banners
- Banner acceleration up to 1.2x (Rule 3.6: setpts + atempo)
- Mirroring (hflip) for top / bottom video streams to bypass duplicate filters
- Automatic TikTok-style subtitle generation & baking via libass
- Real-time percentage progress callback
"""
import os
import re
import json
import asyncio
import subprocess
import platform
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any

from rules import (
    CANVAS_WIDTH,
    CANVAS_HEIGHT,
    DEFAULT_BANNER_WIDTH,
    DEFAULT_BANNER_HEIGHT,
    DEFAULT_BANNER_DURATION,
    get_banner_timestamps,
    calculate_banner_area_percentage,
)
from subtitles import generate_subtitles_file

BASE_DIR = Path(__file__).resolve().parent
FFMPEG_BIN = str(BASE_DIR / ".venv" / "bin" / "ffmpeg")
if not os.path.exists(FFMPEG_BIN):
    FFMPEG_BIN = "ffmpeg"


def probe_file(file_path: str) -> Dict[str, Any]:
    """Extracts duration, dimensions, fps, audio info from a video file."""
    if not os.path.exists(file_path):
        return {"error": "File not found"}
        
    cmd = [FFMPEG_BIN, "-i", file_path]
    p = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    out = p.stderr
    
    info = {
        "path": file_path,
        "filename": os.path.basename(file_path),
        "size_bytes": os.path.getsize(file_path),
        "duration": 0.0,
        "width": 0,
        "height": 0,
        "fps": 30.0,
        "has_audio": False,
        "has_alpha": "alpha_mode : 1" in out or "yuva420p" in out,
    }
    
    # Duration
    m_dur = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", out)
    if m_dur:
        h, m, s = m_dur.groups()
        info["duration"] = round(int(h) * 3600 + int(m) * 60 + float(s), 2)
        
    # Dimensions & fps
    m_vid = re.search(r"Stream #\d+:\d+.*Video:.*?(\d{2,5})x(\d{2,5})", out)
    if m_vid:
        info["width"] = int(m_vid.group(1))
        info["height"] = int(m_vid.group(2))
        
    m_fps = re.search(r"(\d+(?:\.\d+)?) fps", out)
    if m_fps:
        info["fps"] = float(m_fps.group(1))
        
    info["has_audio"] = "Audio:" in out
    return info



def detect_and_get_chroma_filter(banner_path: str, force_blue_removal: bool = False) -> Optional[str]:
    """
    Intelligently inspects the banner video corners to detect chroma key background (blue or green).
    Returns an optimized FFmpeg filter chain combining chromakey and despill for ideal edge cutting,
    preserving Buba's blue hoodie/eyes while eliminating background and blue edge halo.
    """
    try:
        cmd = [
            FFMPEG_BIN, "-ss", "0.5", "-i", banner_path,
            "-vframes", "1", "-f", "image2pipe", "-vcodec", "png", "-"
        ]
        p = subprocess.run(cmd, capture_output=True)
        if p.returncode == 0 and len(p.stdout) > 0:
            import io
            from PIL import Image
            import numpy as np
            im = Image.open(io.BytesIO(p.stdout))
            arr = np.array(im)
            h, w = arr.shape[:2]
            pad = min(30, max(5, h // 8), max(5, w // 8))
            corners = [
                arr[5:pad, 5:pad],
                arr[5:pad, w-pad:w-5],
                arr[h-pad:h-5, 5:pad],
                arr[h-pad:h-5, w-pad:w-5]
            ]
            corner_pixels = np.concatenate([c.reshape(-1, 3) for c in corners], axis=0)
            r = float(np.median(corner_pixels[:, 0]))
            g = float(np.median(corner_pixels[:, 1]))
            b = float(np.median(corner_pixels[:, 2]))

            is_blue = (b > 110) and (b - max(r, g) > 25)
            is_green = (g > 110) and (g - max(r, b) > 25)

            if is_blue or (force_blue_removal and not is_green):
                hex_color = f"0x{int(r):02x}{int(g):02x}{int(b):02x}" if is_blue else "0x0026ff"
                return f"chromakey={hex_color}:0.20:0.02,despill=type=blue:mix=0.5:expand=0.1"
            elif is_green:
                hex_color = f"0x{int(r):02x}{int(g):02x}{int(b):02x}"
                return f"chromakey={hex_color}:0.20:0.02,despill=type=green:mix=0.5:expand=0.1"
    except Exception:
        pass

    if force_blue_removal:
        return "chromakey=0x0026ff:0.22:0.02,despill=type=blue:mix=0.5:expand=0.1"
    return None


async def render_buba_clip(
    main_video_path: str,
    bg_video_path: str,
    banner_path: str,
    output_path: str,
    start_time: float,
    duration: float,
    bg_offset: float = 0.0,
    banner_width: int = DEFAULT_BANNER_WIDTH,
    banner_height: int = DEFAULT_BANNER_HEIGHT,
    split_ratio: float = 0.5,
    pause_on_banner: bool = True,
    banner_speed: float = 1.0,           # Max 1.2x as per Rule 3.6
    remove_blue_bg: bool = False,         # ChromaKey for blue screen
    mirror_top: bool = False,             # Horizontal flip speaker
    mirror_bottom: bool = False,          # Horizontal flip gameplay
    generate_subtitles: bool = False,     # Whisper TikTok subtitles
    subtitle_font: str = "Arial Black",
    subtitle_size: int = 56,
    subtitle_color: str = "yellow",
    subtitle_outline: float = 5.0,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> bool:
    """
    Renders a vertical 9:16 clip complying with all BUBA MEDIA rules and enhancements.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    # 1. Probe banner and compute timing
    banner_info = probe_file(banner_path)
    base_banner_dur = banner_info.get("duration") or DEFAULT_BANNER_DURATION
    
    # Cap banner speed between 1.0 and 1.2 (Rule 3.6)
    banner_speed = max(1.0, min(1.2, float(banner_speed)))
    eff_banner_dur = round(base_banner_dur / banner_speed, 2)
    
    timestamps = get_banner_timestamps(duration, eff_banner_dur)
    
    # 2. Generate subtitles if requested
    ass_subtitles_file = None
    if generate_subtitles:
        if progress_callback:
            progress_callback(5.0, "Распознавание речи и создание субтитров (Whisper)...")
        sub_path = output_path + ".sub.ass"
        ok_sub = await generate_subtitles_file(
            main_video_path,
            start_time,
            duration,
            sub_path,
            banner_timestamps=timestamps,
            pause_duration=eff_banner_dur,
            pause_enabled=pause_on_banner,
            font_name=subtitle_font,
            font_size=subtitle_size,
            color_preset=subtitle_color,
            outline_width=subtitle_outline,
            margin_v=int(CANVAS_HEIGHT * (1.0 - split_ratio) + 90),
        )
        if ok_sub and os.path.exists(sub_path):
            ass_subtitles_file = sub_path

    # Top and bottom heights
    top_h = int(CANVAS_HEIGHT * split_ratio)
    if top_h % 2 != 0:
        top_h -= 1
    bottom_h = CANVAS_HEIGHT - top_h

    # Encoders
    if platform.system() == "Darwin":
        video_enc_args = ["-c:v", "h264_videotoolbox", "-b:v", "6000k"]
    else:
        video_enc_args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-b:v", "5000k"]

    # Mirroring filters
    top_flip = ",hflip" if mirror_top else ""
    bot_flip = ",hflip" if mirror_bottom else ""

    # Banner filter modifiers & chroma key
    banner_filters = []
    chroma_filter = detect_and_get_chroma_filter(banner_path, force_blue_removal=remove_blue_bg)
    if chroma_filter:
        banner_filters.append(chroma_filter)
    banner_filters.append("format=yuva420p")
    banner_filters.append(f"scale={banner_width}:{banner_height}")
    
    if banner_speed != 1.0:
        banner_filters.append(f"setpts=PTS/{banner_speed}")
        audio_speed_filter = f",atempo={banner_speed}"
    else:
        audio_speed_filter = ""

    banner_filter_base = ",".join(banner_filters)

    # Appropriate decoder flags for banner input
    is_banner_webm = banner_path.lower().endswith(".webm")
    banner_input_args = ["-c:v", "libvpx-vp9", "-i", banner_path] if is_banner_webm else ["-i", banner_path]

    if pause_on_banner and len(timestamps) > 0:
        points = [0.0] + [ts for ts in timestamps] + [duration]
        n_seg = len(points) - 1

        cmd = [FFMPEG_BIN, "-y"]
        # Add main video and bg video segments
        for i in range(n_seg):
            seg_s = start_time + points[i]
            seg_d = points[i + 1] - points[i]
            cmd.extend(["-ss", str(seg_s), "-t", str(seg_d), "-i", main_video_path])
            bg_s = bg_offset + points[i]
            cmd.extend(["-ss", str(bg_s), "-t", str(seg_d), "-i", bg_video_path])

        banner_input_start = 2 * n_seg
        for _ in range(len(timestamps)):
            cmd.extend(banner_input_args)

        filter_parts = []
        for i in range(n_seg):
            in_top = 2 * i
            in_bot = 2 * i + 1
            pad_filter = f",tpad=stop_mode=clone:stop_duration={eff_banner_dur}" if i < n_seg - 1 else ""
            filter_parts.append(
                f"[{in_top}:v]scale={CANVAS_WIDTH}:{top_h}:force_original_aspect_ratio=increase,crop={CANVAS_WIDTH}:{top_h}{top_flip}{pad_filter}[top_seg_{i}]"
            )
            filter_parts.append(
                f"[{in_bot}:v]scale={CANVAS_WIDTH}:{bottom_h}:force_original_aspect_ratio=increase,crop={CANVAS_WIDTH}:{bottom_h}{bot_flip}{pad_filter}[bot_seg_{i}]"
            )

        top_inputs = "".join(f"[top_seg_{i}]" for i in range(n_seg))
        bot_inputs = "".join(f"[bot_seg_{i}]" for i in range(n_seg))
        filter_parts.append(f"{top_inputs}concat=n={n_seg}:v=1:a=0[v_top]")
        filter_parts.append(f"{bot_inputs}concat=n={n_seg}:v=1:a=0[v_bot]")
        filter_parts.append("[v_top][v_bot]vstack[v_stacked]")

        # Apply subtitles if present
        if ass_subtitles_file:
            safe_ass = ass_subtitles_file.replace("\\", "/").replace(":", "\\:")
            filter_parts.append(f"[v_stacked]ass='{safe_ass}'[v_base0]")
        else:
            filter_parts.append("[v_stacked]null[v_base0]")

        audio_seg_inputs = []
        for i in range(n_seg):
            in_top = 2 * i
            if i < n_seg - 1:
                filter_parts.append(f"[{in_top}:a]apad=pad_dur={eff_banner_dur}[a_seg_{i}]")
            else:
                filter_parts.append(f"[{in_top}:a]anull[a_seg_{i}]")
            audio_seg_inputs.append(f"[a_seg_{i}]")

        filter_parts.append(f"{''.join(audio_seg_inputs)}concat=n={n_seg}:v=0:a=1[a_main]")

        current_base = "v_base0"
        banner_audio_list = ["[a_main]"]
        for j, ts in enumerate(timestamps):
            final_ts = ts + j * eff_banner_dur
            input_idx = banner_input_start + j
            next_base = f"v_base{j+1}" if j + 1 < len(timestamps) else "v_out"

            filter_parts.append(
                f"[{input_idx}:v]{banner_filter_base},"
                f"setpts=PTS-STARTPTS+{final_ts}/TB[b_scaled{j}]"
            )
            filter_parts.append(
                f"[{current_base}][b_scaled{j}]overlay=(W-w)/2:(H-h)/2:"
                f"enable='between(t,{final_ts},{final_ts + eff_banner_dur})'[{next_base}]"
            )
            current_base = next_base

            delay_ms = int(final_ts * 1000)
            filter_parts.append(f"[{input_idx}:a]{audio_speed_filter.lstrip(',')}{',' if audio_speed_filter else ''}adelay={delay_ms}|{delay_ms}[ba{j}]")
            banner_audio_list.append(f"[ba{j}]")

        filter_parts.append(f"{''.join(banner_audio_list)}amix=inputs={len(banner_audio_list)}:duration=first[a_out]")
        total_render_duration = duration + len(timestamps) * eff_banner_dur

        cmd.extend([
            "-filter_complex", "; ".join(filter_parts),
            "-map", f"[{current_base}]",
            "-map", "[a_out]",
            *video_enc_args,
            "-c:a", "aac", "-b:a", "192k",
            "-t", str(total_render_duration),
            output_path,
        ])
    else:
        # Standard continuous playback without freeze
        cmd = [
            FFMPEG_BIN, "-y",
            "-ss", str(start_time), "-t", str(duration), "-i", main_video_path,
            "-ss", str(bg_offset), "-t", str(duration), "-i", bg_video_path,
        ]
        num_banners = len(timestamps)
        for _ in range(num_banners):
            cmd.extend(banner_input_args)

        filter_parts = [
            f"[0:v]scale={CANVAS_WIDTH}:{top_h}:force_original_aspect_ratio=increase,crop={CANVAS_WIDTH}:{top_h}{top_flip}[v_top]",
            f"[1:v]scale={CANVAS_WIDTH}:{bottom_h}:force_original_aspect_ratio=increase,crop={CANVAS_WIDTH}:{bottom_h}{bot_flip}[v_bottom]",
            "[v_top][v_bottom]vstack[v_stacked]",
        ]

        if ass_subtitles_file:
            safe_ass = ass_subtitles_file.replace("\\", "/").replace(":", "\\:")
            filter_parts.append(f"[v_stacked]ass='{safe_ass}'[v_base0]")
        else:
            filter_parts.append("[v_stacked]null[v_base0]")

        current_base = "v_base0"
        for idx, ts in enumerate(timestamps):
            input_idx = 2 + idx
            next_base = f"v_base{idx+1}" if idx + 1 < num_banners else "v_out"
            filter_parts.append(
                f"[{input_idx}:v]{banner_filter_base},"
                f"setpts=PTS-STARTPTS+{ts}/TB[b_scaled{idx}]"
            )
            filter_parts.append(
                f"[{current_base}][b_scaled{idx}]overlay=(W-w)/2:(H-h)/2:"
                f"enable='between(t,{ts},{ts + eff_banner_dur})'[{next_base}]"
            )
            current_base = next_base

        audio_inputs = ["[0:a]"]
        for idx, ts in enumerate(timestamps):
            input_idx = 2 + idx
            delay_ms = int(ts * 1000)
            filter_parts.append(f"[{input_idx}:a]{audio_speed_filter.lstrip(',')}{',' if audio_speed_filter else ''}adelay={delay_ms}|{delay_ms}[ba{idx}]")
            audio_inputs.append(f"[ba{idx}]")

        if len(audio_inputs) > 1:
            mix_inputs = "".join(audio_inputs)
            filter_parts.append(f"{mix_inputs}amix=inputs={len(audio_inputs)}:duration=first[a_out]")
            map_a = "[a_out]"
        else:
            map_a = "0:a"

        total_render_duration = duration
        cmd.extend([
            "-filter_complex", "; ".join(filter_parts),
            "-map", f"[{current_base}]",
            "-map", map_a,
            *video_enc_args,
            "-c:a", "aac", "-b:a", "192k",
            "-t", str(duration),
            output_path,
        ])
    
    # Run async subprocess with progress monitoring
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    
    time_regex = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
    
    async def monitor_stream(stream):
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace")
            m = time_regex.search(text)
            if m and progress_callback:
                h, m_, s = m.groups()
                current_sec = int(h) * 3600 + int(m_) * 60 + float(s)
                pct = min(100.0, round((current_sec / total_render_duration) * 100.0, 1))
                progress_callback(pct, f"Рендеринг: {pct}% ({int(current_sec)}/{int(total_render_duration)}с)")

    await asyncio.gather(monitor_stream(process.stderr), process.wait())
    
    # If videotoolbox failed, fallback to libx264
    if process.returncode != 0:
        if progress_callback:
            progress_callback(0.0, "Повтор с софтовым энкодером libx264...")
        fallback_cmd = [
            arg if arg != "h264_videotoolbox" else "libx264"
            for arg in cmd
        ]
        if "libx264" in fallback_cmd:
            idx_c = fallback_cmd.index("libx264")
            fallback_cmd[idx_c:idx_c+1] = ["libx264", "-preset", "veryfast", "-crf", "22"]
        
        fallback_proc = await asyncio.create_subprocess_exec(
            *fallback_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.gather(monitor_stream(fallback_proc.stderr), fallback_proc.wait())
        success = fallback_proc.returncode == 0
    else:
        success = True

    # Clean up temp subtitles file
    if ass_subtitles_file and os.path.exists(ass_subtitles_file):
        try:
            os.remove(ass_subtitles_file)
        except Exception:
            pass

    if success and progress_callback:
        progress_callback(100.0, "Готово!")
    return success
