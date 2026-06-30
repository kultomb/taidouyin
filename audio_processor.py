import os
import subprocess
import logging
import tempfile
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
    srt_original_path: str = None,
    tts_speed: float = 1.2
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
    actual_timeline = _premix_tts_segments(tts_segments, tts_mixed_path, video_duration, tts_speed)
    
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
    # - Khi TTS đang nói: bg audio bị nén xuống cực thấp, giọng đọc nổi bật hẳn
    filter_complex = (
        f"[2:a]asplit[tts_trigger][tts_voice];"
        f"[1:a]volume={bg_volume}[bg];"
        f"[bg][tts_trigger]sidechaincompress="
        f"threshold=0.005:ratio=20:attack=5:release=350:level_sc=0.1[bg_ducked];"
        f"[bg_ducked][tts_voice]amix=inputs=2:duration=first:normalize=0[final_audio]"
    )
    
    cmd.extend(["-filter_complex", filter_complex])
    cmd.extend(["-map", "0:v"])
    cmd.extend(["-map", "[final_audio]"])
    cmd.extend(["-c:v", "copy"])
    cmd.extend(["-c:a", "aac", "-b:a", "192k"])
    
    # Burn subtitles nếu cần (hỗ trợ cả SRT và ASS)
    if burn_subtitles and srt_path and os.path.exists(srt_path):
        idx_copy = cmd.index("copy")
        cmd[idx_copy] = "libx264"
        escaped_sub_path = srt_path.replace("\\", "/").replace(":", "\\:")
        if srt_path.endswith(".ass"):
            cmd.extend(["-vf", f"ass='{escaped_sub_path}'"])
        else:
            cmd.extend(["-vf", f"subtitles='{escaped_sub_path}'"])
    
    cmd.extend(["-movflags", "+faststart"])
    cmd.append(output_video_path)
    
    logger.info(f"Running final ffmpeg mix (3 inputs)...")
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        logger.info("Video export and mixing completed successfully.")
        if os.path.exists(tts_mixed_path):
            try:
                os.remove(tts_mixed_path)
            except OSError:
                pass
        return actual_timeline
    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg error during mixing: {e.stderr}")
        raise e

def _premix_tts_segments(tts_segments: list, output_path: str, video_duration: float, tts_speed: float = 1.2) -> list:
    """
    Trộn tất cả các phân đoạn TTS vào một tệp âm thanh duy nhất bằng cách đặt chúng
    chính xác tại mốc thời gian bắt đầu (start) của câu thoại gốc thông qua bộ lọc 'adelay' và 'amix'.
    """
    logger.info(f"Pre-mixing {len(tts_segments)} TTS segments at exact absolute offsets...")
    
    # Bước 1: Tính timeline thực tế (đồng nhất thời gian với câu thoại gốc)
    actual_timeline = _compute_actual_timeline(tts_segments, tts_speed)

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
        
        delay_ms = int(seg["actual_start"] * 1000)
        delay_ms = max(0, delay_ms)
        
        # Nếu delay_ms > 0 thì dùng adelay, ngược lại dùng anull để tránh lỗi trên một số phiên bản ffmpeg
        if delay_ms > 0:
            filter_parts.append(f"{input_label}adelay={delay_ms}|{delay_ms}{output_label}")
        else:
            filter_parts.append(f"{input_label}anull{output_label}")
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

