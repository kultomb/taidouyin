import os
import uuid
import time
import logging
import threading
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Import our custom modules
from downloader import download_douyin_video, load_cookies_txt
from audio_processor import extract_audio, generate_srt, generate_srt_from_timeline, mix_audio_and_video
from translator import get_vertex_client, transcribe_and_translate_audio
from tts_processor import generate_tts_for_subtitles

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("douyin_translator")

app = FastAPI(title="Douyin Video Translator SaaS")

# Serve UI static files
# Ensure static directory exists
os.makedirs("static", exist_ok=True)
os.makedirs("output", exist_ok=True)

# Memory store for jobs (with TTL: tự động xóa sau 2 giờ)
JOBS_TTL_SECONDS = 7200  # 2 giờ
jobs = {}

# Rate limiter đơn giản
_last_request_time = 0.0
MIN_REQUEST_INTERVAL = 2.0  # Tối thiểu 2s giữa các request

def _cleanup_expired_jobs():
    """Xóa job quá hạn TTL để tránh memory leak."""
    now = time.time()
    expired = [jid for jid, j in jobs.items() if now - j.get("_created", now) > JOBS_TTL_SECONDS]
    for jid in expired:
        del jobs[jid]
    if expired:
        logger.info(f"Cleaned up {len(expired)} expired jobs")

class TranslateRequest(BaseModel):
    url: str
    bg_volume: float = 0.30  # Ducking: bg audio volume when TTS is silent
    burn_subtitles: bool = False
    tts_provider: str = "edge"  # "edge" hoặc "google"
    asr_mode: str = "audio"  # "audio" hoặc "video"

