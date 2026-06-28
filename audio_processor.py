import os
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger("douyin_translator")

def extract_audio(video_path: str, output_audio_path: str) -> str:
    """
    Extracts the audio stream from a video file and saves it as MP3.
    """
    logger.info(f"Extracting audio from video: {video_path} -> {output_audio_path}")
    os.makedirs(os.path.dirname(output_audio_path), exist_ok=True)
    
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-q:a", "0",
        "-map", "a",
        output_audio_path
    ]
    
    try:
        # Run command and capture output
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        logger.info("Audio extraction completed successfully.")
        return os.path.abspath(output_audio_path)
    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg error during audio extraction: {e.stderr}")
        raise e

def format_timestamp(seconds: float) -> str:
    """Converts seconds into SRT timestamp format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def generate_srt(subtitles: list, output_srt_path: str, use_original: bool = False):
    """Generates an SRT subtitle file from subtitle segment list (uses Gemini timestamps).
    
    Args:
        subtitles: list các segment
        output_srt_path: đường dẫn output
        use_original: True = tiếng gốc (text), False = tiếng Việt (translation)
    """
    lang = "original" if use_original else "translated"
    logger.info(f"Writing {lang} subtitles to SRT: {output_srt_path}")
    os.makedirs(os.path.dirname(output_srt_path), exist_ok=True)
    
    with open(output_srt_path, "w", encoding="utf-8") as f:
        for idx, sub in enumerate(subtitles):
            start_str = format_timestamp(sub["start"])
            end_str = format_timestamp(sub["end"])
            text = sub.get("text" if use_original else "translation", "").strip()
            f.write(f"{idx+1}\n")
            f.write(f"{start_str} --> {end_str}\n")
            f.write(f"{text}\n\n")

def generate_srt_from_timeline(timeline: list, output_srt_path: str, use_original: bool = False):
    """Generates SRT from actual timeline (khớp chính xác với audio TTS).
    
    Args:
        timeline: list từ _compute_actual_timeline
        output_srt_path: đường dẫn output
        use_original: True = tiếng gốc (text), False = tiếng Việt (translation)
    """
    logger.info(f"Writing SRT from actual timeline: {output_srt_path}")
    os.makedirs(os.path.dirname(output_srt_path), exist_ok=True)
    
    with open(output_srt_path, "w", encoding="utf-8") as f:
        for idx, seg in enumerate(timeline):
            start_str = format_timestamp(seg["actual_start"])
            end_str = format_timestamp(seg["actual_end"])
            text = seg.get("text" if use_original else "translation", "").strip()
            f.write(f"{idx+1}\n")
            f.write(f"{start_str} --> {end_str}\n")
            f.write(f"{text}\n\n")

def mix_audio_and_video(
    video_path: str,
    original_audio_path: str,
    tts_segments: list,
    output_video_path: str,
    bg_volume: float = 0.15,
    burn_subtitles: bool = False,
    srt_path: str = None,
    srt_original_path: str = None
) -> list:
    """
    Mixes the original video, original audio (reduced volume for background music),
    and TTS audio clips (aligned to their start timestamps).
    
    Strategy: Pre-mix all TTS segments into one file first (tránh command line quá dài trên Windows),
    then mix video + bg + mixed_tts in a second pass.
    """
    logger.info(f"Mixing video and voiceover: {video_path}")
    out_dir = os.path.dirname(output_video_path)
    os.makedirs(out_dir, exist_ok=True)
    
    # Lấy độ dài video để làm mốc giới hạn âm thanh tĩnh
    video_duration = _get_audio_duration_ffprobe(video_path)
    if video_duration <= 0:
        video_duration = _get_audio_duration_ffprobe(original_audio_path)
    if video_duration <= 0:
        video_duration = 30.0  # Fallback
        
    # ============================================================
    # Pass 1: Mix tất cả TTS segments thành 1 file duy nhất
    # ============================================================
    tts_mixed_path = os.path.join(out_dir, "_tts_mixed.mp3")
    actual_timeline = _premix_tts_segments(tts_segments, tts_mixed_path, video_duration)
    
    # Ghi đè file SRT với timeline thực tế để khớp chính xác với audio
    if srt_path:
        generate_srt_from_timeline(actual_timeline, srt_path, use_original=False)
    if srt_original_path:
        generate_srt_from_timeline(actual_timeline, srt_original_path, use_original=True)
    
    # ============================================================
    # Pass 2: Mix video + bg audio (ducked) + TTS voiceover
    # ============================================================
    cmd = ["ffmpeg", "-y"]
    cmd.extend(["-i", video_path])          # Input 0: video
    cmd.extend(["-i", original_audio_path])  # Input 1: bg audio gốc
    cmd.extend(["-i", tts_mixed_path])       # Input 2: mixed TTS voiceover

    # Audio ducking: tự động giảm nhạc nền khi có giọng đọc TTS
    # sidechaincompress: TTS (input 2) trigger → nén bg audio (input 1)
    # - Khi TTS im lặng: bg audio phát bình thường ở volume bg_volume
    # - Khi TTS đang nói: bg audio bị nén xuống, giọng đọc nổi bật
    filter_complex = (
        f"[2:a]asplit[tts_trigger][tts_voice];"
        f"[1:a]volume={bg_volume}[bg];"
        f"[bg][tts_trigger]sidechaincompress="
        f"threshold=0.01:ratio=8:attack=20:release=200:level_sc=0.15[bg_ducked];"
        f"[bg_ducked][tts_voice]amix=inputs=2:duration=first[final_audio]"
    )
    
    cmd.extend(["-filter_complex", filter_complex])
    cmd.extend(["-map", "0:v"])
    cmd.extend(["-map", "[final_audio]"])
    cmd.extend(["-c:v", "copy"])
    cmd.extend(["-c:a", "aac", "-b:a", "192k"])
    
    # Burn subtitles nếu cần
    if burn_subtitles and srt_path and os.path.exists(srt_path):
        # Thay "copy" bằng "libx264" (cần re-encode để burn subtitle)
        idx_copy = cmd.index("copy")
        cmd[idx_copy] = "libx264"
        escaped_srt_path = srt_path.replace("\\", "/").replace(":", "\\:")
        cmd.extend(["-vf", f"subtitles='{escaped_srt_path}'"])
    
    cmd.append(output_video_path)
    
    logger.info(f"Running final ffmpeg mix (3 inputs)...")
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        logger.info("Video export and mixing completed successfully.")
        # Dọn file tạm
        if os.path.exists(tts_mixed_path):
            os.remove(tts_mixed_path)
        return actual_timeline  # Trả về timeline thực tế cho SRT
    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg error during mixing: {e.stderr}")
        raise e


def _premix_tts_segments(tts_segments: list, output_path: str, video_duration: float) -> list:
    """
    Trộn tất cả các phân đoạn TTS vào một tệp âm thanh duy nhất bằng cách đặt chúng
    chính xác tại mốc thời gian bắt đầu (start) của câu thoại gốc thông qua bộ lọc 'adelay' và 'amix'.
    """
    logger.info(f"Pre-mixing {len(tts_segments)} TTS segments at exact absolute offsets...")
    import tempfile

    # Bước 1: Tính timeline thực tế (đồng nhất thời gian với câu thoại gốc)
    actual_timeline = _compute_actual_timeline(tts_segments)

    # Nếu không có phân đoạn nào, tạo file lặng rồi trả về
    valid_segments = [seg for seg in actual_timeline if os.path.exists(seg["audio_path"])]
    if not valid_segments:
        _generate_silence(output_path, max(1.0, video_duration))
        return actual_timeline

    # Bước 2: Tạo danh sách đầu vào và xây dựng chuỗi bộ lọc phức hợp (filter_complex)
    cmd = ["ffmpeg", "-y"]
    
    # Tạo tệp tin âm lặng nền có độ dài bằng đúng video_duration để làm nền (tránh lavfi sync issues)
    silence_base_path = os.path.join(tempfile.gettempdir(), "_silence_base.mp3")
    _generate_silence(silence_base_path, video_duration)
    
    # Đầu vào 0: tệp âm lặng nền
    cmd.extend(["-i", silence_base_path])
    
    # Thêm các file âm thanh TTS làm đầu vào tiếp theo (từ 1 đến N)
    for seg in valid_segments:
        cmd.extend(["-i", seg["audio_path"]])
        
    # Xây dựng filter_complex
    filter_parts = []
    mix_labels = ["[0:a]"]
    
    for idx, seg in enumerate(valid_segments):
        input_label = f"[{idx+1}:a]"
        output_label = f"[delayed_{idx}]"
        
        # adelay yêu cầu độ trễ tính bằng mili-giây cho mỗi kênh (ở đây cấu hình stereo)
        delay_ms = int(seg["actual_start"] * 1000)
        # Giới hạn delay tối thiểu là 0ms
        delay_ms = max(0, delay_ms)
        
        filter_parts.append(f"{input_label}adelay={delay_ms}|{delay_ms}{output_label}")
        mix_labels.append(output_label)
        
    # Trộn tất cả luồng đã được delay với nền âm lặng (Sử dụng normalize=0 để giữ nguyên âm lượng gốc)
    filter_parts.append(f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=first:dropout_transition=0:normalize=0[out]")
    
    # Ghi filter_complex ra tệp script tạm thời để tránh giới hạn độ dài dòng lệnh trên Windows
    filter_script_path = os.path.join(tempfile.gettempdir(), "_tts_filter_script.txt")
    with open(filter_script_path, "w", encoding="utf-8") as f:
        f.write(";\n".join(filter_parts))
        
    cmd.extend(["-filter_complex_script", filter_script_path])
    cmd.extend(["-map", "[out]"])
    cmd.extend(["-c:a", "libmp3lame", "-q:a", "2", output_path])
    
    try:
        logger.info(f"Running ffmpeg absolute offset mixing with filter script: {filter_script_path}")
        subprocess.run(cmd, capture_output=True, check=True, timeout=120)
        logger.info("TTS pre-mix at exact absolute offsets completed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"TTS pre-mix failed: {e.stderr.decode() if e.stderr else e}")
        # Fallback tạo file im lặng nếu lỗi
        _generate_silence(output_path, max(1.0, video_duration))
    finally:
        # Dọn dẹp tệp base im lặng
        if os.path.exists(silence_base_path):
            try:
                os.remove(silence_base_path)
            except OSError:
                pass
        # Dọn dẹp tệp filter script tạm
        if os.path.exists(filter_script_path):
            try:
                os.remove(filter_script_path)
            except OSError:
                pass
        # Dọn dẹp các tệp atempo tạm thời
        for seg in actual_timeline:
            temp_path = seg.get("temp_path")
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
                
    return actual_timeline


def _build_atempo_filter(speed_factor: float) -> str:
    """
    Tạo chuỗi bộ lọc atempo cho ffmpeg hỗ trợ bất kỳ speed_factor nào.
    Mỗi bộ lọc atempo chỉ hỗ trợ giá trị từ 0.5 đến 2.0.
    """
    factors = []
    temp = speed_factor
    while temp > 2.0:
        factors.append(2.0)
        temp /= 2.0
    while temp < 0.5:
        factors.append(0.5)
        temp /= 0.5
    if temp != 1.0:
        factors.append(temp)
    return ",".join([f"atempo={f:.4f}" for f in factors])


def _compute_actual_timeline(segments: list) -> list:
    """
    Tính timeline thực tế khớp khít 100% với mốc thời gian của câu gốc.
    Bắt buộc actual_start = original_start, actual_end = original_end.
    Áp dụng tăng tốc độ đọc nhẹ (tối đa 1.25x) để tránh giọng đọc bị méo, rời rạc hoặc bị cắt.
    """
    import tempfile
    
    timeline = []
    MAX_SPEED_FACTOR = 1.25
 
    for i, sub in enumerate(segments):
        translation = (sub.get("translation", "") or "").strip()
        
        tts_dur = sub.get("tts_duration", 0)
        original_start = sub.get("start", 0)
        original_end = sub.get("end", 0)
        original_dur = original_end - original_start
 
        if tts_dur <= 0:
            tts_dur = original_dur
 
        audio_path = sub.get("audio_path", "")
        speed_factor = 1.0
        temp_path = None
        
        # Tăng tốc độ đọc nếu câu dịch dài hơn câu gốc, giới hạn tối đa 1.25x để giữ giọng đọc tự nhiên
        if tts_dur > original_dur and original_dur > 0.1:
            speed_factor = tts_dur / original_dur
            if speed_factor > MAX_SPEED_FACTOR:
                speed_factor = MAX_SPEED_FACTOR
            
            if speed_factor > 1.01 and audio_path and os.path.exists(audio_path):
                logger.info(f"Segment {i} too long: {tts_dur:.2f}s vs {original_dur:.2f}s -> speedup atempo={speed_factor:.3f} (Capped at {MAX_SPEED_FACTOR})")
                adjusted_path = os.path.join(tempfile.gettempdir(), f"_atempo_{i}.mp3")
                try:
                    atempo_filter = _build_atempo_filter(speed_factor)
                    cmd = [
                        "ffmpeg", "-y", "-i", audio_path,
                        "-filter:a", atempo_filter,
                        "-c:a", "libmp3lame", "-q:a", "2",
                        adjusted_path
                    ]
                    subprocess.run(cmd, capture_output=True, check=True, timeout=30)
                    audio_path = adjusted_path
                    temp_path = adjusted_path
                    tts_dur = tts_dur / speed_factor
                except Exception as e:
                    logger.warning(f"Segment {i} atempo failed: {e}")
 
        # Bắt buộc mốc thời gian trùng khít hoàn toàn với câu thoại gốc
        actual_start = original_start
        actual_end = original_end

        timeline.append({
            "audio_path": audio_path,
            "tts_duration": round(tts_dur, 3),
            "actual_start": round(actual_start, 3),
            "actual_end": round(actual_end, 3),
            "original_start": original_start,
            "original_end": original_end,
            "speaker": sub.get("speaker", ""),
            "text": sub.get("text", ""),
            "translation": translation,
            "temp_path": temp_path
        })
 
    return timeline


def _get_audio_duration_ffprobe(file_path: str) -> float:
    """Đo duration audio bằng ffprobe."""
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", file_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def _generate_silence(output_path: str, duration_sec: float):
    """Tạo file mp3 silence với duration chỉ định."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r=44100:cl=stereo",
        "-t", f"{duration_sec:.3f}",
        "-c:a", "libmp3lame", "-q:a", "2",
        output_path
    ]
    subprocess.run(cmd, capture_output=True, timeout=30)