def _compute_actual_timeline(segments: list, tts_speed: float = 1.2) -> list:
    """
    Tính timeline THÔNG MINH đồng bộ với hành động video và TRÁNH TRÙNG LẶP/ĐÈ PHÁT ÂM (nhại):
    
    CHIẾN LƯỢC:
    1. Đảm bảo start time của phân đoạn sau luôn bắt đầu SAU phân đoạn trước cộng một khoảng lặng tối thiểu (MIN_GAP).
       Với phân đoạn đầu tiên (i == 0), actual_start luôn bằng original_start để tránh lệch 120ms gây lọt tiếng gốc.
       Với phân đoạn sau (i > 0), actual_start = max(original_start, last_actual_end + MIN_GAP) để chống đè thoại.
    2. Nếu TTS ngắn hơn slot gốc → Giãn chậm (speed_factor < 1.0, tối thiểu 0.85) để giọng ấm và tự nhiên hơn.
    3. Nếu TTS dài hơn slot gốc → Tận dụng gap tiếp theo, nếu vẫn thiếu thì tăng tốc (tối đa 1.4x).
    4. Nếu sau khi tăng tốc tối đa vẫn dài hơn thời gian trống, ta chấp nhận lùi lịch phát của các câu sau (self-correcting timeline shift) thay vì phát đè lên nhau gây ra lỗi nhại tiếng.
    """
    timeline = []
    MAX_SPEEDUP_LIMIT = 1.4     # Tăng tốc tối đa để tránh méo tiếng
    MAX_SLOWDOWN = 0.85         # Giãn chậm tối đa
    MIN_GAP = 0.12              # Khoảng nghỉ tối thiểu giữa các câu
    TARGET_FILL_RATIO = 0.96    # Mục tiêu lấp đầy 96% slot gốc
    
    last_actual_end = 0.0
 
    for i, sub in enumerate(segments):
        translation = (sub.get("translation", "") or "").strip()
        
        raw_tts_dur = sub.get("tts_duration", 0)
        original_start = sub.get("start", 0)
        original_end = sub.get("end", 0)
 
        if raw_tts_dur <= 0:
            raw_tts_dur = original_end - original_start
 
        audio_path = sub.get("audio_path", "")
        temp_path = None
        
        # 1. Đảm bảo không đè lên câu thoại trước (Tránh lỗi nhại/chồng âm)
        if i == 0:
            actual_start = original_start
        else:
            actual_start = max(original_start, last_actual_end + MIN_GAP)
        
        # Xác định mốc bắt đầu của câu tiếp theo để tính gap khả dụng
        next_start = segments[i + 1]["start"] if (i + 1) < len(segments) else None
        
        # Slot thời gian lý tưởng cho câu này
        effective_dur = max(0.1, original_end - actual_start)
        
        # Độ dài tự nhiên của audio ở tốc độ tts_speed được yêu cầu
        natural_tts_dur = raw_tts_dur / tts_speed
        
        # Gap tối đa có thể mượn trước khi câu sau bắt đầu
        if next_start:
            max_available_time = max(effective_dur, next_start - actual_start - MIN_GAP)
        else:
            max_available_time = max(effective_dur, natural_tts_dur)
            
        speed_factor_relative = 1.0
        
        # ===============================================
        # CASE 1: TTS ngắn hơn slot lý tưởng → GIÃN CHẬM
        # ===============================================
        if natural_tts_dur <= effective_dur:
            desired_dur = effective_dur * TARGET_FILL_RATIO
            slowdown_factor = natural_tts_dur / desired_dur if desired_dur > 0.1 else 1.0
            
            if slowdown_factor < MAX_SLOWDOWN:
                speed_factor_relative = MAX_SLOWDOWN
            else:
                speed_factor_relative = slowdown_factor
                
            speed_factor_relative = min(speed_factor_relative, 1.0)
            actual_end = actual_start + (natural_tts_dur / speed_factor_relative)
            tts_dur = natural_tts_dur / speed_factor_relative
            logger.info(
                f"Segment {i} (Short): natural_dur={natural_tts_dur:.2f}s, slot={effective_dur:.2f}s -> "
                f"slowdown_rel={speed_factor_relative:.3f}x -> new_dur={tts_dur:.2f}s"
            )
            
        # ===============================================
        # CASE 2: TTS dài hơn slot lý tưởng → TĂNG TỐC / MƯỢN TIMELINE
        # ===============================================
        else:
            if natural_tts_dur > max_available_time:
                raw_speed = natural_tts_dur / max_available_time
                speed_factor_relative = min(raw_speed, MAX_SPEEDUP_LIMIT)
                speed_factor_relative = max(1.0, speed_factor_relative)
                logger.info(
                    f"Segment {i} (Long - Speedup): natural_dur={natural_tts_dur:.2f}s, max_available={max_available_time:.2f}s -> "
                    f"speedup_rel={speed_factor_relative:.3f}x (required={raw_speed:.2f}x)"
                )
            else:
                speed_factor_relative = 1.0
                logger.info(
                    f"Segment {i} (Long - Borrow): natural_dur={natural_tts_dur:.2f}s, slot={effective_dur:.2f}s, "
                    f"borrowed from gap, speed_rel=1.0x"
                )
            
            actual_end = actual_start + (natural_tts_dur / speed_factor_relative)
            tts_dur = natural_tts_dur / speed_factor_relative
            
        # Hệ số điều chỉnh tốc độ thực tế áp dụng lên file gốc (1.0x)
        speed_factor = speed_factor_relative * tts_speed
        
        # Áp dụng atempo (cả speedup >1.0 lẫn slowdown <1.0)
        if abs(speed_factor - 1.0) > 0.01 and audio_path and os.path.exists(audio_path):
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
            except Exception as e:
                logger.warning(f"Segment {i} atempo failed: {e}")
 
        last_actual_end = actual_end
 
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


