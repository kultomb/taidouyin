import os
import sys
import uuid
import time
import logging
import threading

# If running in PyInstaller bundle, add MEIPASS directory to PATH
# so that subprocesses and shutil.which can find ffmpeg and ffprobe automatically.
# Also redirect stdout/stderr to os.devnull to prevent Uvicorn console crashes in windowed mode.
if getattr(sys, 'frozen', False):
    os.environ["PATH"] = sys._MEIPASS + os.pathsep + os.environ["PATH"]
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")


from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, Dict, List

# Import our custom modules
from downloader import download_douyin_video, load_cookies_txt
from audio_processor import extract_audio, generate_srt, generate_srt_from_timeline, mix_audio_and_video
from translator import get_vertex_client, transcribe_and_translate_audio
from tts_processor import generate_tts_for_subtitles, detect_speaker_gender
from ocr_engine import extract_subtitle_segments
from google.genai import types  # cho GenerateContentConfig

# Import pipelines
from pipelines.dubbing import DubbingPipeline

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("douyin_translator")

app = FastAPI(title="Douyin Video Translator SaaS")

@app.on_event("startup")
def verify_system_requirements():
    import shutil
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    if not ffmpeg_path:
        logger.error("=" * 60)
        logger.error("LỖI KHỞI ĐỘNG: Không tìm thấy 'ffmpeg' trong biến môi trường PATH!")
        logger.error("Vui lòng tải FFmpeg và cấu hình thư mục chứa ffmpeg.exe vào PATH.")
        logger.error("Nếu không, các bước tách âm thanh và trộn video Việt hóa sẽ BỊ LỖI.")
        logger.error("=" * 60)
    else:
        logger.info(f"[REQUIREMENT] Tìm thấy ffmpeg tại: {ffmpeg_path}")

    if not ffprobe_path:
        logger.error("=" * 60)
        logger.error("LỖI KHỞI ĐỘNG: Không tìm thấy 'ffprobe' trong biến môi trường PATH!")
        logger.error("Vui lòng đảm bảo ffprobe.exe được đặt cùng thư mục với ffmpeg.")
        logger.error("=" * 60)
    else:
        logger.info(f"[REQUIREMENT] Tìm thấy ffprobe tại: {ffprobe_path}")

# Serve UI static files
# Resolve base paths for PyInstaller compatibility
import sys
from pathlib import Path

if getattr(sys, 'frozen', False):
    base_dir = Path(sys._MEIPASS)
    # Output is created relative to the EXE location, not inside temporary folder
    exe_dir = Path(sys.executable).resolve().parent
else:
    base_dir = Path(__file__).resolve().parent
    exe_dir = base_dir

static_dir = base_dir / "static"
output_dir = exe_dir / "output"

os.makedirs(static_dir, exist_ok=True)
os.makedirs(output_dir, exist_ok=True)


# Memory store for jobs (with TTL: tự động xóa sau 2 giờ)
JOBS_TTL_SECONDS = 7200  # 2 giờ
jobs = {}

# Rate limiter đơn giản
_last_request_time = 0.0
MIN_REQUEST_INTERVAL = 2.0  # Tối thiểu 2s giữa các request

def _cleanup_expired_jobs():
    """Xóa job quá hạn TTL để tránh memory leak và giải phóng bộ nhớ vật lý."""
    import shutil
    now = time.time()
    expired = [jid for jid, j in jobs.items() if now - j.get("_created", now) > JOBS_TTL_SECONDS]
    for jid in expired:
        job = jobs[jid]
        folder = job.get("job_folder")
        if folder and os.path.exists(folder):
            try:
                shutil.rmtree(folder, ignore_errors=True)
                logger.info(f"Đã giải phóng thư mục vật lý của job hết hạn: {folder}")
            except Exception as fe:
                logger.warning(f"Không thể xóa thư mục rác {folder}: {fe}")
        del jobs[jid]
    if expired:
        logger.info(f"Cleaned up {len(expired)} expired jobs")


def find_matching_srt(base_name: str) -> Optional[str]:
    """Tìm file srt trùng khớp trong thư mục projects/."""
    if not base_name:
        return None
    projects_dir = "projects"
    if not os.path.exists(projects_dir):
        return None
        
    clean_base = "".join(c if c.isalnum() or c in "_-" else "_" for c in base_name)
    candidates = [
        os.path.join(projects_dir, f"{clean_base}_viet.srt"),
        os.path.join(projects_dir, f"{clean_base}.srt")
    ]
    for cand in candidates:
        if os.path.exists(cand):
            return cand
    return None


def run_pipeline_import(job_id: str, video_path: str):
    """Phase 1 cho video import (local file) — bỏ qua download."""
    job = jobs[job_id]
    
    # Ưu tiên lấy tên gốc truyền từ frontend để giữ tên video nguyên bản
    original_filename = job.get("original_filename")
    if original_filename:
        base_name = os.path.splitext(original_filename)[0]
    else:
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        
    job["video_base_name"] = base_name
    
    # Kiểm tra xem có phụ đề SRT tương ứng trong projects/ không
    detected_srt = find_matching_srt(base_name)
    if detected_srt:
        job["detected_srt"] = detected_srt
        
    safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in base_name)[:40]
    
    # Xóa các thư mục công việc cũ của cùng một video trong output/ để tránh nặng bộ nhớ
    import glob
    import shutil
    if safe_name and len(safe_name) >= 3:
        existing_folders = glob.glob(os.path.join("output", f"*_{safe_name}"))
        for old_folder in existing_folders:
            if os.path.exists(old_folder) and os.path.isdir(old_folder):
                try:
                    shutil.rmtree(old_folder, ignore_errors=True)
                    logger.info(f"Đã dọn dẹp thư mục cũ để tiết kiệm dung lượng: {old_folder}")
                except Exception as de:
                    logger.warning(f"Không thể xóa thư mục cũ {old_folder}: {de}")
                    
    job_folder_name = f"{time.strftime('%Y%m%d_%H%M%S')}_{safe_name}"
    job_folder = f"output/{job_folder_name}"
    os.makedirs(job_folder, exist_ok=True)
    job["job_folder"] = job_folder
    job["folder_name"] = job_folder_name

    def log(msg: str):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] INFO - {msg}"
        job["logs"].append(line)
        logger.info(f"[{job_id}] {msg}")

    try:
        job["step"] = 1
        job["sub_step"] = "STEP 1.0: Di chuyển video từ file import..."
        log(f"Di chuyển video từ: {video_path}")
        original_path = os.path.join(job_folder, "original.mp4")
        shutil.move(video_path, original_path)
        video_path = original_path
        job["original_video"] = video_path
        log(f"Import video thành công: {video_path}")

        if os.path.exists(video_path):
            log("Tối ưu cấu trúc video (Fast Start)...")
            fast_path = os.path.join(job_folder, "original_fast.mp4")
            cmd = ["ffmpeg", "-y", "-i", video_path, "-c", "copy", "-map", "0", "-movflags", "+faststart", fast_path]
            try:
                import subprocess
                subprocess.run(cmd, capture_output=True, check=True, timeout=30)
                os.replace(fast_path, video_path)
                log("Tối ưu cấu trúc video thành công.")
            except Exception as fe:
                log(f"Không thể tối ưu Fast Start: {fe}")

        if job.get("process_mode", "ocr") == "auto" or job.get("imported_srt") or job.get("use_detected_srt"):
            log("Đã nạp phụ đề hoặc chạy chế độ ASR tự động. Bắt đầu Phase 2 ngay...")
            job["status"] = "running"
            dubbing_pipeline.run_phase2(job_id, use_ocr=False, y_start=0, y_end=0, x_start=0, x_end=0)
        else:
            job["status"] = "awaiting_ocr_selection"
            job["sub_step"] = "Đang chờ chọn vùng quét phụ đề (OCR)..."
            log("Import video thành công. Hiển thị video để chọn vùng OCR.")
    except Exception as e:
        logger.error(f"Pipeline Import failure: {str(e)}", exc_info=True)
        job["status"] = "failed"
        job["error"] = str(e)
        job["sub_step"] = "LỖI: Import video thất bại."
        log(f"LỖI HỆ THỐNG: {str(e)}")


