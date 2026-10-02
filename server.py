"""
BubaClipper FastAPI Server
Provides REST APIs for:
- Video file scanning, upload & downloading via URLs (yt-dlp)
- Custom clip rendering & Batch auto-slicing (Split, Subtitles, Mirroring, ChromaKey, 1.2x Banner Speed)
- Real-time task progress monitoring
- Clip gallery, download & video streaming
- Hashtag & Bio checkers for TikTok & Shorts
- Pre-flight compliance audit before submission (calculates strict visible area >= 25%)
- VIP Support tickets & Priority payout queue
- Web UI serving
"""
import os
import sys
import uuid
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import BaseModel

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from rules import (
    CANVAS_WIDTH,
    CANVAS_HEIGHT,
    DEFAULT_BANNER_WIDTH,
    DEFAULT_BANNER_HEIGHT,
    DEFAULT_BANNER_DURATION,
    get_banner_timestamps,
    calculate_banner_area_percentage,
    calculate_visible_banner_percentage,
    is_banner_compliant,
    generate_tiktok_caption,
)
from video_engine import probe_file, render_buba_clip, BASE_DIR
from checker import check_video_hashtag, check_profile_bio
from audit import audit_clip_submission
from tickets import (
    create_ticket,
    list_tickets,
    add_ticket_message,
    submit_payout_request,
    list_payout_requests,
)

app = FastAPI(title="BubaClipper Pro API", version="2.5.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_DIR = BASE_DIR / "output"
STATIC_DIR = BASE_DIR / "static"
OUTPUT_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

# In-memory task queue
TASKS: Dict[str, Dict[str, Any]] = {}


class SingleRenderRequest(BaseModel):
    main_video: str
    bg_video: str
    banner_file: str
    start_time: float
    duration: float
    bg_offset: float = 0.0
    split_ratio: float = 0.5
    banner_width: int = DEFAULT_BANNER_WIDTH
    banner_height: int = DEFAULT_BANNER_HEIGHT
    pause_on_banner: bool = True
    banner_speed: float = 1.0
    remove_blue_bg: bool = False
    mirror_top: bool = False
    mirror_bottom: bool = False
    generate_subtitles: bool = False
    subtitle_font: str = "Arial Black"
    subtitle_size: int = 56
    subtitle_color: str = "yellow"
    subtitle_outline: float = 5.0
    custom_name: Optional[str] = None


class BatchRenderRequest(BaseModel):
    main_video: str
    bg_video: str
    banner_file: str
    clip_duration: float = 60.0
    start_offset: float = 0.0
    max_clips: Optional[int] = None
    split_ratio: float = 0.5
    banner_width: int = DEFAULT_BANNER_WIDTH
    banner_height: int = DEFAULT_BANNER_HEIGHT
    pause_on_banner: bool = True
    banner_speed: float = 1.0
    remove_blue_bg: bool = False
    mirror_top: bool = False
    mirror_bottom: bool = False
    generate_subtitles: bool = False
    subtitle_font: str = "Arial Black"
    subtitle_size: int = 56
    subtitle_color: str = "yellow"
    subtitle_outline: float = 5.0


class DownloadUrlRequest(BaseModel):
    url: str
    target_role: str = "main"


class HashtagCheckRequest(BaseModel):
    url: str
    target_hashtag: str = "#бубавпн"


class BioCheckRequest(BaseModel):
    url: str


class AuditRequest(BaseModel):
    video_file: str
    banner_w: int = DEFAULT_BANNER_WIDTH
    banner_h: int = DEFAULT_BANNER_HEIGHT
    post_url: Optional[str] = None
    profile_url: Optional[str] = None


class TicketCreateRequest(BaseModel):
    user_id: str
    subject: str
    message: str
    is_vip: bool = True


class PayoutSubmitRequest(BaseModel):
    video_url: str
    profile_url: str = ""
    views: int = 100000
    wallet_or_card: str
    telegram_tag: str
    is_priority: bool = True


@app.get("/api/files")
def list_files():
    """Scans workspace directory for suitable video and banner files."""
    valid_exts = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
    files = []
    for f in BASE_DIR.iterdir():
        if f.is_file() and f.suffix.lower() in valid_exts and not f.name.startswith("test_"):
            info = probe_file(str(f))
            files.append(info)
    return {"files": files}


@app.post("/api/upload")
async def api_upload_file(file: UploadFile = File(...)):
    """Uploads a local video or banner file directly into the workspace."""
    safe_name = os.path.basename(file.filename)
    dest_path = BASE_DIR / safe_name
    with open(dest_path, "wb") as f:
        content = await file.read()
        f.write(content)
    info = probe_file(str(dest_path))
    return {"success": True, "filename": safe_name, "info": info}


@app.post("/api/upload-chunk")
async def api_upload_chunk(
    file: UploadFile = File(...),
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    filename: str = Form(...)
):
    """
    Chunked upload endpoint: accepts 5-10MB pieces to bypass proxy 413 limits.
    Reassembles the full file once all chunks arrive.
    """
    temp_dir = BASE_DIR / "temp_uploads" / upload_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = temp_dir / f"chunk_{chunk_index:05d}"
    with open(chunk_path, "wb") as f:
        f.write(await file.read())

    existing_chunks = list(temp_dir.glob("chunk_*"))
    if len(existing_chunks) == total_chunks:
        safe_name = os.path.basename(filename)
        dest_path = BASE_DIR / safe_name
        with open(dest_path, "wb") as out_f:
            for idx in range(total_chunks):
                c_part = temp_dir / f"chunk_{idx:05d}"
                if c_part.exists():
                    with open(c_part, "rb") as in_f:
                        out_f.write(in_f.read())
                    try:
                        c_part.unlink()
                    except Exception:
                        pass
        try:
            temp_dir.rmdir()
        except Exception:
            pass
        info = probe_file(str(dest_path))
        return {"success": True, "completed": True, "filename": safe_name, "info": info}

    return {"success": True, "completed": False, "progress": round((len(existing_chunks) / total_chunks) * 100, 1)}


@app.post("/api/download-url")
async def api_download_url(req: DownloadUrlRequest):
    """Downloads a video by URL using yt-dlp with android player client to bypass YouTube datacenter bot checks."""
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Укажите ссылку на видео")
    
    out_tmpl = str(BASE_DIR / "%(title).40s_%(id)s.%(ext)s")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--no-playlist",
        "--extractor-args", "youtube:player_client=android,web",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", out_tmpl,
        "--no-warnings",
        url
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300.0)
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace")
            raise HTTPException(status_code=400, detail=f"Ошибка загрузки: {err[:200]}")
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail="Превышено время ожидания загрузки видео")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    return {"success": True, "files": list_files()["files"], "message": "Видео успешно скачано!"}


