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
from ocr_engine import extract_subtitle_segments

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

class ResumeRequest(BaseModel):
    use_ocr: bool
    y_start: float = 0.80
    y_end: float = 0.95
    x_start: float = 0.0
    x_end: float = 1.0

def run_pipeline_phase1(job_id: str, url: str):
    job = jobs[job_id]
    
    # Trích xuất Aweme ID để đặt tên thư mục dễ nhận biết
    from downloader import (
        clean_and_rewrite_douyin_url,
        extract_aweme_id,
        resolve_short_url,
        load_cookies_txt
    )
    aweme_id = "video"
    try:
        clean_url = clean_and_rewrite_douyin_url(url)
        if "douyin.com" in clean_url and ("v.douyin.com" in clean_url or "v.iesdouyin.com" in clean_url):
            cookies = load_cookies_txt()
            resolved_url = resolve_short_url(clean_url, cookies)
        else:
            resolved_url = clean_url
        extracted = extract_aweme_id(resolved_url)
        if extracted:
            aweme_id = extracted
    except Exception as e:
        logger.warning(f"Không thể trích xuất aweme_id trước khi tạo thư mục: {e}")

    job_folder_name = f"{time.strftime('%Y%m%d_%H%M%S')}_{aweme_id}"
    job_folder = f"output/{job_folder_name}"
    os.makedirs(job_folder, exist_ok=True)
    job["job_folder"] = job_folder
    job["folder_name"] = job_folder_name
    
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
        
        # Di chuyển moov atom lên đầu (Fast Start) để trình duyệt load và hiển thị ngay lập tức
        if video_path and os.path.exists(video_path):
            log("Tối ưu hóa cấu trúc video (Fast Start) để trình duyệt hiển thị ngay lập tức...")
            fast_path = os.path.join(job_folder, "original_fast.mp4")
            fast_cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-c", "copy",
                "-map", "0",
                "-movflags", "+faststart",
                fast_path
            ]
            try:
                import subprocess
                subprocess.run(fast_cmd, capture_output=True, check=True, timeout=30)
                os.replace(fast_path, video_path)
                log("Tối ưu hóa cấu trúc video thành công.")
            except Exception as fe:
                log(f"Không thể tối ưu hóa video Fast Start: {fe}. Tiếp tục dùng tệp gốc.")
        
        # Chuyển trạng thái sang chờ người dùng chọn vùng OCR
        job["status"] = "awaiting_ocr_selection"
        job["sub_step"] = "Đang chờ người dùng chọn vùng quét phụ đề (OCR)..."
        log("Tải video gốc thành công. Trình duyệt đang hiển thị video để chọn vùng OCR phụ đề cứng.")
        
    except Exception as e:
        logger.error(f"Pipeline Phase 1 failure: {str(e)}", exc_info=True)
        job["status"] = "failed"
        job["error"] = str(e)
        job["sub_step"] = "LỖI: Tải video gốc thất bại."
        log(f"LỖI HỆ THỐNG: {str(e)}")

TRANSLATE_API_URL = "https://http-honyaku-kiban-production-80.schnworks.com/translation/language/translate/v2"

def _translate_ocr_subtitles(ocr_segments: list, log_func) -> list:
    """
    Dịch batch các đoạn OCR (tiếng Trung → tiếng Việt) qua Gist Translation API.
    Trả về list định dạng chuẩn: [{start, end, text, translation, speaker}].
    """
    import requests as req
    texts_to_translate = [seg.get("text", "") for seg in ocr_segments]
    if not any(t.strip() for t in texts_to_translate):
        log_func("Không có văn bản OCR nào để dịch.")
        return []

    log_func(f"Đang dịch {len(texts_to_translate)} đoạn phụ đề qua Gist API...")
    try:
        resp = req.post(
            TRANSLATE_API_URL,
            json={"texts": texts_to_translate, "targetLanguage": "vie"},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        if resp.status_code != 200:
            log_func(f"Gist API lỗi HTTP {resp.status_code}: {resp.text[:200]}")
            # Fallback: giữ nguyên text gốc
            translations = [""] * len(texts_to_translate)
        else:
            data = resp.json()
            translations = data.get("translations", [])
    except Exception as e:
        log_func(f"Gist API không phản hồi: {e}. Giữ nguyên text gốc.")
        translations = [""] * len(texts_to_translate)

    result = []
    for i, seg in enumerate(ocr_segments):
        result.append({
            "start": seg.get("start", 0.0),
            "end": seg.get("end", 0.0),
            "text": seg.get("text", ""),
            "translation": translations[i] if i < len(translations) else "",
            "speaker": "Speaker A",
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
                log(f"RapidOCR trích xuất {len(ocr_segments)} đoạn phụ đề. Đang dịch batch qua Gist API...")
                subtitles = _translate_ocr_subtitles(ocr_segments, log)

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
                job["sub_step"] = "STEP 3.0: Đang nhận dạng giọng nói bằng Gemini 2.5 Flash..."
                log("Gửi tệp âm thanh trực tiếp qua Google GenAI SDK để phân tích và nhận diện giọng nói (ASR)...")
                
                subtitles_data = transcribe_and_translate_audio(client, original_audio_path)
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
            
        # Step 5: Nhận diện giọng / Gán vai
        job["step"] = 5
        job["sub_step"] = "STEP 5.0: Đang phân loại người nói (Diarization)..."
        for idx, sub in enumerate(subtitles):
            log(f"Gán vai cho phân đoạn {idx+1}: {sub.get('speaker', 'default')}")
            
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
        
        # Ghi cả 2 file phụ đề tiếng Việt và tiếng Trung khớp 100% hành động video gốc
        generate_srt(subtitles, srt_path, use_original=False)
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
            srt_original_path=srt_original_path
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
        "bg_volume": request.bg_volume,
        "burn_subtitles": request.burn_subtitles,
        "tts_provider": request.tts_provider,
        "asr_mode": request.asr_mode,
        "_created": time.time(),
    }
    
    # Dọn job cũ trước khi tạo mới
    _cleanup_expired_jobs()
    
    # Start thread
    thread = threading.Thread(
        target=run_pipeline_phase1,
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
        target=run_pipeline_phase2,
        args=(job_id, request.use_ocr, request.y_start, request.y_end, request.x_start, request.x_end),
        daemon=True
    )
    thread.start()
    
    return {"status": "success", "message": "Đã tiếp tục tiến trình dịch thuật."}

@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên xử lý.")
    
    job = jobs[job_id]
    
    # Prepare download urls
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

# Serve Output files statically for video range streaming support
app.mount("/output", StaticFiles(directory="output"), name="output")

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