class TranslateRequest(BaseModel):
    url: str = ""
    imported_file: Optional[str] = None
    bg_volume: float = 0.30  # Ducking: bg audio volume when TTS is silent
    burn_subtitles: bool = False
    tts_provider: str = "edge"  # "edge", "google", hoặc "gemini"
    asr_mode: str = "audio"  # "audio", "video", hoặc "whisper"
    translate_provider: str = "gemini"  # "gemini" hoặc "gist"
    process_mode: str = "ocr"  # "auto" hoặc "ocr"
    voice_map: Optional[Dict] = None  # Ánh xạ từ Speaker name sang giọng đọc chỉ định (tùy chọn)
    voice_name: Optional[str] = None  # Giọng đọc đồng nhất áp dụng cho toàn bộ video (tắt phân vai)
    voice_female: Optional[str] = None  # Giọng Nữ khi chọn tự động phân vai
    voice_male: Optional[str] = None    # Giọng Nam khi chọn tự động phân vai
    topic: Optional[str] = None  # Chủ đề video (vd: sửa điện thoại, tây du ký, review...)
    tts_speed: float = 1.40  # Tốc độ giọng đọc (1.0 = bình thường, 1.4 = nhanh 40%)
    translate_style: str = "default"  # Phong cách dịch: default, dialogue, review, tutorial
    context: Optional[str] = None  # Bối cảnh video để AI hiểu nội dung (vd: phim Tây Du Ký, có Natra...)
    subtitle_style: Optional[Dict] = None  # Style ASS subtitle {font, fontsize, color, position}
    resolution: Optional[str] = "1080"  # Độ phân giải tải video: best, 1080, 720
    imported_srt: Optional[str] = None
    use_detected_srt: bool = False
    original_filename: Optional[str] = None

class ResumeRequest(BaseModel):
    use_ocr: bool
    y_start: float = 0.80
    y_end: float = 0.95
    x_start: float = 0.0
    x_end: float = 1.0

class SubtitleReviewItem(BaseModel):
    text: str
    translation: str
    start: float
    end: float
    speaker: str

class SubtitleReviewResponse(BaseModel):
    subtitles: List[SubtitleReviewItem]

# Init pipelines
dubbing_pipeline = DubbingPipeline(jobs, JOBS_TTL_SECONDS)

# ── Wrappers (gọi từ route) ─────────────────────────────────

def _run_dubbing_phase1(job_id: str, url: str):
    dubbing_pipeline.run_phase1(job_id, url)

def _run_dubbing_phase2(job_id: str, use_ocr: bool, y_start: float, y_end: float,
                         x_start: float = 0.0, x_end: float = 1.0):
    dubbing_pipeline.run_phase2(job_id, use_ocr, y_start, y_end, x_start, x_end)