@app.get("/api/probe")
def get_probe_info(file_path: str):
    path = Path(file_path)
    if not path.is_absolute():
        path = BASE_DIR / file_path
    if not path.exists():
        raise HTTPException(status_code=404, detail="Файл не найден")
    return probe_file(str(path))


@app.get("/api/rules/info")
def get_rules_info(duration: float, banner_w: int = DEFAULT_BANNER_WIDTH, banner_h: int = DEFAULT_BANNER_HEIGHT):
    timestamps = get_banner_timestamps(duration)
    vis_pct = calculate_visible_banner_percentage(banner_w, banner_h)
    box_pct = calculate_banner_area_percentage(banner_w, banner_h)
    compliant = is_banner_compliant(banner_w, banner_h)
    return {
        "duration": duration,
        "timestamps": timestamps,
        "banner_count": len(timestamps),
        "visible_area_percentage": vis_pct,
        "box_area_percentage": box_pct,
        "is_compliant": compliant,
        "caption": generate_tiktok_caption(),
    }


async def process_render_task(task_id: str, params: dict):
    task = TASKS[task_id]
    task["status"] = "processing"
    
    def on_progress(pct: float, msg: str):
        task["progress"] = pct
        task["message"] = msg
        
    try:
        ok = await render_buba_clip(
            main_video_path=params["main_video"],
            bg_video_path=params["bg_video"],
            banner_path=params["banner_file"],
            output_path=params["output_path"],
            start_time=params["start_time"],
            duration=params["duration"],
            bg_offset=params["bg_offset"],
            banner_width=params["banner_width"],
            banner_height=params["banner_height"],
            split_ratio=params["split_ratio"],
            pause_on_banner=params.get("pause_on_banner", True),
            banner_speed=params.get("banner_speed", 1.0),
            remove_blue_bg=params.get("remove_blue_bg", False),
            mirror_top=params.get("mirror_top", False),
            mirror_bottom=params.get("mirror_bottom", False),
            generate_subtitles=params.get("generate_subtitles", False),
            progress_callback=on_progress,
        )
        if ok and os.path.exists(params["output_path"]):
            task["status"] = "completed"
            task["progress"] = 100.0
            task["message"] = "Успешно создано!"
            task["output_file"] = os.path.basename(params["output_path"])
        else:
            task["status"] = "failed"
            task["message"] = "Ошибка FFmpeg при сборке ролика."
    except Exception as e:
        task["status"] = "failed"
        task["message"] = str(e)


