import os
import json
import logging
from pathlib import Path
from google import genai
from google.genai import types, errors
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_not_exception_type

logger = logging.getLogger("douyin_translator")

# Credentials từ environment variables (không hardcode)
# GOOGLE_APPLICATION_CREDENTIALS: path tới JSON key
# GOOGLE_CLOUD_PROJECT: project ID (tùy chọn, đọc từ JSON nếu không có)
# GOOGLE_CLOUD_LOCATION: region (mặc định us-central1)
JSON_PATH = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "full-video-499000")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

class TranslateError(Exception):
    pass

class StopTask(Exception):
    pass

NO_RETRY_EXCEPT = (StopTask,)

def get_vertex_client(json_path: str = JSON_PATH) -> genai.Client:
    """Creates a Vertex AI GenAI Client using a service account JSON file."""
    if not os.path.exists(json_path):
        logger.error(f"Service account file not found at {json_path}")
        raise StopTask(f"Service account file not found at {json_path}")
        
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = json_path
    
    # Read project ID dynamically from JSON key
    try:
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        project_id = data.get("project_id", PROJECT_ID)
        logger.info(f"Loaded credentials for project: {project_id}")
    except Exception as e:
        logger.warning(f"Could not read project ID from JSON file, using default: {PROJECT_ID}. Error: {e}")
        project_id = PROJECT_ID
        
    return genai.Client(
        vertexai=True,
        project=project_id,
        location=LOCATION,
    )

import concurrent.futures
import subprocess
import tempfile