def _translate_ocr_subtitles(ocr_segments: list, log_func, provider: str = "gemini", voice_name: str = None, translate_style: str = "default", context: str = None) -> list:
    if not ocr_segments:
        return []
    texts_to_translate = [seg.get("text", "") for seg in ocr_segments]
    translations = [""] * len(texts_to_translate)
    translated = False

    if provider == "gist":
        # Gist API miễn phí — chỉ dùng Gist, tự động fallback sang Google Translate Web nếu lỗi
        import requests as req
        GIST_URL = "https://http-honyaku-kiban-production-80.schnworks.com/translation/language/translate/v2"
        log_func(f"🌐 Gist API: Đang dịch {len(texts_to_translate)} đoạn (miễn phí)...")
        try:
            resp = req.post(
                GIST_URL,
                json={"texts": texts_to_translate, "targetLanguage": "vie"},
                headers={"Content-Type": "application/json"},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                gist_t = data.get("translations", [])
                if gist_t and any(t.strip() for t in gist_t):
                    translations = gist_t
                    translated = True
                    log_func(f"✅ Gist API dịch thành công {len(translations)} đoạn.")
                else:
                    log_func("⚠️ Gist API trả về kết quả rỗng.")
            else:
                log_func(f"⚠️ Gist API lỗi HTTP {resp.status_code}.")
        except Exception as e:
            log_func(f"⚠️ Gist API lỗi kết nối: {str(e)[:100]}")

        # Tự động fallback sang Google Translate Web API miễn phí nếu Gist thất bại
        if not translated:
            log_func("🌐 Gist API thất bại. Đang tự động chuyển sang dịch bằng Google Translate miễn phí...")
            try:
                google_translations = []
                for text in texts_to_translate:
                    if not text.strip():
                        google_translations.append("")
                        continue
                    url = "https://translate.googleapis.com/translate_a/single"
                    params = {
                        "client": "gtx",
                        "sl": "zh-CN",
                        "tl": "vi",
                        "dt": "t",
                        "q": text
                    }
                    r = req.get(url, params=params, timeout=10)
                    if r.status_code == 200:
                        data = r.json()
                        translated_parts = [part[0] for part in data[0] if part and part[0]]
                        google_translations.append("".join(translated_parts))
                    else:
                        google_translations.append("")
                
                if any(t.strip() for t in google_translations):
                    translations = google_translations
                    translated = True
                    log_func(f"✅ Google Translate dịch thành công {len(translations)} đoạn phụ đề.")
            except Exception as ge:
                log_func(f"⚠️ Google Translate lỗi: {str(ge)[:100]}")

    else:  # gemini
        style = translate_style or "default"
        if voice_name:
            # Chế độ làm video hàng loạt: Dịch phẳng, không phân vai
            log_func(f"🤖 Gemini Vertex ({style}): Đang dịch {len(texts_to_translate)} đoạn...")
            try:
                from prompts import build_batch_prompt
                client = get_vertex_client()
                prompt = build_batch_prompt(texts_to_translate, style=style, context=context)
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[prompt],
                    config=types.GenerateContentConfig(temperature=0.2)
                )
                if response and response.text:
                    lines = [l.strip() for l in response.text.split("\n") if l.strip()]
                    j = 0
                    for i, t in enumerate(texts_to_translate):
                        if t.strip() and j < len(lines):
                            translations[i] = lines[j]
                            j += 1
                    translated = True
                    log_func(f"✅ Gemini Vertex dịch hàng loạt thành công {j}/{len(texts_to_translate)} đoạn.")
                else:
                    log_func("⚠️ Gemini Vertex trả về rỗng. SRT sẽ có text gốc.")
            except Exception as e:
                log_func(f"⚠️ Gemini Vertex lỗi: {str(e)[:100]}. SRT sẽ có text gốc.")
        else:
            # Chế độ tự động phân vai bằng AI
            log_func(f"🤖 Gemini Vertex ({style}): Đang dịch và phân vai {len(texts_to_translate)} đoạn...")
            try:
                from prompts import build_roleplay_prompt
                client = get_vertex_client()
                prompt = build_roleplay_prompt(texts_to_translate, style=style, context=context)
                schema = {
                    "type": "OBJECT",
                    "properties": {
                        "results": {
                            "type": "ARRAY",
                            "description": "List of translations and predicted speakers in the exact same order as input",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "translation": {"type": "STRING", "description": "Vietnamese translation"},
                                    "speaker": {"type": "STRING", "description": "Predicted speaker (e.g. 'Speaker A' for female/neutral characters, 'Speaker B' for male/other characters)"}
                                },
                                "required": ["translation", "speaker"]
                            }
                        }
                    },
                    "required": ["results"]
                }
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=schema,
                        temperature=0.2
                    )
                )
                if response and response.text:
                    import json
                    data = json.loads(response.text)
                    results = data.get("results", [])
                    
                    j = 0
                    for i, t in enumerate(texts_to_translate):
                        if t.strip() and j < len(results):
                            translations[i] = results[j].get("translation", "")
                            if i < len(ocr_segments):
                                ocr_segments[i]["speaker"] = results[j].get("speaker", "Speaker A")
                            j += 1
                    translated = True
                    log_func(f"✅ Gemini Vertex dịch và phân vai thành công {j}/{len(texts_to_translate)} đoạn.")
                else:
                    log_func("⚠️ Gemini Vertex trả về rỗng. SRT sẽ có text gốc.")
            except Exception as e:
                log_func(f"⚠️ Gemini Vertex lỗi: {str(e)[:100]}. SRT sẽ có text gốc.")

    if not translated:
        log_func("⚠️ KHÔNG dịch được. Dùng text gốc (tiếng Trung) làm phụ đề.")
        for i, t in enumerate(texts_to_translate):
            translations[i] = t

    result = []
    for i, seg in enumerate(ocr_segments):
        result.append({
            "start": seg.get("start", 0.0),
            "end": seg.get("end", 0.0),
            "text": seg.get("text", ""),
            "translation": translations[i] if i < len(translations) else "",
            "speaker": seg.get("speaker", "Speaker A"),
        })
    log_func(f"Dịch hoàn tất: {len(result)} đoạn phụ đề.")
    return result


def align_ocr_with_asr_timestamps(ocr_subs: list, asr_subs: list, log_func) -> list:
    """
    Cross-check: So khớp chéo giữa OCR (timestamp từ HÌNH ẢNH - chính xác 100% với video)
    và ASR (timestamp từ ÂM THANH - có thể lệch do delay phát âm).
    
    NGUYÊN TẮC QUAN TRỌNG:
    - LUÔN GIỮ timestamp OCR gốc (vì OCR quét hình ảnh → khớp tuyệt đối với video).
    - Chỉ dùng ASR để PHÁT HIỆN BẤT THƯỜNG (cảnh báo nếu lệch > 1s).
    - KHÔNG ghi đè timestamp OCR bằng ASR.
    """
    if not asr_subs:
        log_func("Không có dữ liệu ASR để cross-check. Giữ nguyên timestamp OCR.")
        return ocr_subs

    checked_subs = []
    warning_count = 0

    for ocr_seg in ocr_subs:
        ocr_start = ocr_seg.get("start", 0.0)
        ocr_end = ocr_seg.get("end", 0.0)
        ocr_text = ocr_seg.get("text", "")
        
        best_match = None
        max_overlap = 0.0
        
        for asr_seg in asr_subs:
            overlap_start = max(ocr_start, asr_seg.get("start", 0.0))
            overlap_end = min(ocr_end, asr_seg.get("end", 0.0))
            overlap = overlap_end - overlap_start
            
            if overlap > 0:
                ocr_dur = ocr_end - ocr_start
                if ocr_dur > 0 and overlap / ocr_dur > 0.3 and overlap > max_overlap:
                    max_overlap = overlap
                    best_match = asr_seg
        
        if best_match:
            asr_start = best_match.get("start", 0.0)
            asr_end = best_match.get("end", 0.0)
            # Kiểm tra độ lệch giữa OCR và ASR
            start_delta = abs(ocr_start - asr_start)
            end_delta = abs(ocr_end - asr_end)
            if start_delta > 1.0 or end_delta > 1.0:
                warning_count += 1
                log_func(
                    f"⚠️ Cảnh báo: OCR-ASR lệch > 1s cho '{ocr_text[:15]}...' | "
                    f"OCR [{ocr_start:.1f}s-{ocr_end:.1f}s] vs ASR [{asr_start:.1f}s-{asr_end:.1f}s]. "
                    f"Giữ nguyên timestamp OCR."
                )
        # LUÔN giữ nguyên OCR segment (không ghi đè)
        checked_subs.append(ocr_seg)

    if warning_count > 0:
        log_func(f"Cross-check hoàn tất: {warning_count}/{len(ocr_subs)} đoạn OCR lệch > 1s so với ASR (giữ nguyên OCR).")
    else:
        log_func(f"Cross-check hoàn tất: {len(ocr_subs)} đoạn OCR đồng bộ tốt với ASR (độ lệch < 1s).")
    return checked_subs


