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
    Saves the final video to output_video_path.
    """
    logger.info(f"Mixing video and voiceover: {video_path}")
    os.makedirs(os.path.dirname(output_video_path), exist_ok=True)
    
    # We build the ffmpeg inputs:
    # Input 0: original video
    # Input 1: original audio (used as bg music)
    # Inputs 2+: each TTS segment
    cmd = ["ffmpeg", "-y"]
    cmd.extend(["-i", video_path])
    cmd.extend(["-i", original_audio_path])
    
    for sub in tts_segments:
        cmd.extend(["-i", sub["audio_path"]])
        
    filter_complex = []
    tts_labels = []
    
    for idx, sub in enumerate(tts_segments):
        start_ms = int(sub["start"] * 1000)
        # Delay left and right channels for stereo sound
        filter_complex.append(f"[{idx+2}:a]adelay={start_ms}|{start_ms}[t{idx}]")
        tts_labels.append(f"[t{idx}]")
        
    if tts_labels:
        # Combine all delayed TTS files using amix
        filter_complex.append(f"{''.join(tts_labels)}amix=inputs={len(tts_labels)}:normalize=0[tts_voice]")
        # Set original audio volume (background music)
        filter_complex.append(f"[1:a]volume={bg_volume}[bg]")
        # Mix background music and TTS voiceover
        filter_complex.append(f"[bg][tts_voice]amix=inputs=2:duration=first[final_audio]")
    else:
        # If no TTS segments, just copy/use original audio
        filter_complex.append(f"[1:a]volume=1.0[final_audio]")
        
    cmd.extend(["-filter_complex", ";".join(filter_complex)])
    
    # Audio codec settings
    cmd.extend(["-map", "0:v"])  # Map video from input 0
    cmd.extend(["-map", "[final_audio]"])  # Map our mixed audio
    cmd.extend(["-c:v", "copy"])  # Copy video stream directly (fast, no re-encode)
    cmd.extend(["-c:a", "aac", "-b:a", "192k"])  # Encode audio as AAC
    
    # If burning subtitles, we cannot use -c:v copy because we need to re-encode the video
    if burn_subtitles and srt_path and os.path.exists(srt_path):
        # Remove the "-c:v copy" from command arguments and insert subtitle filter
        cmd.remove("copy")
        # Replace map and copy
        idx_cv = cmd.index("-c:v")
        # We need to re-encode to burn subtitles. Let's use libx264
        cmd[idx_cv + 1] = "libx264"
        # We need to add subtitle video filter. Note: on Windows, ffmpeg path backslashes need escaping for the subtitles filter
        escaped_srt_path = srt_path.replace("\\", "/").replace(":", "\\:")
        cmd.extend(["-vf", f"subtitles='{escaped_srt_path}'"])
        
    cmd.append(output_video_path)
    
    logger.info(f"Running ffmpeg command: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        logger.info("Video export and mixing completed successfully.")
        return os.path.abspath(output_video_path)
    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg error during mixing: {e.stderr}")
        raise e
