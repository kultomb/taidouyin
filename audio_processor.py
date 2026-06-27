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

def generate_srt(subtitles: list, output_srt_path: str):
    """Generates an SRT subtitle file from subtitle segment list."""
    logger.info(f"Writing subtitles to SRT: {output_srt_path}")
    os.makedirs(os.path.dirname(output_srt_path), exist_ok=True)
    
    with open(output_srt_path, "w", encoding="utf-8") as f:
        for idx, sub in enumerate(subtitles):
            start_str = format_timestamp(sub["start"])
            end_str = format_timestamp(sub["end"])
            # Use translation (Vietnamese)
            text = sub.get("translation", "").strip()
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
    _premix_tts_segments(tts_segments, tts_mixed_path, original_audio_path)
    
    # ============================================================
    # Pass 2: Mix video + bg audio + mixed TTS → final video
    # ============================================================
    cmd = ["ffmpeg", "-y"]
    cmd.extend(["-i", video_path])         # Input 0: video
    cmd.extend(["-i", original_audio_path]) # Input 1: bg audio
    cmd.extend(["-i", tts_mixed_path])      # Input 2: mixed TTS
    
    filter_complex = (
        f"[1:a]volume={bg_volume}[bg];"
        f"[bg][2:a]amix=inputs=2:duration=first[final_audio]"
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
        return os.path.abspath(output_video_path)
    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg error during mixing: {e.stderr}")
        raise e


def _premix_tts_segments(tts_segments: list, output_path: str, bg_audio_path: str):
    """Trộn tất cả TTS segments thành 1 file, mỗi segment được delay đúng start time."""
    logger.info(f"Pre-mixing {len(tts_segments)} TTS segments into single file...")
    
    # Dùng concat filter với adelay thay vì nhiều input riêng lẻ
    # Cách làm: tạo silence đệm cho từng segment, rồi concat
    # Hoặc: dùng amix với adelay - nhưng vẫn phải đưa từng file vào
    
    # Giải pháp: tạo 1 file silence dài bằng video, rồi amix từng TTS vào
    # Nhưng vẫn phải xử lý nhiều input...
    
    # Giải pháp tốt nhất: ghép tuần tự bằng concat protocol
    # Tạo file list cho concat
    import tempfile
    
    # Đo tổng duration của bg audio để biết độ dài tối đa
    total_duration = _get_audio_duration_ffprobe(bg_audio_path)
    if total_duration <= 0:
        total_duration = 9999  # fallback
    
    # Tạo concat file list với silence đệm giữa các segment
    concat_lines = []
    prev_end = 0.0
    
    for idx, sub in enumerate(tts_segments):
        start = sub["start"]
        audio_path = sub["audio_path"]
        
        if not os.path.exists(audio_path):
            continue
        
        # Nếu có khoảng trống trước segment này, thêm silence
        gap = start - prev_end
        if gap > 0.05:  # > 50ms mới thêm silence
            silence_file = os.path.join(tempfile.gettempdir(), f"_silence_{idx}.mp3")
            _generate_silence(silence_file, gap)
            concat_lines.append(f"file '{silence_file.replace(chr(92), '/')}'")
        
        concat_lines.append(f"file '{audio_path.replace(chr(92), '/')}'")
        prev_end = sub["end"]
    
    if not concat_lines:
        # Không có segment nào → copy bg audio
        import shutil
        shutil.copy2(bg_audio_path, output_path)
        return
    
    # Ghi file list
    list_file = os.path.join(tempfile.gettempdir(), "_tts_concat_list.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        f.write("\n".join(concat_lines))
    
    # Dùng concat demuxer
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c:a", "libmp3lame", "-q:a", "2",
        output_path
    ]
    
    logger.info(f"Concat {len(concat_lines)//2} TTS segments + silences...")
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=120)
        logger.info("TTS pre-mix completed.")
    except subprocess.CalledProcessError as e:
        logger.error(f"TTS pre-mix failed: {e.stderr.decode() if e.stderr else e}")
        # Fallback: dùng bg audio
        import shutil
        shutil.copy2(bg_audio_path, output_path)
    finally:
        # Dọn file tạm
        if os.path.exists(list_file):
            os.remove(list_file)


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
