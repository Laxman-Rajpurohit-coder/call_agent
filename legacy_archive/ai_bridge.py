import socket
import struct
import sys
import os
import subprocess
import time
import re
import numpy as np
from faster_whisper import WhisperModel
from llama_cpp import Llama

# Configure Paths
MODELS_DIR = r"c:\daily_works\superfone_call\models"
PIPER_EXE = r"c:\daily_works\superfone_call\piper\piper\piper.exe"
PIPER_MODEL = os.path.join(MODELS_DIR, "en_US-lessac-medium.onnx")
LLM_MODEL = os.path.join(MODELS_DIR, "qwen2.5-1.5b-instruct-q4_k_m.gguf")

# Load AI Models
print("Loading Whisper Speech-to-Text model (tiny.en)...")
stt_model = WhisperModel("tiny.en", device="cpu", compute_type="int8")

print("Loading LLM model (Qwen 2.5 1.5B)...")
llm = Llama(model_path=LLM_MODEL, n_ctx=2048, verbose=False)

print("AI Pipeline loaded successfully!")

def resample_8k_to_16k(audio_bytes):
    """Resample 8000Hz 16-bit PCM to 16000Hz float32 for Whisper"""
    samples = np.frombuffer(audio_bytes, dtype=np.int16)
    if len(samples) == 0:
        return np.array([], dtype=np.float32)
    # Duplicate samples to double frequency
    resampled = np.repeat(samples, 2)
    return resampled.astype(np.float32) / 32768.0

def resample_22k_to_8k(audio_bytes):
    """Resample 22050Hz 16-bit PCM (Piper output) to 8000Hz PCM (Asterisk input)"""
    samples = np.frombuffer(audio_bytes, dtype=np.int16)
    if len(samples) == 0:
        return b''
    # Map 22050Hz indices to 8000Hz
    num_samples = int(len(samples) * 8000 / 22050)
    if num_samples == 0:
        return b''
    indices = np.linspace(0, len(samples) - 1, num_samples).astype(np.int32)
    resampled = samples[indices]
    return resampled.tobytes()

def run_tts(text):
    """Run Piper TTS and return raw 22050Hz PCM bytes"""
    try:
        proc = subprocess.Popen(
            [PIPER_EXE, "--model", PIPER_MODEL, "--output_raw"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        stdout, _ = proc.communicate(input=text.encode('utf-8'))
        return stdout
    except Exception as e:
        print(f"TTS Error: {e}")
        return b''

def get_audio_energy(audio_bytes):
    """Calculate RMS energy of 16-bit PCM audio frame"""
    samples = np.frombuffer(audio_bytes, dtype=np.int16)
    if len(samples) == 0:
        return 0
    return np.sqrt(np.mean(samples.astype(np.float64)**2))

def handle_call(client_socket):
    # Conversations history
    conversation_history = [
        {"role": "system", "content": "You are a helpful, extremely concise voice assistant. Speak naturally. Keep replies under 2 sentences since you are talking over a phone call."}
    ]
    
    print("New call started.")
    
    # Send a welcoming TTS greeting immediately
    greeting = "Hello! I am your voice assistant. How can I help you today?"
    print(f"AI: {greeting}")
    tts_audio = run_tts(greeting)
    asterisk_audio = resample_22k_to_8k(tts_audio)
    
    # Send welcome audio in 320-byte (20ms) chunks to Asterisk
    chunk_size = 320
    for i in range(0, len(asterisk_audio), chunk_size):
        chunk = asterisk_audio[i:i+chunk_size]
        if len(chunk) < chunk_size:
            chunk = chunk + b'\x00' * (chunk_size - len(chunk))
        header = struct.pack('!BH', 0x10, len(chunk))
        client_socket.sendall(header + chunk)
        time.sleep(0.02) # Pace it at 20ms
        
    print("Welcome greeting sent. Listening...")

    audio_buffer = b''
    speaking = False
    silence_start = None
    
    # Silence detection parameters
    SILENCE_THRESHOLD = 500  # RMS energy below this is silence
    SILENCE_DURATION = 1.0   # seconds of silence to trigger STT
    MIN_SPEECH_DURATION = 0.4 # ignore noises shorter than 400ms

    speech_start_time = None
    
    while True:
        # Read 3-byte header
        header = client_socket.recv(3)
        if not header or len(header) < 3:
            break
        
        payload_type, payload_len = struct.unpack('!BH', header)
        
        # Read payload
        payload = b''
        while len(payload) < payload_len:
            chunk = client_socket.recv(payload_len - len(payload))
            if not chunk:
                break
            payload += chunk
            
        if len(payload) < payload_len:
            break
            
        if payload_type == 0x00:
            # Hangup
            print("Received hangup command.")
            break
            
        elif payload_type == 0x10:
            # Audio frame
            energy = get_audio_energy(payload)
            
            if energy > SILENCE_THRESHOLD:
                # User is speaking
                if not speaking:
                    speaking = True
                    speech_start_time = time.time()
                    print("[Speech Detected]")
                audio_buffer += payload
                silence_start = None
            else:
                # Silence
                if speaking:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start >= SILENCE_DURATION:
                        # Silence duration reached! Process speech.
                        speaking = False
                        speech_duration = silence_start - speech_start_time
                        
                        if speech_duration >= MIN_SPEECH_DURATION:
                            print(f"[Processing {speech_duration:.1f}s of speech...]")
                            
                            # Convert 8k mono PCM to 16k float32
                            audio_float32 = resample_8k_to_16k(audio_buffer)
                            audio_buffer = b'' # Clear buffer
                            
                            # STT Transcription
                            segments, _ = stt_model.transcribe(audio_float32, beam_size=5)
                            user_text = "".join(segment.text for segment in segments).strip()
                            
                            if user_text:
                                print(f"User: {user_text}")
                                conversation_history.append({"role": "user", "content": user_text})
                                
                                # Generate LLM response
                                print("AI thinking...")
                                response = llm.create_chat_completion(
                                    messages=conversation_history,
                                    max_tokens=150
                                )
                                ai_text = response['choices'][0]['message']['content'].strip()
                                print(f"AI: {ai_text}")
                                conversation_history.append({"role": "assistant", "content": ai_text})
                                
                                # Piper TTS
                                tts_audio = run_tts(ai_text)
                                asterisk_audio = resample_22k_to_8k(tts_audio)
                                
                                # Send back to Asterisk
                                for i in range(0, len(asterisk_audio), chunk_size):
                                    chunk = asterisk_audio[i:i+chunk_size]
                                    if len(chunk) < chunk_size:
                                        chunk = chunk + b'\x00' * (chunk_size - len(chunk))
                                    response_header = struct.pack('!BH', 0x10, len(chunk))
                                    client_socket.sendall(response_header + chunk)
                                    time.sleep(0.02)
                                    
                            else:
                                print("[No speech transcribed]")
                        else:
                            print("[Ignored brief noise]")
                            audio_buffer = b''
                        
                        silence_start = None

def run_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('0.0.0.0', 9092))
    server_socket.listen(5)
    print("AudioSocket AI Agent listening on port 9092...")
    
    try:
        while True:
            client_socket, client_address = server_socket.accept()
            print(f"Call connection accepted from {client_address}")
            try:
                handle_call(client_socket)
            except Exception as e:
                print(f"Error during call: {e}")
            finally:
                client_socket.close()
                print("Call finished and connection closed.")
    except KeyboardInterrupt:
        print("\nStopping Server.")
    finally:
        server_socket.close()

if __name__ == '__main__':
    run_server()