def get_audio_duration_local(file_path: str) -> float:
    """Đo duration thật của file audio hoặc video bằng ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return float(result.stdout.strip())
    except Exception:
        return 0.0

@retry(
    retry=retry_if_not_exception_type(NO_RETRY_EXCEPT),
    stop=stop_after_attempt(3),
    wait=wait_fixed(3),
    reraise=True
)
def transcribe_chunk_with_gemini(client: genai.Client, chunk_path: str) -> dict:
    """Gửi một đoạn âm thanh/video ngắn (30s) qua Gemini."""
    file_bytes = Path(chunk_path).read_bytes()
    
    ext = Path(chunk_path).suffix.lower()
    if ext == ".mp4":
        mime_type = "video/mp4"
    elif ext == ".mp3":
        mime_type = "audio/mp3"
    elif ext == ".wav":
        mime_type = "audio/wav"
    elif ext in (".ogg", ".oga"):
        mime_type = "audio/ogg"
    else:
        mime_type = "audio/mpeg"
        
    if mime_type.startswith("video/"):
        prompt = (
            "You are an expert video transcriber, translator, and subtitler. "
            "Analyze the video and audio input, transcribe the speech exactly, then translate it into Vietnamese. "
            "Divide the text into short segments (sentences/clauses) and determine the start and end timestamps in seconds "
            "for each segment relative to the start of this clip (0.0s) based on both speech and visual actions (lip movements, screen events). "
            "Also identify the speaker for each segment (e.g. Speaker A, Speaker B)."
        )
    else:
        prompt = (
            "You are an expert audio transcriber, translator, and subtitler. "
            "Listen to the audio input and transcribe the speech exactly, then translate it into Vietnamese. "
            "Divide the text into short segments (sentences/clauses) and determine the start and end timestamps in seconds "
            "for each segment relative to the start of this audio clip (0.0s). Also identify the speaker for each segment (e.g. Speaker A, Speaker B)."
        )
    
    schema = {
        "type": "OBJECT",
        "properties": {
            "subtitles": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "start": {"type": "NUMBER", "description": "Start time in seconds of the spoken segment"},
                        "end": {"type": "NUMBER", "description": "End time in seconds of the spoken segment"},
                        "speaker": {"type": "STRING", "description": "Speaker label (e.g., Speaker A)"},
                        "text": {"type": "STRING", "description": "Original transcript in the native language (Chinese)"},
                        "translation": {"type": "STRING", "description": "Vietnamese translation of the transcript"}
                    },
                    "required": ["start", "end", "speaker", "text", "translation"]
                }
            }
        },
        "required": ["subtitles"]
    }
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_text(text=prompt),
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.2,
                thinking_config=types.ThinkingConfig(thinking_budget=0)
            )
        )
        
        if not response.text:
            return {"subtitles": []}
            
        return json.loads(response.text)
        
    except errors.APIError as e:
        logger.error(f"Vertex API Error in chunk: code={e.code}, message={e.message}")
        if e.code in (400, 403, 404, 500):
            raise StopTask(f"Fatal API error: {e.message}")
        if e.code == 429:
            raise TranslateError("Rate limit / Quota exceeded, retrying...")
        raise TranslateError(e.message)
    except Exception as e:
        logger.error(f"Error during chunk processing: {str(e)}")
        if isinstance(e, StopTask):
            raise e
        raise TranslateError(f"Unexpected error: {str(e)}")

def transcribe_and_translate_audio(client: genai.Client, audio_path: str) -> dict:
    """
    Tự động chia nhỏ âm thanh/video thành các đoạn 30s, chạy nhận diện song song qua Gemini
    để đảm bảo không bị bỏ sót câu thoại và mốc thời gian khớp khít tuyệt đối.
    """
    logger.info(f"Sending file to Gemini for ASR and Translation (Chunked Mode): {audio_path}")
    
    if not os.path.exists(audio_path):
        raise StopTask(f"File not found: {audio_path}")
        
    total_duration = get_audio_duration_local(audio_path)
    if total_duration <= 0:
        raise StopTask("Không thể đo thời lượng của file đầu vào.")
        
    logger.info(f"Tổng thời lượng tệp tin: {total_duration:.2f} giây. Bắt đầu chia nhỏ thành các đoạn 30s...")
    
    ext = Path(audio_path).suffix.lower()
    chunk_size = 30.0
    chunks = []
    start_time = 0.0
    while start_time < total_duration:
        end_time = min(start_time + chunk_size, total_duration)
        chunks.append((start_time, end_time))
        start_time += chunk_size

    results = []
    
    # Hàm xử lý một phân đoạn nhỏ
    def process_chunk(chunk_idx: int, start: float, end: float) -> list:
        duration = end - start
        chunk_file = os.path.join(tempfile.gettempdir(), f"_chunk_{chunk_idx}_{start:.0f}{ext}")
        
        # Cắt âm thanh/video cực nhanh bằng FFmpeg copy
        if ext == ".mp4":
            cmd = [
                "ffmpeg", "-y",
                "-ss", f"{start:.3f}",
                "-t", f"{duration:.3f}",
                "-i", audio_path,
                "-c:v", "copy", "-c:a", "copy",
                chunk_file
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-ss", f"{start:.3f}",
                "-t", f"{duration:.3f}",
                "-i", audio_path,
                "-c", "copy",
                chunk_file
            ]
            
        try:
            subprocess.run(cmd, capture_output=True, check=True, timeout=30)
        except Exception as e:
            logger.error(f"Lỗi cắt chunk {chunk_idx}: {e}")
            return []
            
        # Gửi nhận diện qua Gemini
        try:
            chunk_result = transcribe_chunk_with_gemini(client, chunk_file)
            subtitles = chunk_result.get("subtitles", [])
            
            # Cộng offset thời gian thực tế
            for sub in subtitles:
                sub["start"] = round(start + sub["start"], 3)
                sub["end"] = round(start + sub["end"], 3)
                
            return subtitles
        except Exception as e:
            logger.error(f"Lỗi nhận dạng tại chunk {chunk_idx} ({start}s -> {end}s): {e}")
            return []
        finally:
            if os.path.exists(chunk_file):
                try:
                    os.remove(chunk_file)
                except OSError:
                    pass

    # Chạy song song đa luồng (tối đa 4 luồng cùng lúc để tránh rate limit)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(process_chunk, idx, start, end) for idx, (start, end) in enumerate(chunks)]
        for fut in concurrent.futures.as_completed(futures):
            results.extend(fut.result())
            
    # Hợp nhất và sắp xếp theo mốc thời gian tăng dần
    results.sort(key=lambda x: x.get("start", 0.0))
    
    logger.info(f"Hoàn thành nhận dạng toàn bộ video. Tổng số phân đoạn: {len(results)}")
    return {"subtitles": results}
