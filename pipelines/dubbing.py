"""
🎙️ AI Dubbing Pipeline
Tự động tải video gốc, nhận diện giọng nói, dịch và lồng tiếng Việt.
"""
import os
import time
import threading
import logging

from downloader import download_douyin_video
from audio_processor import extract_audio, generate_srt, mix_audio_and_video
from translator import get_vertex_client, transcribe_and_translate_audio, transcribe_audio_gemini
from tts_processor import generate_tts_for_subtitles, detect_speaker_gender
from ocr_engine import extract_subtitle_segments
from google.genai import types

logger = logging.getLogger("douyin_translator")


class DubbingPipeline:
    """Pipeline dịch thuật & lồng tiếng video (Mode 1)."""

    def __init__(self, job_store: dict, jobs_ttl: int = 7200):
        self.jobs = job_store
        self.JOBS_TTL_SECONDS = jobs_ttl

    # ── helpers ────────────────────────────────────────────
    @staticmethod
    def _make_logger(job: dict, job_id: str):
        def log(msg: str):
            ts = time.strftime("%H:%M:%S")
            line = f"[{ts}] INFO - {msg}"
            job["logs"].append(line)
            logger.info(f"[{job_id}] {msg}")
        return log

    # ── Phase 1: Download ──────────────────────────────────
    def run_phase1(self, job_id: str, url: str):
        job = self.jobs.get(job_id)
        if not job:
            return

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

        log = self._make_logger(job, job_id)

        try:
            job["step"] = 1
            job["sub_step"] = "STEP 1.0: Đang tải video..."
            log(f"Khởi động mô-đun tải video: {url}")
            res_val = job.get("resolution", "1080")
            video_path = download_douyin_video(url, job_folder, resolution=res_val)

            if not video_path or not os.path.exists(video_path):
                raise ValueError("Không thể tải video từ liên kết này. Vui lòng kiểm tra lại liên kết, trạng thái mạng hoặc cập nhật Cookie của bạn.")

            video_base_name = aweme_id
            if video_path and os.path.exists(video_path):
                downloaded_base = os.path.splitext(os.path.basename(video_path))[0]
                if downloaded_base not in ("video", "original", ""):
                    video_base_name = downloaded_base
                original_path = os.path.join(job_folder, "original.mp4")
                if video_path != original_path:
                    os.rename(video_path, original_path)
                video_path = original_path
            job["original_video"] = video_path
            job["video_base_name"] = video_base_name
            log(f"Tải video gốc thành công: {video_path} (Tên gốc: {video_base_name})")

            # Quét tự động phát hiện srt trùng khớp trong projects/
            from main import find_matching_srt
            detected_srt = find_matching_srt(video_base_name)
            if detected_srt:
                job["detected_srt"] = detected_srt

            # Xóa các thư mục công việc cũ của cùng một video trong output/ để tránh nặng bộ nhớ
            import glob
            import shutil
            clean_base = "".join(c if c.isalnum() or c in "_-" else "_" for c in video_base_name)
            if clean_base and len(clean_base) >= 3:
                existing_folders = glob.glob(os.path.join("output", f"*_{clean_base}"))
                for old_folder in existing_folders:
                    if os.path.normpath(old_folder) != os.path.normpath(job_folder) and os.path.exists(old_folder) and os.path.isdir(old_folder):
                        try:
                            shutil.rmtree(old_folder, ignore_errors=True)
                            log(f"Đã dọn dẹp thư mục cũ để tiết kiệm dung lượng: {old_folder}")
                        except Exception as de:
                            logger.warning(f"Không thể xóa thư mục cũ {old_folder}: {de}")

            # Fast Start optimization
            if video_path and os.path.exists(video_path):
                log("Tối ưu hóa cấu trúc video (Fast Start)...")
                fast_path = os.path.join(job_folder, "original_fast.mp4")
                import subprocess
                try:
                    subprocess.run([
                        "ffmpeg", "-y", "-i", video_path,
                        "-c", "copy", "-map", "0",
                        "-movflags", "+faststart", fast_path
                    ], capture_output=True, check=True, timeout=30)
                    os.replace(fast_path, video_path)
                    log("Tối ưu hóa cấu trúc video thành công.")
                except Exception as fe:
                    log(f"Không thể tối ưu hóa video Fast Start: {fe}. Tiếp tục dùng tệp gốc.")

            process_mode = job.get("process_mode", "ocr")
            if process_mode == "auto" or job.get("imported_srt") or job.get("use_detected_srt"):
                log("Chế độ xử lý: Tự động (ASR/SRT). Bắt đầu Phase 2 ngay lập tức...")
                job["status"] = "running"
                self.run_phase2(
                    job_id=job_id, use_ocr=False,
                    y_start=0.0, y_end=0.0, x_start=0.0, x_end=0.0
                )
            else:
                job["status"] = "awaiting_ocr_selection"
                job["sub_step"] = "Đang chờ người dùng chọn vùng quét phụ đề (OCR)..."
                log("Tải video gốc thành công. Trình duyệt đang hiển thị video để chọn vùng OCR.")

        except Exception as e:
            logger.error(f"Pipeline Phase 1 failure: {str(e)}", exc_info=True)
            job["status"] = "failed"
            job["error"] = str(e)
            job["sub_step"] = "LỖI: Tải video gốc thất bại."
            log(f"LỖI HỆ THỐNG: {str(e)}")

    # ── Phase 2: OCR → Translate → TTS → Export ────────────
    def run_phase2(self, job_id: str, use_ocr: bool,
                   y_start: float, y_end: float,
                   x_start: float = 0.0, x_end: float = 1.0):
        job = self.jobs.get(job_id)
        if not job:
            return

        job_folder = job["job_folder"]
        video_path = job["original_video"]
        bg_volume = job.get("bg_volume", 0.15)
        burn_subtitles = job.get("burn_subtitles", False)
        tts_provider = job.get("tts_provider", "edge")

        log = self._make_logger(job, job_id)

        try:
            # --- KIỂM TRA FILE PHỤ ĐỀ SRT IMPORT THỦ CÔNG HOẶC TỰ ĐỘNG PHÁT HIỆN ---
            imported_srt = job.get("imported_srt")
            use_detected_srt = job.get("use_detected_srt")
            detected_srt = job.get("detected_srt")
            
            target_srt_path = None
            if imported_srt and os.path.exists(imported_srt):
                target_srt_path = os.path.join(job_folder, "subtitles.srt")
                import shutil
                try:
                    # Nếu là file nằm trong output/imports thì ta di chuyển để dọn dẹp, ngược lại (ví dụ projects/) thì ta chỉ copy
                    if "imports" in imported_srt:
                        shutil.move(imported_srt, target_srt_path)
                        log(f"Đã nạp và dọn dẹp file phụ đề SRT từ imports: {target_srt_path}")
                    else:
                        shutil.copy2(imported_srt, target_srt_path)
                        log(f"Đã sao chép file phụ đề SRT từ dự án: {target_srt_path}")
                except Exception as me:
                    log(f"Lỗi xử lý file SRT: {me}. Cố sao chép...")
                    shutil.copy2(imported_srt, target_srt_path)
                    if "imports" in imported_srt:
                        try:
                            os.remove(imported_srt)
                        except:
                            pass
            elif use_detected_srt and detected_srt and os.path.exists(detected_srt):
                target_srt_path = os.path.join(job_folder, "subtitles.srt")
                import shutil
                shutil.copy2(detected_srt, target_srt_path)
                log(f"Tự động nạp phụ đề cũ từ projects: {target_srt_path}")
                
            if target_srt_path:
                from audio_processor import parse_srt
                subtitles = parse_srt(target_srt_path)

            if subtitles:
                log(f"Nạp phụ đề thành công ({len(subtitles)} phân đoạn). Bỏ qua bước OCR, ASR và Dịch thuật.")
                job["step"] = 4
                job["sub_step"] = "Đã nạp phụ đề import, bỏ qua OCR & Dịch thuật."
            else:
                if use_ocr:
                    job["step"] = 2
                    job["sub_step"] = "STEP 2.0: Đang quét OCR offline (RapidOCR)..."
                    log(f"Khởi động RapidOCR offline – vùng quét Y=[{y_start:.2f}–{y_end:.2f}]...")
                    original_audio_path = os.path.join(job_folder, "audio.mp3")

                    asr_result = []
                    asr_err = []
                    audio_ready = False
                    try:
                        log("Tách âm thanh gốc làm căn cứ cross-check...")
                        extract_audio(video_path, original_audio_path)
                        job["audio"] = original_audio_path
                        audio_ready = True
                    except Exception as e:
                        log(f"Cảnh báo tách âm thanh gốc thất bại: {e}.")

                    def run_asr():
                        try:
                            if audio_ready and os.path.exists(original_audio_path):
                                client_asr = get_vertex_client()
                                res = transcribe_audio_gemini(client_asr, original_audio_path)
                                asr_result.append(res)
                        except Exception as e:
                            asr_err.append(e)

                    t_asr = threading.Thread(target=run_asr)
                    t_asr.start()

                    try:
                        ocr_segments = extract_subtitle_segments(
                            video_path=video_path,
                            y_start_ratio=y_start, y_end_ratio=y_end,
                            x_start_ratio=x_start, x_end_ratio=x_end,
                            log_func=log,
                        )
                    except Exception as e:
                        log(f"Lỗi RapidOCR: {e}. Tự động chuyển sang ASR fallback.")
                        use_ocr = False
                        ocr_segments = []

                    t_asr.join()

                    if use_ocr and ocr_segments:
                        log(f"RapidOCR trích xuất {len(ocr_segments)} đoạn phụ đề. Đang dịch batch...")
                        translate_provider = job.get("translate_provider", "gemini")
                        subtitles = self._translate_ocr_subtitles(
                            ocr_segments, log,
                            provider=translate_provider,
                            voice_name=job.get("voice_name"),
                            translate_style=job.get("translate_style", "default"),
                            context=job.get("context")
                        )

                        if not subtitles:
                            log("Dịch thất bại. Chuyển sang ASR fallback.")
                            use_ocr = False
                        else:
                            if asr_result and asr_result[0].get("subtitles"):
                                log("Đang cross-check Hybrid Snapping: OCR vs ASR...")
                                asr_subs = asr_result[0].get("subtitles", [])
                                subtitles = self._align_ocr_asr(subtitles, asr_subs, log)
                            subtitles.sort(key=lambda x: x.get("start", 0.0))
                    else:
                        log("RapidOCR không tìm thấy phụ đề. Dùng ASR fallback.")
                        use_ocr = False

                # ── ASR fallback ──
                if not use_ocr:
                    job["step"] = 2
                    job["sub_step"] = "STEP 2.0: Đang tách luồng âm thanh từ video..."
                    log("Trích xuất âm thanh gốc bằng ffmpeg...")
                    original_audio_path = os.path.join(job_folder, "audio.mp3")
                    if not os.path.exists(original_audio_path):
                        extract_audio(video_path, original_audio_path)
                    job["audio"] = original_audio_path
                    log(f"Trích xuất âm thanh thành công: {original_audio_path}")

                    if not subtitles:
                        job["step"] = 3
                        asr_mode = job.get("asr_mode", "audio")
                        if asr_mode == "whisper":
                            job["sub_step"] = "STEP 3.0: Đang nhận dạng giọng nói bằng Local Whisper..."
                            from translator import transcribe_audio_local_whisper
                            whisper_result = transcribe_audio_local_whisper(original_audio_path)
                            whisper_subs = whisper_result.get("subtitles", [])
                            log(f"Đã nhận dạng {len(whisper_subs)} phân đoạn bằng Whisper.")
                            translate_provider = job.get("translate_provider", "gemini")
                            subtitles = self._translate_ocr_subtitles(
                                whisper_subs, log,
                                provider=translate_provider,
                                voice_name=job.get("voice_name"),
                                translate_style=job.get("translate_style", "default"),
                                context=job.get("context")
                            )
                        else:
                            job["sub_step"] = "STEP 3.0: Đang nhận dạng giọng nói bằng Gemini 2.5 Flash..."
                            log("Gửi tệp âm thanh qua Google GenAI SDK để ASR...")
                            asr_client = get_vertex_client()
                            subtitles_data = transcribe_audio_gemini(asr_client, original_audio_path)
                            whisper_subs = subtitles_data.get("subtitles", [])
                            
                            log(f"Đã nhận dạng {len(whisper_subs)} phân đoạn bằng Gemini ASR. Bắt đầu dịch thuật...")
                            translate_provider = job.get("translate_provider", "gemini")
                            subtitles = self._translate_ocr_subtitles(
                                whisper_subs, log,
                                provider=translate_provider,
                                voice_name=job.get("voice_name"),
                                translate_style=job.get("translate_style", "default"),
                                context=job.get("context")
                            )
                        subtitles.sort(key=lambda x: x.get("start", 0.0))
                        log(f"Hoàn thành ASR. Tìm thấy {len(subtitles)} phân đoạn.")

                # ── Step 4: Dịch ──
                job["step"] = 4
                job["sub_step"] = "STEP 4.0: Đang dịch thuật..."
                log("Biên dịch bản dịch tiếng Việt...")

            # --- SUBTITLE REVIEW MODAL PAUSE STEP ---
            job["subtitles"] = subtitles
            
            if job.get("is_batch_item", False):
                job["status"] = "running"
                log("Đang chạy chế độ Hàng loạt (Batch). Tự động bỏ qua bước duyệt phụ đề.")
            else:
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

            # ── Step 5: Diarization ──
            job["step"] = 5
            job["sub_step"] = "STEP 5.0: Đang phân loại người nói..."

            # ── Step 6: TTS ──
            job["step"] = 6
            provider_label = {
                "gemini": "Gemini TTS (AI Native)",
                "google": "Google Cloud TTS (Neural2)",
            }.get(tts_provider, "edge-tts (Microsoft Neural)")
            job["sub_step"] = f"STEP 6.0: Đang lồng tiếng Việt bằng {provider_label}..."
            log(f"Tổng hợp giọng nói tiếng Việt bằng {provider_label}...")
            tts_dir = os.path.join(job_folder, "tts")
            os.makedirs(tts_dir, exist_ok=True)

            voice_map = job.get("voice_map")
            voice_name = job.get("voice_name")
            voice_female = job.get("voice_female")
            voice_male = job.get("voice_male")

            # Tự động gộp thành đơn giọng nếu chỉ thiết lập duy nhất 1 giọng Nữ hoặc Nam
            if not voice_name:
                if voice_female and not voice_male:
                    voice_name = voice_female
                    voice_female = None
                elif voice_male and not voice_female:
                    voice_name = voice_male
                    voice_male = None

            if not voice_map and not voice_name and (voice_female or voice_male):
                voice_map = {}
                seen = set()
                for sub in subtitles:
                    spk = sub.get("speaker", "default")
                    if spk not in seen:
                        seen.add(spk)
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
            log(f"Đã hoàn thành TTS cho {len(subtitles_with_tts)} phân đoạn.")

            # ── Step 7: SRT ──
            job["step"] = 7
            job["sub_step"] = "STEP 7.0: Đang tạo phụ đề..."
            srt_path = os.path.join(job_folder, "subtitles.srt")
            srt_original_path = os.path.join(job_folder, "subtitles_original.srt")
            job["srt"] = srt_path
            job["srt_original"] = srt_original_path

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
                srt_path = ass_path
            generate_srt(subtitles, srt_path.replace(".ass", ".srt") if srt_path.endswith(".ass") else srt_path, use_original=False)
            generate_srt(subtitles, srt_original_path, use_original=True)

            # ── Step 8: Export ──
            job["step"] = 8
            job["sub_step"] = "STEP 8.0: Đang xuất video việt hóa..."
            log("Ghép giọng đọc AI + ducking nhạc nền gốc...")

            output_video_path = os.path.join(job_folder, "translated_video.mp4")

            if not os.path.exists(os.path.join(job_folder, "audio.mp3")):
                extract_audio(video_path, os.path.join(job_folder, "audio.mp3"))
                job["audio"] = os.path.join(job_folder, "audio.mp3")

            mix_audio_and_video(
                video_path=video_path,
                original_audio_path=os.path.join(job_folder, "audio.mp3"),
                tts_segments=subtitles_with_tts,
                output_video_path=output_video_path,
                bg_volume=bg_volume,
                burn_subtitles=burn_subtitles,
                srt_path=srt_path,
                srt_original_path=srt_original_path,
                tts_speed=1.0
            )

            # Cleanup temp files
            try:
                import shutil
                tts_dir_path = os.path.join(job_folder, "tts")
                if os.path.exists(tts_dir_path):
                    shutil.rmtree(tts_dir_path, ignore_errors=True)
                audio_file = os.path.join(job_folder, "audio.mp3")
                if os.path.exists(audio_file):
                    os.remove(audio_file)
            except Exception:
                pass

            job["translated_video"] = output_video_path
            job["status"] = "completed"
            job["sub_step"] = "Hoàn thành!"
            log(f"Hoàn thành! Video lưu tại: {job_folder}/")

            # --- SAO LƯU KẾT QUẢ VÀO THƯ MỤC PROJECTS/ ĐỂ LƯU TRỮ VĨNH VIỄN VÀ NHẬN DIỆN LẦN SAU ---
            try:
                video_base_name = job.get("video_base_name") or "video"
                clean_base = "".join(c if c.isalnum() or c in "_-" else "_" for c in video_base_name)
                projects_dir = "projects"
                os.makedirs(projects_dir, exist_ok=True)
                
                # Sao chép video Việt hóa
                dubbed_dest = os.path.join(projects_dir, f"{clean_base}_viet.mp4")
                import shutil
                shutil.copy2(output_video_path, dubbed_dest)
                log(f"Đã sao lưu video Việt hóa vĩnh viễn: {dubbed_dest}")
                
                # Sao chép phụ đề Việt hóa (.srt)
                actual_srt_source = srt_path
                if srt_path.endswith(".ass"):
                    actual_srt_source = srt_path.replace(".ass", ".srt")
                
                if os.path.exists(actual_srt_source):
                    srt_dest = os.path.join(projects_dir, f"{clean_base}_viet.srt")
                    shutil.copy2(actual_srt_source, srt_dest)
                    log(f"Đã sao lưu phụ đề Việt hóa vĩnh viễn: {srt_dest}")
            except Exception as backup_err:
                log(f"Cảnh báo: Không thể sao lưu kết quả vào projects/: {backup_err}")

        except Exception as e:
            logger.error(f"Pipeline Phase 2 failure: {str(e)}", exc_info=True)
            job["status"] = "failed"
            job["error"] = str(e)
            job["sub_step"] = "LỖI: Tiến trình xử lý thất bại."
            log(f"LỖI HỆ THỐNG: {str(e)}")

    # ── translation helpers ────────────────────────────────
    def _translate_ocr_subtitles(self, ocr_segments, log_func, provider="gemini",
                                  voice_name=None, topic=None,
                                  translate_style="default", context=None):
        import json
        import requests as req

        texts = [seg.get("text", "") for seg in ocr_segments]
        if not any(t.strip() for t in texts):
            log_func("Không có văn bản OCR nào để dịch.")
            return []

        translations = [""] * len(texts)
        translated = False

        if provider == "gist":
            GIST_URL = "https://http-honyaku-kiban-production-80.schnworks.com/translation/language/translate/v2"
            log_func(f"🌐 Gist API: Đang dịch {len(texts)} đoạn...")
            try:
                resp = req.post(GIST_URL, json={"texts": texts, "targetLanguage": "vie"},
                               headers={"Content-Type": "application/json"}, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    gist_t = data.get("translations", [])
                    if gist_t and any(t.strip() for t in gist_t):
                        translations = gist_t
                        translated = True
                        log_func(f"✅ Gist API dịch thành công {len(translations)} đoạn.")
                    else:
                        log_func("⚠️ Gist API trả về rỗng.")
                else:
                    log_func(f"⚠️ Gist API lỗi HTTP {resp.status_code}.")
            except Exception as e:
                log_func(f"⚠️ Gist API lỗi: {str(e)[:100]}")

            if not translated:
                log_func("🌐 Fallback: Google Translate miễn phí...")
                try:
                    google_ts = []
                    for text in texts:
                        if not text.strip():
                            google_ts.append("")
                            continue
                        r = req.get("https://translate.googleapis.com/translate_a/single",
                                   params={"client": "gtx", "sl": "zh-CN", "tl": "vi", "dt": "t", "q": text}, timeout=10)
                        if r.status_code == 200:
                            parts = [p[0] for p in r.json()[0] if p and p[0]]
                            google_ts.append("".join(parts))
                        else:
                            google_ts.append("")
                    if any(t.strip() for t in google_ts):
                        translations = google_ts
                        translated = True
                        log_func(f"✅ Google Translate dịch {len(translations)} đoạn.")
                except Exception as ge:
                    log_func(f"⚠️ Google Translate lỗi: {str(ge)[:100]}")

        else:  # gemini
            style = translate_style or "default"
            if voice_name:
                log_func(f"🤖 Gemini Vertex ({style}): Đang dịch {len(texts)} đoạn...")
                try:
                    from prompts import build_batch_prompt
                    client = get_vertex_client()
                    prompt = build_batch_prompt(texts, style=style, context=context)
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=[prompt],
                        config=types.GenerateContentConfig(temperature=0.2)
                    )
                    if response and response.text:
                        lines = [l.strip() for l in response.text.split("\n") if l.strip()]
                        j = 0
                        for i, t in enumerate(texts):
                            if t.strip() and j < len(lines):
                                translations[i] = lines[j]
                                j += 1
                        translated = True
                        log_func(f"✅ Gemini Vertex dịch {j}/{len(texts)} đoạn.")
                except Exception as e:
                    log_func(f"⚠️ Gemini Vertex lỗi: {str(e)[:100]}")
            else:
                log_func(f"🤖 Gemini Vertex ({style}): Đang dịch & phân vai {len(texts)} đoạn...")
                try:
                    from prompts import build_roleplay_prompt
                    client = get_vertex_client()
                    prompt = build_roleplay_prompt(texts, style=style, context=context)
                    schema = {
                        "type": "OBJECT",
                        "properties": {
                            "results": {
                                "type": "ARRAY",
                                "items": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "translation": {"type": "STRING"},
                                        "speaker": {"type": "STRING"}
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
                        data = json.loads(response.text)
                        results = data.get("results", [])
                        j = 0
                        for i, t in enumerate(texts):
                            if t.strip() and j < len(results):
                                translations[i] = results[j].get("translation", "")
                                if i < len(ocr_segments):
                                    ocr_segments[i]["speaker"] = results[j].get("speaker", "Speaker A")
                                j += 1
                        translated = True
                        log_func(f"✅ Gemini Vertex dịch & phân vai {j}/{len(texts)} đoạn.")
                except Exception as e:
                    log_func(f"⚠️ Gemini Vertex lỗi: {str(e)[:100]}")

        if not translated:
            log_func("⚠️ KHÔNG dịch được. Dùng text gốc.")
            for i, t in enumerate(texts):
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

    @staticmethod
    def _align_ocr_asr(ocr_subs, asr_subs, log_func):
        checked = []
        warnings = 0
        for ocr_seg in ocr_subs:
            ocr_start = ocr_seg.get("start", 0.0)
            ocr_end = ocr_seg.get("end", 0.0)
            best_match = None
            max_overlap = 0.0
            for asr_seg in asr_subs:
                overlap = max(0, min(ocr_end, asr_seg.get("end", 0.0)) - max(ocr_start, asr_seg.get("start", 0.0)))
                if overlap > 0:
                    ocr_dur = ocr_end - ocr_start
                    if ocr_dur > 0 and overlap / ocr_dur > 0.3 and overlap > max_overlap:
                        max_overlap = overlap
                        best_match = asr_seg
            if best_match:
                delta = abs(ocr_start - best_match.get("start", 0.0))
                if delta > 1.0:
                    warnings += 1
            checked.append(ocr_seg)
        if warnings:
            log_func(f"Cross-check: {warnings}/{len(ocr_subs)} đoạn lệch >1s (giữ nguyên OCR).")
        else:
            log_func(f"Cross-check: {len(ocr_subs)} đoạn OCR đồng bộ tốt với ASR.")
        return checked