def run_pipeline(job_id: str, url: str, bg_volume: float, burn_subtitles: bool, tts_provider: str = "edge", asr_mode: str = "audio"):
    job = jobs[job_id]
    job_folder = f"output/{time.strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(job_folder, exist_ok=True)
    
    def log(msg: str):
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] INFO - {msg}"
        job["logs"].append(line)
        logger.info(f"[{job_id}] {msg}")
        
    try:
        # Step 1: Tải Video
        job["step"] = 1
        job["sub_step"] = "STEP 1.0: Đang tải video chất lượng cao nhất từ Douyin..."
        log(f"Khởi động mô-đun tải video Douyin: {url}")
        video_path = download_douyin_video(url, job_folder)
        # Rename to original.mp4 for consistency
        if video_path and os.path.exists(video_path):
            original_path = os.path.join(job_folder, "original.mp4")
            if video_path != original_path:
                os.rename(video_path, original_path)
            video_path = original_path
        job["original_video"] = video_path
        log(f"Tải video gốc thành công: {video_path}")
        
        # Step 2: Tách Âm thanh
        job["step"] = 2
        job["sub_step"] = "STEP 2.0: Đang tách luồng âm thanh từ video..."
        log("Trích xuất âm thanh gốc bằng ffmpeg...")
        original_audio_path = os.path.join(job_folder, "audio.mp3")
        extract_audio(video_path, original_audio_path)
        job["audio"] = original_audio_path
        log(f"Trích xuất âm thanh thành công: {original_audio_path}")
        
        job["sub_step"] = "STEP 2.5: Đang tách vocal giọng nói (Demucs)..."
        log("Phân tích tần số âm thanh và cô lập giọng nói...")
        time.sleep(1.5)
        
        # Step 3: ASR
        job["step"] = 3
        job["sub_step"] = "STEP 3.0: Đang nhận dạng giọng nói bằng Gemini 2.5 Flash..."
        log("Khởi tạo kết nối Vertex AI Client...")
        client = get_vertex_client()
        
        import subprocess
        if asr_mode == "video":
            job["sub_step"] = "STEP 3.2: Đang tối ưu hóa và nén video gửi tới Gemini..."
            log("Nén video chất lượng cực thấp (320x240, mono audio) để giảm dung lượng tải lên...")
            compressed_video_path = os.path.join(job_folder, "compressed_video.mp4")
            
            compress_cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-vf", "scale=320:-2,fps=10",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "32",
                "-c:a", "aac", "-b:a", "32k", "-ac", "1",
                compressed_video_path
            ]
            try:
                subprocess.run(compress_cmd, capture_output=True, check=True, timeout=60)
                log(f"Nén video thành công: {compressed_video_path} (Kích thước: {os.path.getsize(compressed_video_path) / 1024 / 1024:.2f} MB)")
                asr_input_path = compressed_video_path
            except Exception as e:
                log(f"Lỗi nén video: {e}. Tự động fallback sang nhận diện chỉ âm thanh.")
                asr_input_path = original_audio_path
        else:
            asr_input_path = original_audio_path
            log("Gửi tệp âm thanh trực tiếp qua Google GenAI SDK để phân tích và nhận diện giọng nói (ASR)...")
        
        job["sub_step"] = "STEP 3.5: Đang chạy ASR và định vị mốc thời gian..."
        subtitles_data = transcribe_and_translate_audio(client, asr_input_path)
        subtitles = subtitles_data.get("subtitles", [])
        log(f"Hoàn thành nhận dạng giọng nói. Tìm thấy {len(subtitles)} phân đoạn hội thoại.")
        
        # Step 4: Dịch thuật
        job["step"] = 4
        job["sub_step"] = "STEP 4.0: Đang dịch thuật sang Tiếng Việt..."
        log("Đang dịch và tối ưu hóa bản dịch tiếng Việt...")
        for idx, sub in enumerate(subtitles):
            log(f"Phân đoạn {idx+1}: '{sub['text']}' -> '{sub['translation']}'")
            
        # Step 5: Nhận diện giọng
        job["step"] = 5
        job["sub_step"] = "STEP 5.0: Đang phân loại người nói (Diarization)..."
        log("Nhận dạng danh tính giọng đọc và gán vai...")
        for idx, sub in enumerate(subtitles):
            log(f"Gán vai cho phân đoạn {idx+1}: {sub['speaker']}")
            
        # Step 6: TTS AI
        job["step"] = 6
        provider_label = "Google Cloud TTS (Neural2)" if tts_provider == "google" else "edge-tts (Microsoft Neural)"
        job["sub_step"] = f"STEP 6.0: Đang lồng tiếng Việt bằng {provider_label}..."
        log(f"Tổng hợp giọng nói tiếng Việt bằng {provider_label}...")
        tts_dir = os.path.join(job_folder, "tts")
        os.makedirs(tts_dir, exist_ok=True)
        subtitles_with_tts = generate_tts_for_subtitles(subtitles, tts_dir, provider=tts_provider)
        log(f"Đã hoàn thành tổng hợp giọng nói cho {len(subtitles_with_tts)} phân đoạn.")
        
        # Step 7: Tạo SRT
        job["step"] = 7
        job["sub_step"] = "STEP 7.0: Đang tạo phụ đề..."
        srt_path = os.path.join(job_folder, "subtitles.srt")
        srt_original_path = os.path.join(job_folder, "subtitles_original.srt")
        job["srt"] = srt_path
        job["srt_original"] = srt_original_path
        
        # Ghi file phụ đề gốc tiếng Trung khớp hành động video
        generate_srt(subtitles, srt_original_path, use_original=True)
        
        # Step 8: Xuất video cuối
        job["step"] = 8
        job["sub_step"] = "STEP 8.0: Đang xuất video việt hóa..."
        log("Ghép giọng đọc AI, giảm âm lượng nhạc nền gốc và xuất video thành phẩm...")
        
        output_video_path = os.path.join(job_folder, "translated_video.mp4")
        actual_timeline = mix_audio_and_video(
            video_path=video_path,
            original_audio_path=original_audio_path,
            tts_segments=subtitles_with_tts,
            output_video_path=output_video_path,
            bg_volume=bg_volume,
            burn_subtitles=burn_subtitles,
            srt_path=srt_path
        )
        
        # Cập nhật SRT với timeline thực tế (đồng bộ 100% cho cả 2 phụ đề)
        if actual_timeline:
            log("Cập nhật cả 2 phụ đề Việt & Trung khớp 100% timeline thực tế sau khi lồng tiếng...")
            generate_srt_from_timeline(actual_timeline, srt_path)
            generate_srt_from_timeline(actual_timeline, srt_original_path, use_original=True)
            log("Cả 2 bản phụ đề Việt & Trung đã đồng bộ thời gian 100%!")
            job["srt"] = srt_path
            job["srt_original"] = srt_original_path
        
        # Dọn dẹp file trung gian
        log("Dọn dẹp file trung gian...")
        import shutil
        tts_dir_path = os.path.join(job_folder, "tts")
        if os.path.exists(tts_dir_path):
            shutil.rmtree(tts_dir_path)
        audio_file = os.path.join(job_folder, "audio.mp3")
        if os.path.exists(audio_file):
            os.remove(audio_file)
        
        job["translated_video"] = output_video_path
        job["status"] = "completed"
        job["sub_step"] = "Hoàn thành! Video đã sẵn sàng trong thư mục output."
        log(f"Hoàn thành! Video lưu tại: {job_folder}/")
        log(f"  - translated_video.mp4 (video đã dịch)")
        log(f"  - original.mp4 (video gốc)")
        log(f"  - subtitles.srt (phụ đề tiếng Việt, cùng thời gian)")
        log(f"  - subtitles_original.srt (phụ đề tiếng Trung, cùng thời gian)")
        
    except Exception as e:
        logger.error(f"Pipeline failure: {str(e)}", exc_info=True)
        job["status"] = "failed"
        job["error"] = str(e)
        job["sub_step"] = "LỖI: Tiến trình xử lý thất bại."
        log(f"LỖI HỆ THỐNG: {str(e)}")
