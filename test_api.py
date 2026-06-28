"""
Test API: Dịch thuật (Gist) + TTS Giọng Đọc (edge-tts, Google)
Chạy: python test_api.py
"""
import os
import sys
import json
import asyncio
import requests
import subprocess
from pathlib import Path

# ──────────────────────────────────────────────
# 1. TEST API DỊCH THUẬT TỪ GIST
# https://gist.github.com/qtvhao/135928332c74030211cb3f4c91007876
# ──────────────────────────────────────────────
TRANSLATE_API_URL = "https://http-honyaku-kiban-production-80.schnworks.com/translation/language/translate/v2"

def test_translate_api():
    """Ping thử API dịch thuật batch."""
    print("\n" + "="*60)
    print("[1] TEST API DỊCH THUẬT (Gist Batch Translation)")
    print("="*60)
    
    test_texts = [
        "你好，今天天气真好，我们出去走走吧。",
        "这个产品的质量非常好，我推荐给大家。",
        "请注意安全，遵守交通规则。"
    ]
    
    payload = {
        "texts": test_texts,
        "targetLanguage": "vie"
    }
    
    print(f"URL: {TRANSLATE_API_URL}")
    print(f"Input ({len(test_texts)} texts):")
    for i, t in enumerate(test_texts):
        print(f"  [{i+1}] {t}")
    
    translated = False
    try:
        resp = requests.post(
            TRANSLATE_API_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        print(f"\nStatus: {resp.status_code}")
        print(f"Response: {resp.text[:500]}")
        
        if resp.status_code == 200:
            data = resp.json()
            translations = data.get("translations", [])
            print(f"\n✅ Dịch thành công bằng Gist API ({len(translations)} câu):")
            for i, t in enumerate(translations):
                print(f"  [{i+1}] {t}")
            translated = True
        else:
            print(f"❌ Gist API lỗi HTTP {resp.status_code}")
    except Exception as e:
        print(f"⚠️ Gist API lỗi kết nối (DNS/Network): {str(e)[:150]}")

    if not translated:
        print("\n🌐 Đang tự động thử dịch dự phòng bằng Google Translate Web API...")
        try:
            google_translations = []
            for text in test_texts:
                url = "https://translate.googleapis.com/translate_a/single"
                params = {
                    "client": "gtx",
                    "sl": "zh-CN",
                    "tl": "vi",
                    "dt": "t",
                    "q": text
                }
                r = requests.get(url, params=params, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    translated_parts = [part[0] for part in data[0] if part and part[0]]
                    google_translations.append("".join(translated_parts))
                else:
                    google_translations.append("")
            
            if any(t.strip() for t in google_translations):
                print(f"✅ Dịch dự phòng Google Translate thành công:")
                for i, t in enumerate(google_translations):
                    print(f"  [{i+1}] {t}")
            else:
                print("❌ Dịch dự phòng Google Translate thất bại.")
        except Exception as ge:
            print(f"❌ Lỗi dịch dự phòng Google: {ge}")


# ──────────────────────────────────────────────
# 2. TEST TTS GIỌNG ĐỌC (edge-tts)
# ──────────────────────────────────────────────
def test_edge_tts():
    """Test giọng đọc edge-tts tiếng Việt."""
    print("\n" + "="*60)
    print("[2] TEST TTS - edge-tts (Microsoft Neural)")
    print("="*60)
    
    try:
        import edge_tts
    except ImportError:
        print("❌ edge-tts chưa cài! Cài: pip install edge-tts")
        return
    
    voices = {
        "Nữ miền Nam (Hoài My)": "vi-VN-HoaiMyNeural",
        "Nam miền Nam (Nam Minh)": "vi-VN-NamMinhNeural",
    }
    
    test_sentence = (
        "Xin chào quý khách! Hôm nay chúng tôi xin giới thiệu một sản phẩm mới "
        "với chất lượng vượt trội, giá cả phải chăng và nhiều ưu đãi hấp dẫn."
    )
    
    async def synthesize(voice_name, voice_id, label):
        output_file = f"test_edge_{voice_id.split('-')[-1]}.mp3"
        print(f"\n🎤 [{label}] {voice_id}")
        print(f"   Text: {test_sentence[:80]}...")
        
        try:
            await edge_tts.Communicate(test_sentence, voice_id).save(output_file)
            size = os.path.getsize(output_file)
            
            # Đo duration bằng ffprobe
            try:
                result = subprocess.run([
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    output_file
                ], capture_output=True, text=True, timeout=10)
                duration = float(result.stdout.strip())
            except Exception:
                duration = 0
            
            print(f"   ✅ OK! File: {output_file} ({size/1024:.1f}KB, {duration:.2f}s)")
            print(f"   ▶️  Mở file để nghe thử...")
            os.startfile(output_file)  # Windows: mở file bằng default player
            return duration
        except Exception as e:
            print(f"   ❌ Lỗi: {e}")
            return None
    
    async def run_all():
        tasks = [synthesize(name, vid, name) for name, vid in voices.items()]
        await asyncio.gather(*tasks)
    asyncio.run(run_all())


# ──────────────────────────────────────────────
# 3. TEST TTS GIỌNG ĐỌC (Google Cloud TTS)
# ──────────────────────────────────────────────
def test_google_tts():
    """Test giọng đọc Google Cloud TTS Neural2."""
    print("\n" + "="*60)
    print("[3] TEST TTS - Google Cloud TTS (Neural2)")
    print("="*60)
    
    try:
        from google.cloud import texttospeech
    except ImportError:
        print("❌ google-cloud-texttospeech chưa cài! Cài: pip install google-cloud-texttospeech")
        return
    
    json_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not json_path or not os.path.exists(json_path):
        print("❌ GOOGLE_APPLICATION_CREDENTIALS chưa set hoặc file không tồn tại!")
        print("   Set biến môi trường GOOGLE_APPLICATION_CREDENTIALS=path/to/key.json")
        return
    
    client = texttospeech.TextToSpeechClient()
    
    voices = {
        "Nữ Neural2-A": "vi-VN-Neural2-A",
        "Nữ Neural2-B": "vi-VN-Neural2-B", 
        "Nam Neural2-D": "vi-VN-Neural2-D",
    }
    
    test_sentence = (
        "Chào mừng bạn đến với công nghệ trí tuệ nhân tạo. "
        "Giọng đọc này được tạo ra bởi Google Cloud Text-to-Speech, "
        "sử dụng công nghệ Neural2 tiên tiến nhất hiện nay."
    )
    
    for label, voice_name in voices.items():
        print(f"\n🎤 [{label}] {voice_name}")
        print(f"   Text: {test_sentence[:80]}...")
        
        try:
            synthesis_input = texttospeech.SynthesisInput(text=test_sentence)
            voice = texttospeech.VoiceSelectionParams(
                language_code="vi-VN",
                name=voice_name,
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=1.0,
                pitch=0.0,
            )
            
            response = client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config,
            )
            
            output_file = f"test_google_{voice_name.split('-')[-1]}.mp3"
            with open(output_file, "wb") as f:
                f.write(response.audio_content)
            
            size = os.path.getsize(output_file)
            
            # Đo duration
            try:
                result = subprocess.run([
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    output_file
                ], capture_output=True, text=True, timeout=10)
                duration = float(result.stdout.strip())
            except Exception:
                duration = 0
            
            print(f"   ✅ OK! File: {output_file} ({size/1024:.1f}KB, {duration:.2f}s)")
            print(f"   ▶️  Mở file để nghe thử...")
            os.startfile(output_file)
        except Exception as e:
            print(f"   ❌ Lỗi: {e}")


# ──────────────────────────────────────────────
# 4. TEST GIÃN CHẬM (atempo) - KIỂM TRA CHẤT LƯỢNG
# ──────────────────────────────────────────────
def test_atempo_slowdown():
    """Test hiệu ứng giãn chậm giọng đọc."""
    print("\n" + "="*60)
    print("[4] TEST GIÃN CHẬM (atempo) - So sánh tốc độ đọc")
    print("="*60)
    
    # Tìm file TTS edge mới tạo
    edge_files = [f for f in os.listdir(".") if f.startswith("test_edge_") and f.endswith(".mp3")]
    if not edge_files:
        print("⚠️ Chưa có file edge-tts. Chạy test [2] trước.")
        return
    
    input_file = edge_files[0]
    rates = [0.90, 0.85, 0.80, 0.75]
    
    for rate in rates:
        output_file = f"test_slow_{int(rate*100)}.mp3"
        print(f"\n🐢 Giãn chậm {rate:.0%} (atempo={rate:.2f}): {input_file} → {output_file}")
        
        try:
            if rate < 0.5:
                atempo_filter = f"atempo={rate*2:.4f},atempo=0.5"
            else:
                atempo_filter = f"atempo={rate:.4f}"
                
            subprocess.run([
                "ffmpeg", "-y", "-i", input_file,
                "-filter:a", atempo_filter,
                "-c:a", "libmp3lame", "-q:a", "2",
                output_file
            ], capture_output=True, check=True, timeout=15)
            
            # Đo duration
            try:
                result = subprocess.run([
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    output_file
                ], capture_output=True, text=True, timeout=10)
                duration = float(result.stdout.strip())
            except Exception:
                duration = 0
                
            print(f"   ✅ OK! Duration: {duration:.2f}s")
            print(f"   ▶️  Mở file để nghe...")
            os.startfile(output_file)
        except Exception as e:
            print(f"   ❌ Lỗi: {e}")


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════╗")
    print("║          TEST API - DỊCH THUẬT & GIỌNG ĐỌC          ║")
    print("╚══════════════════════════════════════════════════════╝")
    
    # 1. Test API dịch từ Gist
    test_translate_api()
    
    # 2. Test TTS edge-tts (miễn phí)
    if input("\n👉 Test edge-tts? (y/n): ").lower() == 'y':
        test_edge_tts()
    
    # 3. Test TTS Google Cloud (có phí)
    if input("\n👉 Test Google Cloud TTS? (y/n): ").lower() == 'y':
        test_google_tts()
    
    # 4. Test giãn chậm
    if input("\n👉 Test giãn chậm atempo? (y/n): ").lower() == 'y':
        test_atempo_slowdown()
    
    print("\n✅ Hoàn thành tất cả test!")