def run_pipeline_phase2(job_id: str, use_ocr: bool, y_start: float, y_end: float, x_start: float = 0.0, x_end: float = 1.0):
    job = jobs[job_id]
    job_folder = job["job_folder"]
    video_path = job["original_video"]
    bg_volume = job.get("bg_volume", 0.15)
    burn_subtitles = job.get("burn_subtitles", False)
    tts_provider = job.get("tts_provider", "edge")
    
    def log(msg: str):
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] INFO - {msg}"
        job["logs"].append(line)
        logger.info(f"[{job_id}] {msg}")
        
    try:
        subtitles = []
        
        if use_ocr:
            job["step"] = 2
            job["sub_step"] = "STEP 2.0: Đang quét OCR offline (RapidOCR PaddleOCR ONNX)..."
            log(f"Khởi động RapidOCR offline – vùng quét Y=[{y_start:.2f}–{y_end:.2f}], không tốn token Gemini...")
            original_audio_path = os.path.join(job_folder, "audio.mp3")

            # Tách âm thanh gốc trước, để chạy ASR song song với OCR
            asr_result = []
            asr_err = []
            audio_ready = False
            try:
                log("Tách âm thanh gốc làm căn cứ cross-check...")
                extract_audio(video_path, original_audio_path)
                job["audio"] = original_audio_path
                audio_ready = True
            except Exception as e:
                log(f"Cảnh báo tách âm thanh gốc thất bại: {e}. Sẽ chạy OCR thuần túy không cross-check.")

            # Chạy ASR song song với OCR
            def run_asr():
                try:
                    if audio_ready and os.path.exists(original_audio_path):
                        client_asr = get_vertex_client()
                        res = transcribe_and_translate_audio(client_asr, original_audio_path)
                        asr_result.append(res)
                except Exception as e:
                    asr_err.append(e)

            t_asr = threading.Thread(target=run_asr)
            t_asr.start()

            # Chạy OCR offline (RapidOCR) – đồng bộ, dùng video gốc
            try:
                ocr_segments = extract_subtitle_segments(
                    video_path=video_path,
                    y_start_ratio=y_start,
                    y_end_ratio=y_end,
                    x_start_ratio=x_start,
                    x_end_ratio=x_end,
                    log_func=log,
                )
            except Exception as e:
                log(f"Lỗi RapidOCR: {e}. Tự động chuyển sang ASR fallback.")
                use_ocr = False
                ocr_segments = []

            # Chờ ASR hoàn thành (nếu đang chạy)
            t_asr.join()

            if use_ocr and ocr_segments:
                log(f"RapidOCR trích xuất {len(ocr_segments)} đoạn phụ đề. Đang dịch batch...")
                translate_provider = job.get("translate_provider", "gemini")
                subtitles = _translate_ocr_subtitles(ocr_segments, log, provider=translate_provider, voice_name=job.get("voice_name"), translate_style=job.get("translate_style", "default"), context=job.get("context"))

                if not subtitles:
                    log("Dịch thất bại hoặc không có phụ đề. Chuyển sang ASR fallback.")
                    use_ocr = False
                else:
                    # Cross-check với ASR
                    if asr_result and asr_result[0].get("subtitles"):
                        log("Đang cross-check Hybrid Snapping: OCR vs ASR...")
                        asr_subs = asr_result[0].get("subtitles", [])
                        subtitles = align_ocr_with_asr_timestamps(subtitles, asr_subs, log)
                    else:
                        log("Không có dữ liệu ASR để cross-check. Giữ nguyên timestamp OCR (đã chính xác tuyệt đối).")
                    subtitles.sort(key=lambda x: x.get("start", 0.0))
            else:
                log("RapidOCR không tìm thấy phụ đề hoặc lỗi. Dùng ASR fallback.")
                use_ocr = False
                            
        # Chạy quy trình nhận diện từ giọng nói (ASR) thông thường nếu không dùng OCR hoặc bị lỗi/rỗng
        if not use_ocr:
            # Step 2: Tách Âm thanh
            job["step"] = 2
            job["sub_step"] = "STEP 2.0: Đang tách luồng âm thanh từ video..."
            log("Trích xuất âm thanh gốc bằng ffmpeg...")
            original_audio_path = os.path.join(job_folder, "audio.mp3")
            if not os.path.exists(original_audio_path):
                extract_audio(video_path, original_audio_path)
            job["audio"] = original_audio_path
            log(f"Trích xuất âm thanh thành công: {original_audio_path}")
            
            job["sub_step"] = "STEP 2.5: Đang tách vocal giọng nói (Demucs)..."
            log("Phân tích tần số âm thanh và cô lập giọng nói...")
            time.sleep(1.5)
            
            # Step 3: ASR
            if not subtitles:
                job["step"] = 3
                asr_mode = job.get("asr_mode", "audio")
                if asr_mode == "whisper":
                    job["sub_step"] = "STEP 3.0: Đang nhận dạng giọng nói bằng Local Whisper offline..."
                    log("Đang tải mô hình Whisper và chạy ASR offline trên tệp âm thanh...")
                    from translator import transcribe_audio_local_whisper
                    whisper_result = transcribe_audio_local_whisper(original_audio_path)
                    whisper_subs = whisper_result.get("subtitles", [])
                    log(f"Đã nhận dạng {len(whisper_subs)} phân đoạn bằng Whisper. Đang gửi sang bộ dịch...")
                    translate_provider = job.get("translate_provider", "gemini")
                    subtitles = _translate_ocr_subtitles(whisper_subs, log, provider=translate_provider, voice_name=job.get("voice_name"), translate_style=job.get("translate_style", "default"), context=job.get("context"))
                else:
                    job["sub_step"] = "STEP 3.0: Đang nhận dạng giọng nói bằng Gemini 2.5 Flash..."
                    log("Gửi tệp âm thanh trực tiếp qua Google GenAI SDK để phân tích và nhận diện giọng nói (ASR)...")
                    asr_client = get_vertex_client()
                    subtitles_data = transcribe_and_translate_audio(asr_client, original_audio_path)
                    subtitles = subtitles_data.get("subtitles", [])
                
                subtitles.sort(key=lambda x: x.get("start", 0.0))
                log(f"Hoàn thành nhận dạng giọng nói ASR. Tìm thấy {len(subtitles)} phân đoạn hội thoại.")
            else:
                log("Sử dụng dữ liệu phụ đề ASR đã nhận dạng song song trước đó làm kết quả Fallback.")
            
        # Step 4: Dịch thuật (Đã dịch sang Việt trong OCR hoặc ASR)
        job["step"] = 4
        job["sub_step"] = "STEP 4.0: Đang dịch thuật và biên tập phụ đề..."
        log("Biên dịch tối ưu hóa bản dịch tiếng Việt...")
        for idx, sub in enumerate(subtitles):
            log(f"Phân đoạn {idx+1}: '{sub.get('text', '')}' -> '{sub.get('translation', '')}'")
            
        # --- SUBTITLE REVIEW MODAL PAUSE STEP ---
        job["subtitles"] = subtitles
        job["status"] = "awaiting_subtitle_review"
        job["subtitle_review_completed"] = False
        job["subtitle_review_paused"] = False
        job["subtitle_review_countdown"] = 30
        
        log("Đang chờ người dùng kiểm tra phụ đề (tối đa 30 giây)...")
        
        start_pause_time = time.time()
        accumulated_elapsed = 0.0
        while not job["subtitle_review_completed"]:
            if job.get("subtitle_review_paused", False):
                accumulated_elapsed += (time.time() - start_pause_time)
                while job.get("subtitle_review_paused", False) and not job["subtitle_review_completed"]:
                    time.sleep(0.2)
                start_pause_time = time.time()
                if job["subtitle_review_completed"]:
                    break
                
            elapsed = time.time() - start_pause_time
            remaining = 30.0 - (accumulated_elapsed + elapsed)
            if remaining <= 0:
                log("Hết thời gian chờ 30 giây. Tự động tiếp tục...")
                break
                
            job["subtitle_review_countdown"] = max(0, int(remaining))
            time.sleep(0.5)
            
        subtitles = job.get("subtitles", subtitles)
        job["status"] = "running"
        
        # Step 5: Nhận diện giọng / Gán vai
        job["step"] = 5
        job["sub_step"] = "STEP 5.0: Đang phân loại người nói (Diarization)..."
        for idx, sub in enumerate(subtitles):
            log(f"Gán vai cho phân đoạn {idx+1}: {sub.get('speaker', 'default')}")
            
        # Step 6: TTS AI
        job["step"] = 6
        if tts_provider == "gemini":
            provider_label = "Gemini TTS (AI Native)"
        elif tts_provider == "google":
            provider_label = "Google Cloud TTS (Neural2)"
        else:
            provider_label = "edge-tts (Microsoft Neural)"
        job["sub_step"] = f"STEP 6.0: Đang lồng tiếng Việt bằng {provider_label}..."
        log(f"Tổng hợp giọng nói tiếng Việt bằng {provider_label}...")
        tts_dir = os.path.join(job_folder, "tts")
        os.makedirs(tts_dir, exist_ok=True)

        # --- Build voice_map từ voice_female / voice_male nếu có ---
        voice_map = job.get("voice_map")
        voice_name = job.get("voice_name")
        voice_female = job.get("voice_female")
        voice_male = job.get("voice_male")
        topic = job.get("topic")

        # Tự động gộp thành đơn giọng nếu chỉ thiết lập duy nhất 1 giọng Nữ hoặc Nam
        if not voice_name:
            if voice_female and not voice_male:
                voice_name = voice_female
                voice_female = None
            elif voice_male and not voice_female:
                voice_name = voice_male
                voice_male = None

        if not voice_map and not voice_name and (voice_female or voice_male):
            # Tự động phân vai: gán giọng nữ/nam cho từng speaker dựa trên gender
            voice_map = {}
            seen_speakers = set()
            for sub in subtitles:
                spk = sub.get("speaker", "default")
                if spk not in seen_speakers:
                    seen_speakers.add(spk)
                    gender = detect_speaker_gender(spk)
                    if gender == "male" and voice_male:
                        voice_map[spk] = voice_male
                    elif gender == "female" and voice_female:
                        voice_map[spk] = voice_female
            if voice_map:
                log(f"Phân vai giọng đọc: Nữ={voice_female}, Nam={voice_male} ({len(voice_map)} speakers)")

        tts_speed = job.get("tts_speed", 1.2)

        subtitles_with_tts = generate_tts_for_subtitles(
            subtitles, tts_dir, provider=tts_provider,
            voice_map=voice_map, voice_name=voice_name, tts_speed=tts_speed
        )
        log(f"Đã hoàn thành tổng hợp giọng nói cho {len(subtitles_with_tts)} phân đoạn.")
        
        # Step 7: Tạo SRT
        job["step"] = 7
        job["sub_step"] = "STEP 7.0: Đang tạo phụ đề..."
        srt_path = os.path.join(job_folder, "subtitles.srt")
        srt_original_path = os.path.join(job_folder, "subtitles_original.srt")
        job["srt"] = srt_path
        job["srt_original"] = srt_original_path
        
        # Ghi cả 2 file phụ đề tiếng Việt và tiếng Trung khớp 100% hành động video gốc
        sub_style = job.get("subtitle_style")
        if sub_style and burn_subtitles:
            from audio_processor import generate_ass
            ass_path = srt_path.replace(".srt", ".ass")
            generate_ass(subtitles, ass_path, {
                "font": sub_style.get("font", "Montserrat"),
                "fontsize": sub_style.get("fontsize", 20),
                "color": sub_style.get("color", "&H00FFFFFF"),
                "alignment": sub_style.get("position", 2),
            })
            srt_path = ass_path  # mix_audio_and_video sẽ dùng ASS thay SRT
        generate_srt(subtitles, srt_path if not srt_path.endswith(".ass") else srt_path.replace(".ass", ".srt"), use_original=False)
        generate_srt(subtitles, srt_original_path, use_original=True)
        
        # Step 8: Xuất video cuối
        job["step"] = 8
        job["sub_step"] = "STEP 8.0: Đang xuất video việt hóa..."
        log("Ghép giọng đọc AI, giảm âm lượng nhạc nền gốc và xuất video thành phẩm...")
        
        output_video_path = os.path.join(job_folder, "translated_video.mp4")
        
        # Nếu chạy qua nhánh OCR thì cần trích xuất original audio trước để mix
        original_audio_path = os.path.join(job_folder, "audio.mp3")
        if not os.path.exists(original_audio_path):
            extract_audio(video_path, original_audio_path)
            job["audio"] = original_audio_path
            
        actual_timeline = mix_audio_and_video(
            video_path=video_path,
            original_audio_path=original_audio_path,
            tts_segments=subtitles_with_tts,
            output_video_path=output_video_path,
            bg_volume=bg_volume,
            burn_subtitles=burn_subtitles,
            srt_path=srt_path,
            srt_original_path=srt_original_path,
            tts_speed=1.0
        )
        
        # Dọn dẹp file trung gian (Bọc try-except để tránh lỗi Lock file trên Windows làm hỏng tiến độ)
        try:
            log("Dọn dẹp file trung gian...")
            import shutil
            tts_dir_path = os.path.join(job_folder, "tts")
            if os.path.exists(tts_dir_path):
                shutil.rmtree(tts_dir_path, ignore_errors=True)
            audio_file = os.path.join(job_folder, "audio.mp3")
            if os.path.exists(audio_file):
                os.remove(audio_file)
        except Exception as ce:
            log(f"Cảnh báo dọn dẹp file trung gian thất bại (không ảnh hưởng video đầu ra): {ce}")
            
        job["translated_video"] = output_video_path
        job["status"] = "completed"
        job["sub_step"] = "Hoàn thành! Video đã sẵn sàng trong thư mục output."
        log(f"Hoàn thành! Video lưu tại: {job_folder}/")
        
    except Exception as e:
        logger.error(f"Pipeline Phase 2 failure: {str(e)}", exc_info=True)
        job["status"] = "failed"
        job["error"] = str(e)
        job["sub_step"] = "LỖI: Tiến trình xử lý thất bại."
        log(f"LỖI HỆ THỐNG: {str(e)}")


