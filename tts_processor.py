import os
import asyncio
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
        
        logger.info(f"Synthesizing TTS segment {idx}: '{text}' using {voice}")
        try:
            loop.run_until_complete(generate_segment_tts_async(text, voice, file_path))
            sub_copy = dict(sub)
            sub_copy["audio_path"] = os.path.abspath(file_path)
            updated_subtitles.append(sub_copy)
        except Exception as e:
            logger.error(f"Error generating TTS for segment {idx}: {e}")
            # Continue anyway
            
    loop.close()
    return updated_subtitles
