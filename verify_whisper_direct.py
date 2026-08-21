import os
import numpy as np
import av
import time
from faster_whisper import WhisperModel

def transcribe_file(mp3_file):
    if not os.path.exists(mp3_file):
        print(f"MP3 recording not found at {mp3_file}")
        return
        
    print(f"\n--- Transcribing {mp3_file} ---")
    container = av.open(mp3_file)
    stream = container.streams.audio[0]
    resampler = av.AudioResampler(format='flt', layout='mono', rate=16000)

    audio_data = []
    for frame in container.decode(stream):
        resampled = resampler.resample(frame)
        for r_frame in resampled:
            audio_data.append(r_frame.to_ndarray()[0])
            
    audio_np = np.concatenate(audio_data)
    
    model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
    segments, info = model.transcribe(audio_np, beam_size=5)
    segment_list = list(segments)
    
    print(f"Detected language: '{info.language}' with probability {info.language_probability:.4f}")
    for idx, segment in enumerate(segment_list):
        confidence_proxy = float(np.exp(segment.avg_logprob))
        print(f"  Segment {idx+1}: [{segment.start:.1f}s -> {segment.end:.1f}s] '{segment.text.strip()}' | conf={confidence_proxy:.4f} | no_speech={segment.no_speech_prob:.4f}")

def main():
    files = [
        r"MicroSIP-3.22.12\Recordings\20260818-162414-600-outgoing-test1000.mp3",
        r"MicroSIP-3.22.12\Recordings\20260818-162451-600-outgoing-test1000.mp3",
        r"MicroSIP-3.22.12\Recordings\20260818-162632-600-outgoing-test1000.mp3"
    ]
    for f in files:
        transcribe_file(f)

if __name__ == '__main__':
    main()