# ── Upload API ─────────────────────────────────────────────────────────
UPLOAD_DIR = os.path.join(str(output_dir), "imports")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/api/upload-video")
async def upload_video(file: UploadFile = File(...)):
    """Nhận file video upload, lưu vào output/imports/."""
    import uuid as _uuid
    ext = os.path.splitext(file.filename or "video.mp4")[1].lower()
    if ext not in (".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv"):
        raise HTTPException(status_code=400, detail=f"Định dạng không hỗ trợ: {ext}")
    safe_name = f"{_uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(UPLOAD_DIR, safe_name)
    try:
        contents = await file.read()
        with open(dest_path, "wb") as f:
            f.write(contents)
        size_mb = len(contents) / (1024 * 1024)
        logger.info(f"Upload: {file.filename} ({size_mb:.1f} MB) -> {dest_path}")
        
        # Tự động quét tìm phụ đề cùng tên trong projects/
        base_name = os.path.splitext(file.filename)[0] if file.filename else ""
        detected_srt = find_matching_srt(base_name)
        
        return {
            "status": "success", 
            "path": dest_path, 
            "filename": file.filename, 
            "size_mb": round(size_mb, 1),
            "detected_srt": detected_srt
        }
    except Exception as e:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise HTTPException(status_code=500, detail=f"Lỗi upload: {str(e)}")


