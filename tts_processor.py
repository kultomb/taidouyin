import os
import asyncio
import subprocess
import edge_tts
import logging
from pathlib import Path

logger = logging.getLogger("douyin_translator")

# Mapping of speakers to edge-tts Vietnamese voices
VOICES = {
    "speaker a": "vi-VN-HoaiMyNeural",
    "speaker b": "vi-VN-NamMinhNeural",
    "default": "vi-VN-HoaiMyNeural"
}

def get_voice_for_speaker(speaker_name: str) -> str:
    """Returns a Vietnamese neural voice name for a given speaker label."""
    if not speaker_name:
        return VOICES["default"]
    
    clean_name = speaker_name.lower().strip()
    # Check if speaker label ends with 'a' or contains '1' etc.
    if "b" in clean_name or "2" in clean_name or "nam" in clean_name:
        return VOICES["speaker b"]
    elif "a" in clean_name or "1" in clean_name or "nu" in clean_name or "nữ" in clean_name:
        return VOICES["speaker a"]
        
    return VOICES["default"]

def get_audio_duration(file_path: str) -> float:
    """Đo duration thật của file audio bằng ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return float(result.stdout.strip())
    except Exception as e:
        logger.warning(f"Không thể đo duration của {file_path}: {e}")
        return 0.0

def adjust_tts_speed(input_path: str, output_path: str, target_duration: float) -> str:
    """
    Điều chỉnh tốc độ file TTS bằng atempo để khớp với target_duration.
    Nếu chênh lệch < 10% thì không cần chỉnh.
    Trả về path của file đã chỉnh (hoặc file gốc nếu không cần chỉnh).
    """
    actual_duration = get_audio_duration(input_path)
    if actual_duration <= 0 or target_duration <= 0:
        return input_path
    
    ratio = actual_duration / target_duration
    # Chỉ điều chỉnh nếu chênh lệch > 10%
    if 0.9 <= ratio <= 1.1:
        logger.debug(f"TTS duration {actual_duration:.2f}s ~= target {target_duration:.2f}s, skip atempo")
        return input_path
    
    # atempo chỉ hỗ trợ 0.5 - 2.0, nếu ngoài khoảng thì chain 2 lần
    atempo = ratio
    logger.info(f"Adjusting TTS speed: {actual_duration:.2f}s -> {target_duration:.2f}s (atempo={atempo:.3f})")
    
    try:
        # Nếu atempo ngoài khoảng [0.5, 2.0], dùng 2 filter chain
        if atempo < 0.5:
            atempo1 = atempo * 2  # < 1.0
            atempo_filter = f"atempo={atempo1:.4f},atempo=0.5"
        elif atempo > 2.0:
            atempo1 = atempo / 2  # > 1.0
            atempo_filter = f"atempo={atempo1:.4f},atempo=2.0"
        else:
            atempo_filter = f"atempo={atempo:.4f}"
        
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-filter:a", atempo_filter,
            "-q:a", "2",
            output_path
        ]
        subprocess.run(cmd, capture_output=True, check=True, timeout=30)
        return output_path
    except Exception as e:
        logger.warning(f"Failed to adjust TTS speed: {e}, using original")
        return input_path

async def generate_segment_tts_async(text: str, voice: str, output_path: str):
    """Asynchronously calls edge-tts to generate an audio segment."""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def generate_tts_for_subtitles(subtitles: list, output_dir: str = "output/tts") -> list:
    """
    Generates a WAV/MP3 file for each subtitle segment using edge-tts.
    Returns the list of subtitles with a new 'audio_path' key pointing to each file.
    """
    logger.info(f"Generating TTS for {len(subtitles)} subtitle segments...")
    os.makedirs(output_dir, exist_ok=True)
    
    # We use an async wrapper to run edge-tts since edge-tts is built on asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    updated_subtitles = []
    for idx, sub in enumerate(subtitles):
        text = sub.get("translation", "")
        speaker = sub.get("speaker", "default")
        voice = get_voice_for_speaker(speaker)
        
        # Clean text
        text = text.replace("[", "").replace("]", "").strip()
        if not text:
            # Skip empty translation segments
            continue
            
        file_path = os.path.join(output_dir, f"tts_{idx:04d}.mp3")
        
        logger.info(f"Synthesizing TTS segment {idx}: '{text[:40]}...' using {voice}")
        try:
            loop.run_until_complete(generate_segment_tts_async(text, voice, file_path))
            
            # Điều chỉnh tốc độ TTS để khớp với duration segment gốc
            segment_duration = sub["end"] - sub["start"]
            adjusted_path = os.path.join(output_dir, f"tts_{idx:04d}_adjusted.mp3")
            final_path = adjust_tts_speed(file_path, adjusted_path, segment_duration)
            
            sub_copy = dict(sub)
            sub_copy["audio_path"] = os.path.abspath(final_path)
            updated_subtitles.append(sub_copy)
        except Exception as e:
            logger.error(f"Error generating TTS for segment {idx}: {e}")
            # Continue anyway
            
    loop.close()
    return updated_subtitles
