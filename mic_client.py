"""
mic_client.py — Device 2 (RPi/Laptop di Smartroom)

Flow:
  1. Connect ke MQTT broker (server)
  2. Subscribe topic: meetily/recording/command
  3. Terima { action: "start", meetingId, title, ... } → mulai rekam
  4. Open WebSocket ws://NEXUS:3500/ws/meetily/stream
     → Kirim raw PCM terus-menerus via callback (non-blocking, latensi ~5 detik)
     → Nexus buffer & kirim ke Whisper tiap 5 detik → SSE ke widget
  5. Terima { action: "stop" } → stop stream, kirim WS stop message
     → Upload full WAV ke Meetily sebagai arsip

Install deps:
  pip install sounddevice numpy paho-mqtt requests websocket-client
"""

import json
import wave
import tempfile
import os
import threading
import time
import requests
import numpy as np
import sounddevice as sd
import paho.mqtt.client as mqtt
import websocket  # pip install websocket-client

# ─── CONFIG ──────────────────────────────────────────────────────────────────
MQTT_BROKER   = "localhost"       # IP server (ganti sesuai IP server)
MQTT_PORT     = 1883
MQTT_TOPIC    = "meetily/recording/command"

SERVER_IP     = "10.8.1.84"
SERVER_IPP    = "10.8.1.84"
NEXUS_URL     = f"http://{SERVER_IPP}:3500"   # Nexus Web App
NEXUS_WS_URL  = f"ws://{SERVER_IPP}:3500/ws/meetily/stream"  # WebSocket endpoint
MEETILY_URL   = f"http://{SERVER_IP}:8178"   # Meetily Whisper — simpan full recording

SAMPLE_RATE   = 16000
CHANNELS      = 1
DTYPE         = "int16"
BLOCKSIZE     = 4096              # ~256ms per callback
DEVICE        = "pulse"               # Ganti ke device mic kamu jika perlu

# ─── STATE ───────────────────────────────────────────────────────────────────
is_recording  = False
stop_event    = threading.Event()
current_meeting: dict = {}

# ─── RECORDING ───────────────────────────────────────────────────────────────

def record_and_stream():
    """Stream audio via WebSocket ke Nexus — non-blocking, latensi ~5 detik."""
    global is_recording

    meeting_id = current_meeting.get("meetingId", "unknown")
    title      = current_meeting.get("title", "Meeting")
    print(f"[MIC] Mulai stream: {title} (meetingId={meeting_id})")

    all_audio = []
    ws = None

    try:
        # ── Buka WebSocket ke Nexus ──────────────────────────────────────────
        ws = websocket.WebSocket()
        ws.connect(NEXUS_WS_URL)
        print(f"[MIC] WebSocket connected: {NEXUS_WS_URL}")

        # Kirim start message
        ws.send(json.dumps({
            "type":      "start",
            "meetingId": meeting_id,
            "title":     title,
        }))

        # ── Audio callback (berjalan di thread sounddevice) ──────────────────
        def audio_callback(indata, frames, time_info, status):
            if status:
                print(f"[MIC] Audio status: {status}")
            all_audio.append(indata.copy())
            try:
                if ws.connected:
                    ws.send_binary(indata.tobytes())
            except Exception as e:
                print(f"[MIC] WS send error: {e}")

        # ── Buka InputStream — non-blocking, jalan sampai stop_event ────────
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            device=DEVICE,
            blocksize=BLOCKSIZE,
            callback=audio_callback,
        ):
            print("[MIC] InputStream aktif, menunggu stop signal...")
            stop_event.wait()  # Block sampai MQTT stop diterima

        print("[MIC] InputStream berhenti.")

        # ── Kirim stop message ke Nexus via WS ──────────────────────────────
        try:
            if ws.connected:
                ws.send(json.dumps({
                    "type":      "stop",
                    "meetingId": meeting_id,
                }))
                print(f"[MIC] Stop message terkirim (meetingId={meeting_id})")
        except Exception as e:
            print(f"[MIC] WS stop send error: {e}")

    except Exception as e:
        print(f"[MIC] Error saat streaming: {e}")

    finally:
        # Tutup WebSocket
        if ws:
            try:
                ws.close()
            except Exception:
                pass

    # ── Upload full WAV ke Meetily sebagai arsip ─────────────────────────────
    if all_audio:
        full_audio = np.concatenate(all_audio, axis=0)
        save_and_upload_recording(full_audio)

    is_recording = False
    print("[MIC] Recording selesai.")


def save_and_upload_recording(audio: np.ndarray):
    """Simpan full recording dan upload ke Meetily untuk arsip."""
    meeting_id = current_meeting.get("meetingId", "unknown")
    filename   = f"recording_{meeting_id}.wav"

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False, prefix=f"meeting_{meeting_id}_") as f:
        tmp_path = f.name

    try:
        write_wav(tmp_path, audio)
        print(f"[MIC] Menyimpan recording ({len(audio)/SAMPLE_RATE:.1f}s) → {tmp_path}")

        with open(tmp_path, "rb") as f:
            resp = requests.post(
                f"{MEETILY_URL}/upload",
                files={"file": (filename, f, "audio/wav")},
                data={"meetingId": meeting_id},
                timeout=120,
            )
        if resp.ok:
            print(f"[MIC] Upload berhasil: {resp.json()}")
        else:
            print(f"[MIC] Upload gagal {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[MIC] Upload error: {e}")
        print(f"[MIC] File tersimpan lokal di: {tmp_path}")
    # Jangan hapus tmp_path — biar ada backup lokal


def write_wav(path: str, audio: np.ndarray):
    with wave.open(path, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # int16 = 2 bytes
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())


# ─── MQTT HANDLERS ───────────────────────────────────────────────────────────

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[MQTT] Connected ke broker {MQTT_BROKER}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC)
        print(f"[MQTT] Subscribe: {MQTT_TOPIC}")
    else:
        print(f"[MQTT] Connect gagal, rc={rc}")


def on_message(client, userdata, msg):
    global is_recording, current_meeting

    try:
        payload = json.loads(msg.payload.decode())
        action  = payload.get("action")

        print(f"[MQTT] Terima: action={action}, meeting={payload.get('title')}")

        if action == "start" and not is_recording:
            current_meeting = payload
            is_recording    = True
            stop_event.clear()
            thread = threading.Thread(target=record_and_stream, daemon=True)
            thread.start()

        elif action == "stop" and is_recording:
            print("[MQTT] Stop signal diterima")
            stop_event.set()

        else:
            print(f"[MQTT] Ignored: action={action}, is_recording={is_recording}")

    except Exception as e:
        print(f"[MQTT] Error parsing message: {e}")


def on_disconnect(client, userdata, rc):
    if rc != 0:
        print(f"[MQTT] Disconnected (rc={rc}), reconnecting...")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  Meetily Mic Client (WebSocket streaming mode)")
    print(f"  MQTT Broker : {MQTT_BROKER}:{MQTT_PORT}")
    print(f"  Topic       : {MQTT_TOPIC}")
    print(f"  Nexus WS    : {NEXUS_WS_URL}")
    print(f"  Meetily URL : {MEETILY_URL}")
    print("=" * 55)
    print("Menunggu sinyal dari server...\n")

    mqttc = mqtt.Client(client_id=f"mic-client-{int(time.time())}")
    mqttc.on_connect    = on_connect
    mqttc.on_message    = on_message
    mqttc.on_disconnect = on_disconnect

    mqttc.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)

    try:
        mqttc.loop_forever()
    except KeyboardInterrupt:
        print("\n[MIC] Stop.")
        stop_event.set()
        mqttc.disconnect()