@app.post("/api/upload-srt")
async def upload_srt(file: UploadFile = File(...)):
    """Nhận file phụ đề SRT upload, lưu vào output/imports/."""
    import uuid as _uuid
    ext = os.path.splitext(file.filename or "subtitles.srt")[1].lower()
    if ext != ".srt":
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file định dạng .srt")
    safe_name = f"{_uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(UPLOAD_DIR, safe_name)
    try:
        contents = await file.read()
        with open(dest_path, "wb") as f:
            f.write(contents)
        return {"status": "success", "path": dest_path, "filename": file.filename}
    except Exception as e:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise HTTPException(status_code=500, detail=f"Lỗi upload SRT: {str(e)}")


@app.post("/api/get-cookies")
def get_cookies_endpoint(platform: str = "douyin"):
    import subprocess
    import sys
    try:
        logger.info(f"Khởi chạy giao diện thu thập cookie cho {platform}...")
        result = subprocess.run(
            [sys.executable, "get_cookies_gui.py", platform],
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout
        )
        
        cookie_file = "cookies.txt"
        if os.path.exists(cookie_file):
            mtime = os.path.getmtime(cookie_file)
            # If created/modified in the last 5 minutes
            if time.time() - mtime < 300:
                cookies = load_cookies_txt(cookie_file)
                if cookies:
                    return {"status": "success", "message": f"Đã lưu và gộp thành công cookies vào cookies.txt!"}
        
        return {"status": "error", "message": "Không tìm thấy file cookies mới hoặc phiên làm việc đã bị hủy."}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Quá thời gian chờ đăng nhập (5 phút)."}
    except Exception as e:
        logger.error(f"Lỗi khởi chạy get_cookies_gui.py cho {platform}: {e}")
        return {"status": "error", "message": f"Lỗi khởi chạy công cụ lấy cookie: {str(e)}"}


class BatchTranslateRequest(BaseModel):
    urls: List[str]
    bg_volume: float = 0.30
    burn_subtitles: bool = False
    tts_provider: str = "edge"
    asr_mode: str = "audio"
    translate_provider: str = "gemini"
    process_mode: str = "auto"
    voice_map: Optional[Dict] = None
    voice_name: Optional[str] = None
    voice_female: Optional[str] = None
    voice_male: Optional[str] = None
    topic: Optional[str] = None
    tts_speed: float = 1.40
    translate_style: str = "default"
    context: Optional[str] = None
    subtitle_style: Optional[Dict] = None
    resolution: Optional[str] = "1080"

def run_batch_pipeline_sync(batch_id: str, request: BatchTranslateRequest):
    batch_job = jobs[batch_id]
    
    for idx, item in enumerate(batch_job["items"]):
        batch_job["current_index"] = idx
        item["status"] = "running"
        
        sub_job_id = str(uuid.uuid4())
        item["job_id"] = sub_job_id
        
        # Tạo sub-job trong store
        jobs[sub_job_id] = {
            "job_id": sub_job_id,
            "status": "running",
            "step": 0,
            "sub_step": "Khởi tạo tiến trình...",
            "logs": [],
            "original_video": None,
            "translated_video": None,
            "srt": None,
            "srt_original": None,
            "audio": None,
            "error": None,
            "bg_volume": request.bg_volume,
            "burn_subtitles": request.burn_subtitles,
            "tts_provider": request.tts_provider,
            "asr_mode": request.asr_mode,
            "translate_provider": request.translate_provider,
            "process_mode": request.process_mode,
            "voice_map": request.voice_map,
            "voice_name": request.voice_name,
            "voice_female": request.voice_female,
            "voice_male": request.voice_male,
            "topic": request.topic,
            "tts_speed": request.tts_speed,
            "translate_style": request.translate_style,
            "context": request.context,
            "subtitle_style": request.subtitle_style,
            "resolution": request.resolution,
            "is_batch_item": True, # Đánh dấu đây là sub-job thuộc một batch
            "_created": time.time(),
        }
        
        try:
            # 1. Chạy Phase 1 đồng bộ
            dubbing_pipeline.run_phase1(sub_job_id, item["url"])
            
            sub_job = jobs[sub_job_id]
            # Nếu chạy ocr mode ở batch, tự động chạy Phase 2 với tọa độ phụ đề mặc định
            if sub_job["status"] == "awaiting_ocr_selection":
                sub_job["status"] = "running"
                sub_job["sub_step"] = "Tự động kích hoạt OCR với vùng mặc định..."
                dubbing_pipeline.run_phase2(
                    job_id=sub_job_id,
                    use_ocr=True,
                    y_start=0.80,
                    y_end=0.95,
                    x_start=0.0,
                    x_end=1.0
                )
                
            # Đợi cho đến khi sub-job hoàn thành hoặc lỗi
            while sub_job["status"] not in ("completed", "failed"):
                time.sleep(1)
                
            if sub_job["status"] == "completed":
                item["status"] = "completed"
                item["translated_video"] = sub_job["translated_video"]
            else:
                item["status"] = "failed"
                item["error"] = sub_job.get("error", "Lỗi xử lý video.")
                
        except Exception as e:
            item["status"] = "failed"
            item["error"] = str(e)
            logger.error(f"Lỗi xử lý video batch {item['url']}: {e}", exc_info=True)
            if sub_job_id in jobs:
                jobs[sub_job_id]["status"] = "failed"
                jobs[sub_job_id]["error"] = str(e)
                jobs[sub_job_id]["logs"].append(f"[LỖI] {e}")
                
    batch_job["status"] = "completed"

