"""
🎬 AI Re-Edit Pipeline (MODE 2 - Full Implementation)
Pipeline: Download → ASR → Scene Analyzer → Vision Analyzer → Edit Planner → Render
"""
import os
import json
import time
import shutil
import logging

from downloader import download_douyin_video
from audio_processor import extract_audio, generate_srt

logger = logging.getLogger("douyin_translator")


class ReEditPipeline:
    """Pipeline AI Re-Edit video (Mode 2)."""

    def __init__(self, job_store: dict):
        self.jobs = job_store

    def _make_logger(self, job: dict, job_id: str):
        def log(msg: str):
            ts = time.strftime("%H:%M:%S")
            line = f"[{ts}] INFO - {msg}"
            job["logs"].append(line)
            logger.info(f"[reedit:{job_id}] {msg}")
        return log

    # ==================================================================
    # MAIN PIPELINE
    # ==================================================================
    def run(self, job_id: str, url: str):
        job = self.jobs.get(job_id)
        if not job:
            return

        project_id = f"reedit_{time.strftime('%Y%m%d_%H%M%S')}"
        project_dir = f"projects/{project_id}"
        for sub in ["audio", "subtitles", "frames", "analysis", "edit", "output"]:
            os.makedirs(os.path.join(project_dir, sub), exist_ok=True)

        job["project_dir"] = project_dir
        job["project_id"] = project_id
        log = self._make_logger(job, job_id)

        try:
            # ── STEP 1: Download Video ─────────────────────
            job["step"] = 1
            job["sub_step"] = "STEP 1/6: Dang tai video goc..."
            log("Dang tai video tu nguon...")

            video_path = download_douyin_video(url, os.path.join(project_dir, "output"))
            if not video_path or not os.path.exists(video_path):
                raise RuntimeError("Tai video that bai.")

            source_path = os.path.join(project_dir, "source.mp4")
            if video_path != source_path:
                shutil.copy2(video_path, source_path)
            job["video_path"] = source_path
            log(f"Video da tai: {source_path}")

            # ── STEP 2: Extract Audio + ASR ────────────────
            job["step"] = 2
            job["sub_step"] = "STEP 2/6: Dang tach am thanh & nhan dang giong noi..."
            log("Dang tach am thanh va chay ASR...")

            audio_path = os.path.join(project_dir, "audio", "original.wav")
            extract_audio(source_path, audio_path)

            srt_segments = []
            try:
                from translator import transcribe_audio_local_whisper
                result = transcribe_audio_local_whisper(audio_path)
                srt_segments = result.get("subtitles", [])
                log(f"Whisper nhan dang {len(srt_segments)} doan.")
            except Exception as e:
                log(f"Whisper khong kha dung, thu Gemini ASR: {str(e)[:80]}")
                try:
                    from translator import get_vertex_client, transcribe_and_translate_audio
                    client = get_vertex_client()
                    result = transcribe_and_translate_audio(client, audio_path)
                    srt_segments = result.get("subtitles", [])
                    log(f"Gemini ASR nhan dang {len(srt_segments)} doan.")
                except Exception as e2:
                    log(f"Gemini ASR cung loi: {str(e2)[:80]}. Dung SRT gia lap.")
                    srt_segments = self._dummy_srt(source_path)

            srt_path = os.path.join(project_dir, "subtitles", "source.srt")
            generate_srt(srt_segments, srt_path, use_original=True)
            job["srt_segments"] = srt_segments[:]
            log(f"SRT da luu: {srt_path}")

            # ── STEP 3: Scene Analyzer (Gemini) ────────────
            job["step"] = 3
            job["sub_step"] = "STEP 3/6: Dang phan tich canh bang Gemini AI..."
            log("Gemini dang phan tich noi dung & phan canh...")
            scenes = self._analyze_scenes(srt_segments, source_path, log)
            scenes_path = os.path.join(project_dir, "analysis", "scenes.json")
            with open(scenes_path, "w", encoding="utf-8") as f:
                json.dump(scenes, f, ensure_ascii=False, indent=2)
            job["scenes"] = scenes
            log(f"Phan tich {len(scenes)} canh. Da luu scenes.json")

            # ── STEP 4: Vision Analyzer (Gemini Vision) ────
            job["step"] = 4
            job["sub_step"] = "STEP 4/6: Dang phan tich hinh anh tung canh..."
            log("Dang trich frame & phan tich visual style...")
            style_info = self._analyze_vision(source_path, scenes, project_dir, log)
            style_path = os.path.join(project_dir, "analysis", "style.json")
            with open(style_path, "w", encoding="utf-8") as f:
                json.dump(style_info, f, ensure_ascii=False, indent=2)
            log(f"Phan tich visual: {style_info.get('genre', 'unknown')} | {style_info.get('style', 'unknown')}")

            # ── STEP 5: Edit Planner (Gemini) ──────────────
            job["step"] = 5
            job["sub_step"] = "STEP 5/6: Dang lap ke hoach chinh sua..."
            log("Gemini dang quyet dinh: KEEP / CUT / ENHANCE / REPLACE...")
            edit_plan = self._create_edit_plan(scenes, style_info, log)
            plan_path = os.path.join(project_dir, "edit", "edit_plan.json")
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(edit_plan, f, ensure_ascii=False, indent=2)
            job["edit_plan"] = edit_plan
            log(f"Edit plan: {len(edit_plan)} decisions")

            # ── STEP 6: Render Engine ──────────────────────
            job["step"] = 6
            job["sub_step"] = "STEP 6/6: Dang render video ket qua..."
            log("Dang ghep video theo edit plan...")
            output_path = self._render_video(source_path, audio_path, scenes, edit_plan, project_dir, log)
            job["output_video"] = output_path
            log(f"Video ket qua: {output_path}")

            # ── DONE ──
            job["status"] = "completed"
            job["sub_step"] = "Hoan thanh! Video da san sang."
            log("AI Re-Edit hoan tat!")

        except Exception as e:
            logger.error(f"ReEdit pipeline failure: {str(e)}", exc_info=True)
            job["status"] = "failed"
            job["error"] = str(e)
            job["sub_step"] = f"LOI: {str(e)[:80]}"
            log(f"LOI: {str(e)}")

    # ==================================================================
    # STEP 3: SCENE ANALYZER (Gemini AI)
    # ==================================================================
    def _analyze_scenes(self, srt_segments: list, video_path: str, log) -> list:
        """Dung Gemini phan tich SRT thanh cac scene co y nghia."""
        if not srt_segments:
            return self._group_by_time(srt_segments)

        text_batch = []
        for i, seg in enumerate(srt_segments):
            text_batch.append(f"[{i}] {seg.get('start', 0):.1f}s-{seg.get('end', 0):.1f}s: {seg.get('text', '')}")

        batch_str = "\n".join(text_batch[:80])

        try:
            from translator import get_vertex_client
            from google.genai import types

            client = get_vertex_client()
            prompt = f"""You are a professional video editor AI. Analyze the following subtitle timeline and group segments into logical SCENES.

For each scene, provide:
- id: scene number
- start: start time in seconds
- end: end time in seconds
- summary: ONE sentence in Vietnamese describing what happens
- importance: 1-10
- emotion: one word (dramatic, funny, tense, calm, informative, etc.)

Subtitle timeline:
{batch_str}

Return ONLY a JSON array. Example:
[{{"id":1,"start":0,"end":25,"summary":"Co gai buoc vao khu rung toi","importance":8,"emotion":"mystery"}}]"""

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3
                )
            )

            if response and response.text:
                scenes = json.loads(response.text)
                if isinstance(scenes, list) and len(scenes) > 0:
                    log(f"  Gemini phan tich duoc {len(scenes)} canh.")
                    return scenes

        except Exception as e:
            log(f"  Gemini scene analyzer loi: {str(e)[:80]}")

        return self._group_by_time(srt_segments)

    def _group_by_time(self, segments: list) -> list:
        """Fallback: Gom SRT theo khoang lang > 1.5s."""
        if not segments:
            return []
        scenes = []
        cur = {"id": 1, "start": segments[0].get("start", 0),
               "end": segments[0].get("end", 0),
               "text": segments[0].get("text", ""),
               "summary": "Tu dong gom", "importance": 5, "emotion": "neutral"}
        for seg in segments[1:]:
            gap = seg.get("start", 0) - cur["end"]
            if gap > 1.5 or (cur["end"] - cur["start"]) > 25:
                scenes.append(cur)
                cur = {"id": len(scenes) + 1, "start": seg.get("start", 0),
                       "end": seg.get("end", 0),
                       "text": seg.get("text", ""),
                       "summary": "Tu dong gom", "importance": 5, "emotion": "neutral"}
            else:
                cur["end"] = seg.get("end", 0)
                cur["text"] += " " + seg.get("text", "")
        scenes.append(cur)
        return scenes

    # ==================================================================
    # STEP 4: VISION ANALYZER (Gemini Vision)
    # ==================================================================
    def _analyze_vision(self, video_path: str, scenes: list, project_dir: str, log) -> dict:
        """Trich frame tu video + dung Gemini Vision phan tich visual style."""
        import subprocess

        frames_dir = os.path.join(project_dir, "frames")
        os.makedirs(frames_dir, exist_ok=True)

        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                capture_output=True, text=True, timeout=10
            )
            duration = float(result.stdout.strip())
        except Exception:
            duration = 60.0

        frame_paths = []
        sample_times = []
        interval = max(3, duration / 6)
        t = interval / 2
        while t < duration and len(sample_times) < 5:
            sample_times.append(t)
            t += interval

        for i, ts in enumerate(sample_times):
            frame_path = os.path.join(frames_dir, f"frame_{i:03d}.jpg")
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(ts), "-i", video_path,
                 "-vframes", "1", "-q:v", "3", frame_path],
                capture_output=True, timeout=15
            )
            if os.path.exists(frame_path) and os.path.getsize(frame_path) > 100:
                frame_paths.append((ts, frame_path))

        if not frame_paths:
            return {"style": "unknown", "genre": "unknown", "location": "unknown",
                    "camera": "standard", "color": "neutral", "characters": [], "quality_score": 5}

        log(f"  Da trich {len(frame_paths)} frames. Dang goi Gemini Vision...")
        return self._call_vision_api(frame_paths, log)

    def _call_vision_api(self, frame_paths: list, log) -> dict:
        """Goi Gemini Vision phan tich frame."""
        try:
            from translator import get_vertex_client
            from google.genai import types
            import base64

            client = get_vertex_client()

            parts = []
            for ts, fpath in frame_paths:
                with open(fpath, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                parts.append(types.Part.from_uri(
                    file_uri=f"data:image/jpeg;base64,{b64}",
                    mime_type="image/jpeg"
                ))

            parts.append(types.Part.from_text(
                """Analyze these video frames and describe the VISUAL STYLE in JSON:
{
  "style": "cinematic realistic / anime / documentary / vlog / gaming / other",
  "genre": "fantasy / action / drama / comedy / tutorial / review / game / other",
  "location": "indoor / outdoor / studio / forest / city / room / other",
  "camera": "static / handheld / cinematic / drone / screen recording",
  "color": "warm / cool / dark / bright / neutral",
  "characters": [{"name":"description"}],
  "quality_score": 1-10
}
Return ONLY valid JSON."""
            ))

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2
                )
            )

            if response and response.text:
                result = json.loads(response.text)
                log(f"  Visual: {result.get('style', '?')} | {result.get('genre', '?')} | quality={result.get('quality_score', '?')}/10")
                return result

        except Exception as e:
            log(f"  Vision API loi: {str(e)[:80]}")

        return {"style": "unknown", "genre": "unknown", "location": "unknown",
                "camera": "standard", "color": "neutral", "characters": [], "quality_score": 5}

    # ==================================================================
    # STEP 5: EDIT PLANNER (Gemini AI)
    # ==================================================================
    def _create_edit_plan(self, scenes: list, style_info: dict, log) -> list:
        """Gemini quyet dinh hanh dong cho tung scene: KEEP / CUT / ENHANCE / REPLACE."""
        if not scenes:
            return []

        scene_list = []
        for s in scenes:
            scene_list.append({
                "id": s["id"],
                "start": s["start"],
                "end": s["end"],
                "duration": round(s["end"] - s["start"], 1),
                "summary": s.get("summary", ""),
                "importance": s.get("importance", 5),
                "emotion": s.get("emotion", "neutral")
            })

        input_json = json.dumps({
            "video_style": style_info,
            "scenes": scene_list
        }, ensure_ascii=False, indent=2)

        try:
            from translator import get_vertex_client
            from google.genai import types

            client = get_vertex_client()
            prompt = f"""You are an expert video editor. For each scene, decide ONE action:

- KEEP: Scene is good, keep as is
- CUT: Scene is boring/redundant, remove it
- ENHANCE: Scene is OK but could be improved
- REPLACE: Scene quality is low, replace with AI-generated video

Rules:
- KEEP at least 40% of scenes
- CUT scenes with importance < 4 AND duration > 10s
- ENHANCE scenes with quality urgency
- REPLACE max 30% of scenes
- Total duration should stay similar

Input:
{input_json}

Return ONLY a JSON array:
[{{"scene":1,"action":"KEEP","reason":"...","effect":null,"prompt":null}}]
For REPLACE, include "prompt": "cinematic AI video generation prompt in English"
For ENHANCE, include "effect": "zoom / color grade / slow motion / etc."
"""

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.4
                )
            )

            if response and response.text:
                plan = json.loads(response.text)
                if isinstance(plan, list):
                    actions = {}
                    for p in plan:
                        a = p.get("action", "KEEP")
                        actions[a] = actions.get(a, 0) + 1
                    log(f"  Plan: {actions}")
                    return plan

        except Exception as e:
            log(f"  Edit planner loi: {str(e)[:80]}")

        return [{"scene": s["id"], "action": "KEEP", "reason": "Auto fallback", "effect": None, "prompt": None} for s in scenes]

    # ==================================================================
    # STEP 6: RENDER ENGINE (FFmpeg + AI Enhance/Replace)
    # ==================================================================
    def _render_video(self, source_path: str, audio_path: str,
                      scenes: list, edit_plan: list,
                      project_dir: str, log) -> str:
        import subprocess

        output_path = os.path.join(project_dir, "output", "final.mp4")
        concat_file = os.path.join(project_dir, "edit", "concat_list.txt")
        ai_dir = os.path.join(project_dir, "edit", "ai_clips")
        os.makedirs(ai_dir, exist_ok=True)

        # Lấy video info
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height,r_frame_rate",
                 "-of", "csv=p=0", source_path],
                capture_output=True, text=True, timeout=10)
            w, h, fps_str = result.stdout.strip().split(",")
            width = int(w)
            height = int(h)
            fps = eval(fps_str) if fps_str else 30
        except Exception:
            width, height, fps = 1920, 1080, 30

        scene_map = {s["id"]: s for s in scenes} if scenes else {}
        clip_files = []
        kept = cut = enhanced = replaced = 0

        for decision in edit_plan:
            scene_id = decision.get("scene", 0)
            action = decision.get("action", "KEEP")
            scene = scene_map.get(scene_id, {})
            start = scene.get("start", 0)
            end = scene.get("end", 0)
            dur = end - start
            if dur <= 0.5:
                continue

            if action == "CUT":
                cut += 1
                log(f"  CUT scene {scene_id} ({start:.0f}s-{end:.0f}s)")
                continue

            # ENHANCE: tạo clip với hiệu ứng FFmpeg
            if action == "ENHANCE":
                enhanced += 1
                effect = decision.get("effect", "color")
                clip_path = os.path.join(ai_dir, f"enhance_{scene_id:03d}.mp4")
                self._render_enhance_clip(source_path, clip_path, start, dur,
                                          effect, width, height, fps, log)

            # REPLACE: tạo ảnh AI + Ken Burns
            elif action == "REPLACE":
                replaced += 1
                prompt = decision.get("prompt", "cinematic scene")
                clip_path = os.path.join(ai_dir, f"replace_{scene_id:03d}.mp4")
                self._render_replace_clip(clip_path, prompt, dur, width, height,
                                          fps, source_path, start, log)

            else:  # KEEP: trích clip gốc
                kept += 1
                clip_path = os.path.join(ai_dir, f"keep_{scene_id:03d}.mp4")
                subprocess.run([
                    "ffmpeg", "-y", "-ss", str(start), "-t", str(dur),
                    "-i", source_path,
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                    "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart", clip_path
                ], capture_output=True, timeout=60)

            if os.path.exists(clip_path) and os.path.getsize(clip_path) > 1000:
                clip_files.append(clip_path)

        log(f"  KEEP={kept} CUT={cut} ENHANCE={enhanced} REPLACE={replaced}")

        if not clip_files:
            log("  Tat ca bi CUT! Giu nguyen video goc.")
            shutil.copy2(source_path, output_path)
            return output_path

        # Ghi concat list
        with open(concat_file, "w", encoding="utf-8") as f:
            for cf in clip_files:
                f.write(f"file '{os.path.abspath(cf)}'\n")

        # FFmpeg concat + audio
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_file,
            "-i", audio_path,
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest", "-movflags", "+faststart", output_path
        ]
        log("  Dang chay FFmpeg concat...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            log(f"  FFmpeg concat failed, fallback copy.")
            shutil.copy2(source_path, output_path)

        return output_path

    # ── ENHANCE: FFmpeg effects ────────────────────────────
    def _render_enhance_clip(self, src: str, dst: str, start: float, dur: float,
                             effect: str, w: int, h: int, fps: float, log):
        import subprocess
        el = effect.lower()

        if "zoom" in el:
            vf = f"zoompan=z='min(zoom+0.0005,1.3)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}"
        elif "slow" in el:
            vf = f"setpts=1.5*PTS,fps={fps}"
        elif "color" in el or "grade" in el:
            vf = "eq=contrast=1.15:saturation=1.2:brightness=0.02"
        else:
            vf = "eq=contrast=1.1:saturation=1.1"

        cmd = [
            "ffmpeg", "-y", "-ss", str(start), "-t", str(dur),
            "-i", src,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", dst
        ]
        subprocess.run(cmd, capture_output=True, timeout=120)
        if os.path.exists(dst):
            log(f"    ENHANCE clip: {os.path.getsize(dst)//1024}KB [{effect[:40]}]")

    # ── REPLACE: Gemini AI image + Ken Burns ───────────────
    def _render_replace_clip(self, dst: str, prompt: str, dur: float,
                             w: int, h: int, fps: float,
                             src: str, start: float, log):
        import subprocess

        # B1: Dùng Gemini tạo prompt chi tiết
        ai_prompt = self._gen_replace_prompt(prompt, log)

        # B2: Lấy frame gốc làm reference
        ref_img = os.path.join(os.path.dirname(dst), f"ref_{int(time.time())}.jpg")
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(start + dur/2), "-i", src,
            "-vframes", "1", "-q:v", "3", ref_img
        ], capture_output=True, timeout=10)

        # B3: Tạo ảnh AI từ Gemini Image Generation
        ai_img = self._generate_ai_image(ai_prompt, ref_img, log)

        # B4: Nếu có ảnh → Ken Burns, nếu không → copy clip gốc
        if ai_img and os.path.exists(ai_img) and os.path.getsize(ai_img) > 500:
            log(f"    REPLACE: tao AI image {os.path.getsize(ai_img)//1024}KB -> Ken Burns")
            vf = f"zoompan=z='min(zoom+0.001,1.2)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}"
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", ai_img,
                "-t", str(dur),
                "-vf", vf,
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", dst
            ]
            subprocess.run(cmd, capture_output=True, timeout=60)
            log(f"    REPLACE clip done: {os.path.getsize(dst)//1024 if os.path.exists(dst) else 0}KB")
        else:
            log(f"    REPLACE: AI image failed, fallback to original clip")
            subprocess.run([
                "ffmpeg", "-y", "-ss", str(start), "-t", str(dur),
                "-i", src,
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart", dst
            ], capture_output=True, timeout=30)

    # ── AI Image Generation ────────────────────────────────
    def _gen_replace_prompt(self, prompt: str, log) -> str:
        """Dùng Gemini tạo prompt chi tiết cho AI image generation."""
        try:
            from translator import get_vertex_client
            from google.genai import types
            client = get_vertex_client()
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[f"Create a detailed AI image generation prompt in English based on: '{prompt}'. "
                          f"Include style, lighting, composition, camera angle. Max 200 chars. Return ONLY the prompt, no explanation."],
                config=types.GenerateContentConfig(temperature=0.7, max_output_tokens=200)
            )
            if resp and resp.text:
                detailed = resp.text.strip()[:300]
                log(f"    AI prompt: {detailed[:80]}...")
                return detailed
        except Exception as e:
            log(f"    Prompt gen error: {str(e)[:50]}")
        return prompt

    def _generate_ai_image(self, prompt: str, ref_img: str, log) -> str:
        """Tạo ảnh từ Gemini 2.5 Flash Image Generation."""
        try:
            from translator import get_vertex_client
            from google.genai import types
            import base64

            client = get_vertex_client()

            # Build parts with reference image + text prompt
            parts = []
            if os.path.exists(ref_img):
                with open(ref_img, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                parts.append(types.Part.from_uri(
                    file_uri=f"data:image/jpeg;base64,{b64}",
                    mime_type="image/jpeg"
                ))

            parts.append(types.Part.from_text(
                f"Generate a high-quality cinematic image based on this description: {prompt}\n"
                f"Style: cinematic, photorealistic, 16:9 aspect ratio, HDR quality."
            ))

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    temperature=0.8,
                    response_modalities=["TEXT", "IMAGE"]
                )
            )

            # Extract image from response
            if response and response.candidates:
                for candidate in response.candidates:
                    for part in candidate.content.parts:
                        if hasattr(part, 'inline_data') and part.inline_data:
                            img_data = part.inline_data.data
                            if img_data:
                                img_path = os.path.join(
                                    os.path.dirname(ref_img),
                                    f"ai_gen_{int(time.time())}.jpg"
                                )
                                with open(img_path, "wb") as f:
                                    f.write(img_data)
                                return img_path

        except Exception as e:
            log(f"    AI image gen error: {str(e)[:80]}")

        return ref_img  # fallback to reference frame

    # ==================================================================
    # HELPERS
    # ==================================================================
    @staticmethod
    def _dummy_srt(video_path: str) -> list:
        import subprocess
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                capture_output=True, text=True, timeout=10
            )
            duration = float(result.stdout.strip())
        except Exception:
            duration = 60.0
        segments = []
        for i in range(0, int(duration), 5):
            segments.append({
                "start": float(i), "end": min(float(i + 5), duration),
                "text": "[No ASR]", "translation": "[Không có ASR]", "speaker": "Speaker A"
            })
        return segments