@app.post("/api/render/single")
async def start_single_render(req: SingleRenderRequest, bg_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())[:8]
    out_name = req.custom_name or f"clip_{task_id}.mp4"
    if not out_name.endswith(".mp4"):
        out_name += ".mp4"
    output_path = str(OUTPUT_DIR / out_name)
    
    params = {
        "main_video": str(BASE_DIR / req.main_video if not os.path.isabs(req.main_video) else req.main_video),
        "bg_video": str(BASE_DIR / req.bg_video if not os.path.isabs(req.bg_video) else req.bg_video),
        "banner_file": str(BASE_DIR / req.banner_file if not os.path.isabs(req.banner_file) else req.banner_file),
        "output_path": output_path,
        "start_time": req.start_time,
        "duration": req.duration,
        "bg_offset": req.bg_offset,
        "split_ratio": req.split_ratio,
        "banner_width": req.banner_width,
        "banner_height": req.banner_height,
        "pause_on_banner": req.pause_on_banner,
        "banner_speed": req.banner_speed,
        "remove_blue_bg": req.remove_blue_bg,
        "mirror_top": req.mirror_top,
        "mirror_bottom": req.mirror_bottom,
        "generate_subtitles": req.generate_subtitles,
        "subtitle_font": req.subtitle_font,
        "subtitle_size": req.subtitle_size,
        "subtitle_color": req.subtitle_color,
        "subtitle_outline": req.subtitle_outline,
    }
    
    TASKS[task_id] = {
        "id": task_id,
        "type": "single",
        "name": out_name,
        "status": "queued",
        "progress": 0.0,
        "message": "В очереди на рендеринг...",
        "output_file": out_name,
        "caption": generate_tiktok_caption(),
    }
    
    bg_tasks.add_task(process_render_task, task_id, params)
    return {"task_id": task_id, "status": "queued"}


@app.post("/api/render/batch")
async def start_batch_render(req: BatchRenderRequest, bg_tasks: BackgroundTasks):
    main_p = str(BASE_DIR / req.main_video if not os.path.isabs(req.main_video) else req.main_video)
    bg_p = str(BASE_DIR / req.bg_video if not os.path.isabs(req.bg_video) else req.bg_video)
    banner_p = str(BASE_DIR / req.banner_file if not os.path.isabs(req.banner_file) else req.banner_file)
    
    main_info = probe_file(main_p)
    bg_info = probe_file(bg_p)
    total_dur = main_info.get("duration", 0.0)
    bg_dur = bg_info.get("duration", 500.0)
    
    if total_dur <= 0:
        raise HTTPException(status_code=400, detail="Не удалось определить длительность основного видео")
        
    created_task_ids = []
    current_time = req.start_offset
    part = 1
    
    planned_clips = []
    while current_time + 10.0 <= total_dur:
        dur = min(req.clip_duration, total_dur - current_time)
        if dur < 10.0:
            break
        planned_clips.append((current_time, dur, part))
        current_time += dur
        part += 1
        if req.max_clips and len(planned_clips) >= req.max_clips:
            break
            
    total_parts = len(planned_clips)
    
    for start_t, dur, p_num in planned_clips:
        task_id = str(uuid.uuid4())[:8]
        out_name = f"part_{p_num:02d}_{int(dur)}s_{task_id}.mp4"
        output_path = str(OUTPUT_DIR / out_name)
        
        cur_bg_offset = (start_t * 0.7) % max(10.0, bg_dur - dur - 5.0)
        
        params = {
            "main_video": main_p,
            "bg_video": bg_p,
            "banner_file": banner_p,
            "output_path": output_path,
            "start_time": start_t,
            "duration": dur,
            "bg_offset": cur_bg_offset,
            "split_ratio": req.split_ratio,
            "banner_width": req.banner_width,
            "banner_height": req.banner_height,
            "pause_on_banner": req.pause_on_banner,
            "banner_speed": req.banner_speed,
            "remove_blue_bg": req.remove_blue_bg,
            "mirror_top": req.mirror_top,
            "mirror_bottom": req.mirror_bottom,
            "generate_subtitles": req.generate_subtitles,
        }
        
        TASKS[task_id] = {
            "id": task_id,
            "type": "batch",
            "name": f"Часть {p_num}/{total_parts} ({int(dur)}c)",
            "status": "queued",
            "progress": 0.0,
            "message": "Ожидает очереди...",
            "output_file": out_name,
            "caption": generate_tiktok_caption(p_num, total_parts),
        }
        created_task_ids.append(task_id)
        
    async def run_batch_sequential(task_list):
        for tid, pars in task_list:
            await process_render_task(tid, pars)
            
    items_to_run = [(tid, {
        "main_video": main_p,
        "bg_video": bg_p,
        "banner_file": banner_p,
        "output_path": str(OUTPUT_DIR / TASKS[tid]["output_file"]),
        "start_time": planned_clips[i][0],
        "duration": planned_clips[i][1],
        "bg_offset": (planned_clips[i][0] * 0.7) % max(10.0, bg_dur - planned_clips[i][1] - 5.0),
        "split_ratio": req.split_ratio,
        "banner_width": req.banner_width,
        "banner_height": req.banner_height,
        "pause_on_banner": req.pause_on_banner,
        "banner_speed": req.banner_speed,
        "remove_blue_bg": req.remove_blue_bg,
        "mirror_top": req.mirror_top,
        "mirror_bottom": req.mirror_bottom,
        "generate_subtitles": req.generate_subtitles,
        "subtitle_font": req.subtitle_font,
        "subtitle_size": req.subtitle_size,
        "subtitle_color": req.subtitle_color,
        "subtitle_outline": req.subtitle_outline,
    }) for i, tid in enumerate(created_task_ids)]
    
    bg_tasks.add_task(run_batch_sequential, items_to_run)
    return {"batch_count": len(created_task_ids), "task_ids": created_task_ids}


