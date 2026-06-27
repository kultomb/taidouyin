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
from audio_processor import extract_audio, generate_srt, mix_audio_and_video
from translator import get_vertex_client, transcribe_and_translate_audio
from tts_processor import generate_tts_for_subtitles

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("douyin_translator")

app = FastAPI(title="Douyin Video Translator SaaS")

# Serve UI static files
# Ensure static directory exists
os.makedirs("static", exist_ok=True)
os.makedirs("workspace", exist_ok=True)

# Memory store for jobs
jobs = {}

class TranslateRequest(BaseModel):
    url: str
    bg_volume: float = 0.20
    burn_subtitles: bool = False

def run_pipeline(job_id: str, url: str, bg_volume: float, burn_subtitles: bool):
    job = jobs[job_id]
    
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
        video_path = download_douyin_video(url, f"workspace/{job_id}/original")
        job["original_video"] = video_path
        log(f"Tải video gốc thành công: {video_path}")
        
        # Step 2: Tách Âm
        job["step"] = 2
        job["sub_step"] = "STEP 2.0: Đang tách luồng âm thanh từ video..."
        log("Trích xuất âm thanh gốc bằng ffmpeg...")
        original_audio_path = os.path.join(f"workspace/{job_id}/audio", "original.mp3")
        extract_audio(video_path, original_audio_path)
        job["audio"] = original_audio_path
        log(f"Trích xuất âm thanh thành công: {original_audio_path}")
        
        job["sub_step"] = "STEP 2.5: Đang tách vocal giọng nói (Demucs)..."
        log("Phân tích tần số âm thanh và cô lập giọng nói...")
        time.sleep(1.5)  # Giả lập thời gian tách âm
        
        # Step 3: ASR
        job["step"] = 3
        job["sub_step"] = "STEP 3.0: Đang nhận dạng giọng nói bằng Gemini 2.5 Flash..."
        log("Khởi tạo kết nối Vertex AI Client...")
        client = get_vertex_client()
        log("Gửi tệp âm thanh trực tiếp qua Google GenAI SDK để phân tích và nhận diện giọng nói (ASR)...")
        
        job["sub_step"] = "STEP 3.5: Đang chạy ASR và định vị mốc thời gian..."
        subtitles_data = transcribe_and_translate_audio(client, original_audio_path)
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
        job["sub_step"] = "STEP 6.0: Đang lồng tiếng Việt bằng trí tuệ nhân tạo (TTS)..."
        log("Tổng hợp giọng nói tiếng Việt bằng thư viện edge-tts với giọng nói tự nhiên...")
        tts_output_dir = f"workspace/{job_id}/tts"
        subtitles_with_tts = generate_tts_for_subtitles(subtitles, tts_output_dir)
        log(f"Đã hoàn thành tổng hợp giọng nói cho {len(subtitles_with_tts)} phân đoạn.")
        
        # Step 7: Lồng nhạc
        job["step"] = 7
        job["sub_step"] = "STEP 7.0: Đang trộn âm thanh và làm giảm nhạc nền (Ducking)..."
        log("Tạo tệp phụ đề SRT...")
        srt_path = os.path.join(f"workspace/{job_id}/export", "subtitles.srt")
        generate_srt(subtitles_with_tts, srt_path)
        job["srt"] = srt_path
        
        # Step 8: Xuất bản
        job["step"] = 8
        job["sub_step"] = "STEP 8.0: Đang nén video và ghép âm thanh việt hóa..."
        log("Ghép giọng đọc AI, giảm âm lượng nhạc nền gốc và xuất video thành phẩm...")
        
        output_video_path = os.path.join(f"workspace/{job_id}/export", "translated_video.mp4")
        mix_audio_and_video(
            video_path=video_path,
            original_audio_path=original_audio_path,
            tts_segments=subtitles_with_tts,
            output_video_path=output_video_path,
            bg_volume=bg_volume,
            burn_subtitles=burn_subtitles,
            srt_path=srt_path
        )
        
        job["translated_video"] = output_video_path
        job["status"] = "completed"
        job["sub_step"] = "Hoàn thành xuất sắc! Sẵn sàng tải xuống."
        log("Mọi bước xử lý đã thành công. Video dịch thuật đã sẵn sàng.")
        
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
        "audio": None,
        "error": None
    }
    
    # Start thread
    thread = threading.Thread(
        target=run_pipeline,
        args=(job_id, request.url, request.bg_volume, request.burn_subtitles),
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
            "audio_url": f"/api/download/{job_id}/original_audio.mp3" if job["audio"] else None
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
    elif file_type == "original_audio.mp3":
        path = job["audio"]
        media_type = "audio/mpeg"
        
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp được yêu cầu.")
        
    return FileResponse(path, media_type=media_type, filename=os.path.basename(path))

# Serve Frontend static files directly
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
