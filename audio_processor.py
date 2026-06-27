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
    srt_path: str = None
) -> str:
    """
    Mixes the original video, original audio (reduced volume for background music),
    and TTS audio clips (aligned to their start timestamps).
    
    Strategy: Pre-mix all TTS segments into one file first (tránh command line quá dài trên Windows),
    then mix video + bg + mixed_tts in a second pass.
    """
    logger.info(f"Mixing video and voiceover: {video_path}")
    out_dir = os.path.dirname(output_video_path)
    os.makedirs(out_dir, exist_ok=True)
    
    # ============================================================
    # Pass 1: Mix tất cả TTS segments thành 1 file duy nhất
    # ============================================================
    tts_mixed_path = os.path.join(out_dir, "_tts_mixed.mp3")
    actual_timeline = _premix_tts_segments(tts_segments, tts_mixed_path)
    
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


def _premix_tts_segments(tts_segments: list, output_path: str) -> list:
    """
    Trộn tất cả TTS segments thành 1 file với timeline động.
    
    Thay vì ép TTS vào slot gốc (gây robot voice), ta:
    1. Giữ TTS tốc độ tự nhiên
    2. Thêm silence giữa các segment để align với nhịp gốc
    3. Cross-fade 50ms giữa các segment
    
    Returns:
        list actual_timeline: [{start, end, audio_path}, ...] với timestamp thực tế
    """
    logger.info(f"Pre-mixing {len(tts_segments)} TTS segments with dynamic timeline...")
    import tempfile

    # Bước 1: Tính timeline thực tế
    actual_timeline = _compute_actual_timeline(tts_segments)

    # Bước 2: Tạo concat list với silence động (không cross-fade để tránh bug lặp segment)
    concat_parts = []
    silence_files = []
    accumulated_duration = 0.0

    for i, seg in enumerate(actual_timeline):
        audio_path = seg["audio_path"]
        if not os.path.exists(audio_path):
            continue

        # Tính khoảng lặng dựa trên thời lượng tích lũy thực tế
        gap = seg["actual_start"] - accumulated_duration
        if gap > 0.03:
            silence_file = os.path.join(tempfile.gettempdir(), f"_silence_{i}.mp3")
            _generate_silence(silence_file, gap)
            concat_parts.append(silence_file)
            silence_files.append(silence_file)
            accumulated_duration += gap

        concat_parts.append(audio_path)
        accumulated_duration += seg["tts_duration"]

    if not concat_parts:
        _generate_silence(output_path, 1.0)
        return actual_timeline

    # Ghi file list cho concat
    list_file = os.path.join(tempfile.gettempdir(), "_tts_concat_list.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for p in concat_parts:
            f.write(f"file '{p.replace(chr(92), '/')}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c:a", "libmp3lame", "-q:a", "2",
        output_path
    ]

    logger.info(f"Concat {len(actual_timeline)} TTS segments with dynamic timing...")
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=120)
        logger.info("TTS pre-mix completed with natural timing.")
    except subprocess.CalledProcessError as e:
        logger.error(f"TTS pre-mix failed: {e.stderr.decode() if e.stderr else e}")
        _generate_silence(output_path, 1.0)
    finally:
        # Dọn file tạm
        for f in silence_files:
            try:
                os.remove(f)
            except OSError:
                pass
        try:
            os.remove(list_file)
        except OSError:
            pass

    return actual_timeline


def _compute_actual_timeline(segments: list) -> list:
    """
    Tính timeline thực tế với adaptive atempo cho từng phân đoạn thoại
    để khớp khít 100% với thời lượng và mốc thời gian của câu gốc.
    """
    import tempfile
    
    timeline = []
    current_time = 0.0

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
        
        # Nếu câu dịch dài hơn câu gốc, tự động tăng tốc đọc nhẹ để khớp khít thời lượng gốc
        if tts_dur > original_dur and original_dur > 0.2:
            raw_factor = tts_dur / original_dur
            # Giới hạn tốc độ tăng tối đa là 1.3 để giữ giọng nghe tự nhiên
            speed_factor = min(1.3, raw_factor)
            
            if speed_factor > 1.02 and audio_path and os.path.exists(audio_path):
                logger.info(f"Segment {i} too long: {tts_dur:.2f}s vs {original_dur:.2f}s -> speedup atempo={speed_factor:.3f}")
                adjusted_path = os.path.join(tempfile.gettempdir(), f"_atempo_{i}.mp3")
                try:
                    cmd = [
                        "ffmpeg", "-y", "-i", audio_path,
                        "-filter:a", f"atempo={speed_factor:.4f}",
                        "-c:a", "libmp3lame", "-q:a", "2",
                        adjusted_path
                    ]
                    subprocess.run(cmd, capture_output=True, check=True, timeout=30)
                    audio_path = adjusted_path
                    tts_dur = tts_dur / speed_factor
                except Exception as e:
                    logger.warning(f"Segment {i} atempo failed: {e}")

        # Đồng bộ hóa mốc thời gian với bản gốc (chỉ lùi nếu câu trước bị tràn quá giới hạn speed 1.3)
        actual_start = max(current_time, original_start)
        actual_end = actual_start + tts_dur

        # Đảm bảo khoảng nghỉ tối thiểu 50ms giữa các câu thoại
        if i > 0 and timeline:
            actual_start = max(actual_start, timeline[-1]["actual_end"] + 0.05)
            actual_end = actual_start + tts_dur

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
        })

        current_time = actual_end

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