@app.get("/api/tasks")
def get_tasks():
    return {"tasks": list(TASKS.values())}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return TASKS[task_id]


@app.get("/api/clips")
def list_rendered_clips():
    clips = []
    if OUTPUT_DIR.exists():
        for f in sorted(OUTPUT_DIR.iterdir(), key=os.path.getmtime, reverse=True):
            if f.is_file() and f.suffix.lower() == ".mp4":
                info = probe_file(str(f))
                clips.append({
                    "filename": f.name,
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                    "duration": info.get("duration", 0),
                    "mtime": f.stat().st_mtime,
                    "url": f"/clips/{f.name}",
                    "caption": generate_tiktok_caption(),
                })
    return {"clips": clips}


@app.get("/clips/{filename}")
def download_clip(filename: str):
    target = OUTPUT_DIR / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(path=str(target), media_type="video/mp4", filename=filename)


@app.post("/api/check/hashtag")
async def api_check_hashtag(req: HashtagCheckRequest):
    return await check_video_hashtag(req.url, req.target_hashtag)


@app.post("/api/check/bio")
async def api_check_bio(req: BioCheckRequest):
    return await check_profile_bio(req.url)


@app.post("/api/audit")
async def api_audit(req: AuditRequest):
    target = OUTPUT_DIR / req.video_file if not os.path.isabs(req.video_file) else Path(req.video_file)
    if not target.exists():
        cand = BASE_DIR / req.video_file
        if cand.exists():
            target = cand
        else:
            raise HTTPException(status_code=404, detail="Файл для аудита не найден")
    return await audit_clip_submission(
        str(target),
        banner_w=req.banner_w,
        banner_h=req.banner_h,
        post_url=req.post_url,
        profile_url=req.profile_url
    )


@app.get("/api/tickets")
def api_get_tickets(user_id: Optional[str] = None):
    return {"tickets": list_tickets(user_id)}


@app.post("/api/tickets/create")
def api_create_ticket(req: TicketCreateRequest):
    return create_ticket(user_id=req.user_id, subject=req.subject, message=req.message, is_vip=req.is_vip)


@app.get("/api/payouts")
def api_get_payouts(telegram_tag: Optional[str] = None):
    return {"payouts": list_payout_requests(telegram_tag)}


@app.post("/api/payout/submit")
def api_submit_payout(req: PayoutSubmitRequest):
    return submit_payout_request(
        video_url=req.video_url,
        profile_url=req.profile_url,
        views=req.views,
        wallet_or_card=req.wallet_or_card,
        telegram_tag=req.telegram_tag,
        is_priority=req.is_priority
    )


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static_dir")

@app.get("/")
def serve_index():
    return FileResponse(STATIC_DIR / "index.html")

app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="root_static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
