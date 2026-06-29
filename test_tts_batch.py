"""Test Gemini TTS batch mode"""
import sys, os, logging
sys.path.insert(0, '.')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

from tts_processor import generate_tts_for_subtitles

subs = [
    {'translation': 'Xin chao cac ban', 'speaker': 'Speaker A', 'start': 0.0, 'end': 3.0},
    {'translation': 'Hom nay toi se huong dan', 'speaker': 'Speaker A', 'start': 3.5, 'end': 6.5},
    {'translation': 'Cam on da theo doi', 'speaker': 'Speaker B', 'start': 7.0, 'end': 9.0},
]

os.makedirs('output/tts_test', exist_ok=True)
result = generate_tts_for_subtitles(subs, 'output/tts_test', provider='gemini')

print()
for i, s in enumerate(result):
    path = s.get('audio_path', 'MISSING')
    dur = s.get('tts_duration', 0)
    print(f'{i}: dur={dur:.1f}s path={path}')