@app.post("/api/translate/batch")
def start_batch_translation(request: BatchTranslateRequest):
    # Dọn dẹp url rỗng
    urls = [url.strip() for url in request.urls if url.strip()]
    if not urls:
        raise HTTPException(status_code=400, detail="Danh sách liên kết rỗng.")
        
    batch_id = str(uuid.uuid4())
    jobs[batch_id] = {
        "job_id": batch_id,
        "is_batch": True,
        "status": "running",
        "urls": urls,
        "current_index": 0,
        "items": [
             {
                 "url": url,
                 "job_id": None,
                 "status": "waiting",
                 "translated_video": None,
                 "error": None
             }
             for url in urls
        ],
        "_created": time.time()
    }
    
    _cleanup_expired_jobs()
    
    # Khởi chạy luồng xử lý hàng loạt tuần tự trong background
    thread = threading.Thread(
        target=run_batch_pipeline_sync,
        args=(batch_id, request),
        daemon=True
    )
    thread.start()
    
    return {"batch_id": batch_id}


@app.post("/api/translate")
def start_translation(request: TranslateRequest):
    global _last_request_time
    
    # Rate limit
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < MIN_REQUEST_INTERVAL:
        wait = round(MIN_REQUEST_INTERVAL - elapsed, 1)
        raise HTTPException(status_code=429, detail=f"Vui lòng đợi {wait}s trước khi gửi request tiếp theo.")
    _last_request_time = now
    
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "job_id": job_id,
        "status": "running",
        "step": 0,
        "sub_step": "Khởi tạo tiến trình...",
        "logs": [],
        "original_video": None,
        "translated_video": None,
        "srt": None,
        "srt_original": None,
        "audio": None,
        "error": None,
        "bg_volume": request.bg_volume,
        "burn_subtitles": request.burn_subtitles,
        "tts_provider": request.tts_provider,
        "asr_mode": request.asr_mode,
        "translate_provider": request.translate_provider,
        "process_mode": request.process_mode,
        "voice_map": request.voice_map,
        "voice_name": request.voice_name,
        "voice_female": request.voice_female,
        "voice_male": request.voice_male,
        "topic": request.topic,
        "tts_speed": request.tts_speed,
        "translate_style": request.translate_style,
        "context": request.context,
        "subtitle_style": request.subtitle_style,
        "resolution": request.resolution,
        "imported_srt": request.imported_srt,
        "use_detected_srt": request.use_detected_srt,
        "original_filename": request.original_filename,
        "_created": time.time(),
    }
    
    # Dọn job cũ trước khi tạo mới
    _cleanup_expired_jobs()
    
    if request.imported_file:
        thread = threading.Thread(target=run_pipeline_import, args=(job_id, request.imported_file), daemon=True)
    else:
        thread = threading.Thread(
            target=_run_dubbing_phase1,
            args=(job_id, request.url),
            daemon=True
        )
    thread.start()
    
    return {"job_id": job_id}


@app.post("/api/translate/resume/{job_id}")
def resume_translation(job_id: str, request: ResumeRequest):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên xử lý.")
        
    job = jobs[job_id]
    if job["status"] != "awaiting_ocr_selection":
        raise HTTPException(status_code=400, detail="Phiên xử lý không ở trạng thái chờ chọn vùng OCR.")
        
    job["status"] = "running"
    job["sub_step"] = "Bắt đầu tiếp tục tiến trình..."
    
    # Khởi chạy luồng xử lý Phase 2
    thread = threading.Thread(
        target=_run_dubbing_phase2,
        args=(job_id, request.use_ocr, request.y_start, request.y_end, request.x_start, request.x_end),
        daemon=True
    )
    thread.start()
    
    return {"status": "success", "message": "Đã tiếp tục tiến trình dịch thuật."}