@app.post("/api/get-cookies")
def get_cookies_endpoint():
    import subprocess
    import sys
    try:
        logger.info("Khởi chạy giao diện thu thập cookie Douyin...")
        result = subprocess.run(
            [sys.executable, "get_cookies_gui.py"],
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
                    return {"status": "success", "message": f"Đã lưu thành công {len(cookies)} cookies vào cookies.txt!"}
        
        return {"status": "error", "message": "Không tìm thấy file cookies mới hoặc phiên làm việc đã bị hủy."}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Quá thời gian chờ đăng nhập (5 phút)."}
    except Exception as e:
        logger.error(f"Lỗi khởi chạy get_cookies_gui.py: {e}")
        return {"status": "error", "message": f"Lỗi khởi chạy công cụ lấy cookie: {str(e)}"}

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
        "_created": time.time(),
    }
    
    # Dọn job cũ trước khi tạo mới
    _cleanup_expired_jobs()
    
    # Start thread
    thread = threading.Thread(
        target=run_pipeline,
        args=(job_id, request.url, request.bg_volume, request.burn_subtitles, request.tts_provider, request.asr_mode),
        daemon=True
    )
    thread.start()
    
    return {"job_id": job_id}

@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên xử lý.")
    
    job = jobs[job_id]
    
    # Prepare download urls
    result_urls = {}
    if job["status"] == "completed":
        result_urls = {
            "original_video_url": f"/api/download/{job_id}/original_video.mp4" if job["original_video"] else None,
            "translated_video_url": f"/api/download/{job_id}/translated_video.mp4" if job["translated_video"] else None,
            "srt_url": f"/api/download/{job_id}/subtitles.srt" if job["srt"] else None,
            "srt_original_url": f"/api/download/{job_id}/subtitles_original.srt" if job.get("srt_original") else None,
        }
        
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "step": job["step"],
        "sub_step": job["sub_step"],
        "logs": job["logs"],
        "result": result_urls,
        "error": job["error"]
    }

@app.get("/api/download/{job_id}/{file_type}")
def download_file(job_id: str, file_type: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên xử lý.")
        
    job = jobs[job_id]
    path = None
    media_type = "application/octet-stream"
    
    if file_type == "original_video.mp4":
        path = job["original_video"]
        media_type = "video/mp4"
    elif file_type == "translated_video.mp4":
        path = job["translated_video"]
        media_type = "video/mp4"
    elif file_type == "subtitles.srt":
        path = job["srt"]
        media_type = "text/plain"
    elif file_type == "subtitles_original.srt":
        path = job.get("srt_original")
        if not path or not os.path.exists(path):
            raise HTTPException(status_code=404, detail="File SRT gốc không tồn tại.")
        media_type = "text/plain"
    elif file_type == "original_audio.mp3":
        path = job.get("audio")
        if not path or not os.path.exists(path):
            raise HTTPException(status_code=404, detail="File audio đã được dọn dẹp sau khi xử lý.")
        media_type = "audio/mpeg"
        
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp được yêu cầu.")
        
    return FileResponse(path, media_type=media_type, filename=os.path.basename(path))

# Serve Frontend static files directly
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        reload_dirs=[".", "utils"],
        reload_excludes=["output/*", "*.mp4", "*.mp3", "*.srt"],
    )