# ============================================================
# ASS Subtitle Generator (karaoke-style)
# ============================================================

ASS_DEFAULT_STYLE = {
    "font": "Montserrat",
    "fontsize": 22,
    "color": "&H00FFFFFF",       # Trắng (AABBGGRR format)
    "bg_color": "&H80000000",    # Đen 50% trong suốt
    "outline": 1.5,
    "shadow": 1,
    "alignment": 2,              # 2 = bottom-center
    "margin_l": 30,
    "margin_r": 30,
    "margin_v": 50,
}

# Available fonts in fonts/ directory
AVAILABLE_FONTS = [
    "BeVietnamPro", "Inter", "Lora", "Montserrat", "Nunito",
    "OpenSans", "Oswald", "PlayfairDisplay", "Quicksand", "Roboto"
]

# Available colors
AVAILABLE_COLORS = {
    "Trắng": "&H00FFFFFF",
    "Vàng": "&H0000FFFF",
    "Xanh lá": "&H0000FF00",
    "Xanh dương": "&H00FF0000",
    "Đỏ": "&H000000FF",
    "Hồng": "&H00FF80FF",
    "Cam": "&H0000A5FF",
    "Tím": "&H00FF0080",
}


def generate_ass(subtitles: list, output_ass_path: str, style: dict = None):
    """Tạo ASS subtitle với style tùy chỉnh (font, màu, kích thước, vị trí...).
    
    Args:
        subtitles: list segment có 'start', 'end', 'translation'
        output_ass_path: đường dẫn output .ass
        style: dict style config {font, fontsize, color, bg_color, outline, shadow, alignment, margin_l, margin_r, margin_v}
    """
    s = {**ASS_DEFAULT_STYLE, **(style or {})}
    
    font = s.get("font", "Montserrat")
    fontsize = int(s.get("fontsize", 22))
    color = s.get("color", "&H00FFFFFF")
    bg_color = s.get("bg_color", "&H80000000")
    outline = float(s.get("outline", 1.5))
    shadow = int(s.get("shadow", 1))
    alignment = int(s.get("alignment", 2))
    margin_l = int(s.get("margin_l", 30))
    margin_r = int(s.get("margin_r", 30))
    margin_v = int(s.get("margin_v", 50))
    
    os.makedirs(os.path.dirname(output_ass_path) if os.path.dirname(output_ass_path) else ".", exist_ok=True)
    
    with open(output_ass_path, "w", encoding="utf-8-sig") as f:
        # Script Header
        f.write("[Script Info]\n")
        f.write("Title: DouyinTranslate\n")
        f.write("ScriptType: v4.00+\n")
        f.write("WrapStyle: 0\n")
        f.write("ScaledBorderAndShadow: yes\n")
        f.write("PlayResX: 1920\n")
        f.write("PlayResY: 1080\n\n")
        
        # Style
        f.write("[V4+ Styles]\n")
        f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
                "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
                "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
        f.write(f"Style: Default,{font},{fontsize},{color},&H00000000,&H00000000,{bg_color},"
                f"0,0,0,0,100,100,0,0,1,{outline},{shadow},{alignment},"
                f"{margin_l},{margin_r},{margin_v},1\n\n")
        
        # Events
        f.write("[Events]\n")
        f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        
        for i, sub in enumerate(subtitles):
            if "actual_start" in sub:
                start = _sec_to_ass_time(sub["actual_start"])
                end = _sec_to_ass_time(sub["actual_end"])
            else:
                start = _sec_to_ass_time(sub.get("start", 0))
                end = _sec_to_ass_time(sub.get("end", 0))
            text = sub.get("translation", sub.get("text", "")).strip()
            if not text:
                continue
            text = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
            f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")
    
    logger.info(f"ASS subtitle written: {output_ass_path}")


def generate_ass_from_timeline(timeline: list, output_ass_path: str, style: dict = None):
    """Tạo ASS từ actual timeline (khớp chính xác với audio TTS)."""
    generate_ass(timeline, output_ass_path, style)


def _sec_to_ass_time(seconds: float) -> str:
    """Convert seconds to ASS time format H:MM:SS.cc"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