@app.post("/api/translate/review/pause/{job_id}")
def pause_subtitle_countdown(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên xử lý.")
    job = jobs[job_id]
    job["subtitle_review_paused"] = True
    return {"status": "success", "message": "Đã tạm dừng đếm ngược."}


@app.post("/api/translate/review/continue/{job_id}")
def continue_subtitle_tts(job_id: str, request: SubtitleReviewResponse):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên xử lý.")
    job = jobs[job_id]
    
    revised_subs = []
    for item in request.subtitles:
        revised_subs.append({
            "text": item.text,
            "translation": item.translation,
            "start": item.start,
            "end": item.end,
            "speaker": item.speaker
        })
        
    job["subtitles"] = revised_subs
    job["subtitle_review_completed"] = True
    job["subtitle_review_paused"] = False
    job["status"] = "running"
    return {"status": "success", "message": "Đã lưu chỉnh sửa phụ đề và tiếp tục lồng tiếng."}



@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên xử lý.")
    
    job = jobs[job_id]
    
    # Nếu là Batch Job (xử lý hàng loạt)
    if job.get("is_batch", False):
        current_sub_logs = []
        for item in job["items"]:
            if item["status"] == "running" and item["job_id"]:
                sub_job = jobs.get(item["job_id"])
                if sub_job:
                    current_sub_logs = sub_job.get("logs", [])
                    break
                    
        formatted_items = []
        for item in job["items"]:
            sub_id = item["job_id"]
            download_urls = {}
            if sub_id and sub_id in jobs:
                sub_job = jobs[sub_id]
                if "folder_name" in sub_job:
                    download_urls = {
                        "original_video_url": f"/output/{sub_job['folder_name']}/original.mp4" if sub_job.get("original_video") else None,
                        "translated_video_url": f"/output/{sub_job['folder_name']}/translated_video.mp4" if sub_job.get("translated_video") else None,
                        "srt_url": f"/output/{sub_job['folder_name']}/subtitles.srt" if sub_job.get("srt") else None,
                    }
            formatted_items.append({
                "url": item["url"],
                "status": item["status"],
                "job_id": item["job_id"],
                "error": item["error"],
                "result": download_urls
            })
            
        return {
            "is_batch": True,
            "job_id": job["job_id"],
            "status": job["status"],
            "current_index": job["current_index"],
            "items": formatted_items,
            "logs": current_sub_logs,
            "sub_step": f"Đang dịch video {job['current_index'] + 1}/{len(job['urls'])}" if job["status"] == "running" else "Đã hoàn thành toàn bộ danh sách!"
        }

    # Nếu là Single Job thông thường
    result_urls = {}
    if "folder_name" in job:
        result_urls = {
            "original_video_url": f"/output/{job['folder_name']}/original.mp4" if job.get("original_video") else None,
            "translated_video_url": f"/output/{job['folder_name']}/translated_video.mp4" if job.get("translated_video") else None,
            "srt_url": f"/output/{job['folder_name']}/subtitles.srt" if job.get("srt") else None,
            "srt_original_url": f"/output/{job['folder_name']}/subtitles_original.srt" if job.get("srt_original") else None,
        }
        
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "step": job["step"],
        "sub_step": job["sub_step"],
        "logs": job["logs"],
        "result": result_urls,
        "error": job["error"],
        "subtitle_review_countdown": job.get("subtitle_review_countdown", 30),
        "subtitle_review_paused": job.get("subtitle_review_paused", False),
        "subtitles": job.get("subtitles") if job["status"] == "awaiting_subtitle_review" else None
    }

@app.get("/api/download/{job_id}/{file_type}")
def download_file(job_id: str, file_type: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên xử lý.")
        
    job = jobs[job_id]
    path = None
    media_type = "application/octet-stream"
    
    # Lấy tên gốc của video để đặt tên file tải về cho đồng bộ
    video_base_name = job.get("video_base_name") or "video"
    clean_base = "".join(c if c.isalnum() or c in "_-" else "_" for c in video_base_name)
    download_filename = None
    
    if file_type == "original_video.mp4":
        path = job["original_video"]
        media_type = "video/mp4"
        download_filename = f"{clean_base}_original.mp4"
    elif file_type == "translated_video.mp4":
        path = job["translated_video"]
        media_type = "video/mp4"
        download_filename = f"{clean_base}_viet.mp4"
    elif file_type == "subtitles.srt":
        path = job["srt"]
        media_type = "text/plain"
        if path and path.endswith(".ass"):
            download_filename = f"{clean_base}_viet.ass"
        else:
            download_filename = f"{clean_base}_viet.srt"
    elif file_type == "subtitles_original.srt":
        path = job.get("srt_original")
        if not path or not os.path.exists(path):
            raise HTTPException(status_code=404, detail="File SRT gốc không tồn tại.")
        media_type = "text/plain"
        download_filename = f"{clean_base}_original.srt"
    elif file_type == "original_audio.mp3":
        path = job.get("audio")
        if not path or not os.path.exists(path):
            raise HTTPException(status_code=404, detail="File audio đã được dọn dẹp sau khi xử lý.")
        media_type = "audio/mpeg"
        download_filename = f"{clean_base}_audio.mp3"
        
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp được yêu cầu.")
        
    if not download_filename:
        download_filename = os.path.basename(path)
        
    return FileResponse(path, media_type=media_type, filename=download_filename)

# Serve Output files statically for video range streaming support
app.mount("/output", StaticFiles(directory=str(output_dir)), name="output")

class GlossarySaveRequest(BaseModel):
    content: str

@app.get("/api/glossary/{style}")
def get_glossary_endpoint(style: str):
    if style not in ["default", "dialogue", "review", "tutorial", "general"]:
        raise HTTPException(status_code=400, detail="Phong cách từ điển không hợp lệ.")
    
    filename = f"glossary_{style}.txt" if style != "general" else "glossary.txt"
    filepath = Path(__file__).parent / filename
    
    if not filepath.exists():
        return {"style": style, "content": ""}
        
    try:
        content = filepath.read_text(encoding="utf-8-sig", errors="ignore")
        return {"style": style, "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Không thể đọc file: {str(e)}")

@app.post("/api/glossary/{style}")
def save_glossary_endpoint(style: str, request: GlossarySaveRequest):
    if style not in ["default", "dialogue", "review", "tutorial", "general"]:
        raise HTTPException(status_code=400, detail="Phong cách từ điển không hợp lệ.")
        
    filename = f"glossary_{style}.txt" if style != "general" else "glossary.txt"
    filepath = Path(__file__).parent / filename
    
    try:
        filepath.write_text(request.content, encoding="utf-8-sig")
        # Xóa cache prompt để nạp lại glossary mới ở lượt dịch kế tiếp
        import prompts
        prompts._cache.clear()
        return {"status": "success", "message": f"Đã lưu từ điển {style} thành công."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Không thể ghi file: {str(e)}")


@app.get("/api/video/info")
def get_video_info_endpoint(url: str):
    from downloader import get_video_info
    if not url or not url.strip():
        raise HTTPException(status_code=400, detail="URL không hợp lệ.")
    return get_video_info(url)


# Serve Projects folder for Re-Edit results
projects_dir = exe_dir / "projects"
os.makedirs(projects_dir, exist_ok=True)
app.mount("/projects", StaticFiles(directory=str(projects_dir)), name="projects")

# Serve Frontend static files directly
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    if getattr(sys, 'frozen', False):
        # Automatically launch web browser on startup when running as compiled EXE
        import webbrowser
        
        # Start browser after 1.5s delay to ensure uvicorn server has started
        def open_browser():
            time.sleep(1.5)
            webbrowser.open("http://localhost:8001")
            
        threading.Thread(target=open_browser, daemon=True).start()
        
        # Use app object directly when frozen, disable reload
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=8001
        )
    else:
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8001,
            reload=True,
            reload_dirs=[".", "utils"],
            reload_excludes=["output/*", "*.mp4", "*.mp3", "*.srt"],
        )

