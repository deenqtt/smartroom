# Zigbee2MQTT Setup on Raspberry Pi
## Menggunakan Sonoff Zigbee 3.0 USB Dongle Plus V2 (CC2652P)

---

## Prasyarat

- Raspberry Pi (OS berbasis Debian/Ubuntu)
- Docker & Docker Compose sudah terinstall
- MQTT Broker (Mosquitto) sudah berjalan
- Sonoff Zigbee 3.0 USB Dongle Plus V2

---

## Step 1 — Cek Dongle Terdeteksi

Colok dongle ke USB, lalu cek:

```bash
ls -l /dev/serial/by-id/
```

Contoh output yang benar:
```
lrwxrwxrwx 1 root root 13 Apr 14 16:22 usb-Itead_Sonoff_Zigbee_3.0_USB_Dongle_Plus_V2_...-if00-port0 -> ../../ttyUSB0
```

Pastikan dongle terbaca sebagai `/dev/ttyUSB0`.

---

## Step 2 — Nonaktifkan Service yang Mengganggu

Service seperti `brltty` atau `ModemManager` bisa merebut port serial sebelum Zigbee2MQTT.

```bash
sudo systemctl stop brltty
sudo systemctl disable brltty

sudo systemctl stop ModemManager
sudo systemctl disable ModemManager
```

Setelah itu, **unplug lalu colok ulang** dongle.

---

## Step 3 — Tambah User ke Group dialout

```bash
sudo usermod -aG dialout $USER
```

> Logout dan login ulang agar grup aktif.

---

## Step 4 — Buat Direktori Data

```bash
sudo mkdir -p /opt/zigbee2mqtt/data
```

---

## Step 5 — Buat File Konfigurasi

```bash
sudo nano /opt/zigbee2mqtt/data/configuration.yaml
```

Isi dengan konfigurasi berikut:

```yaml
homeassistant:
  enabled: false

mqtt:
  base_topic: zigbee2mqtt
  server: mqtt://localhost:1883   # sesuaikan dengan IP/port MQTT broker

serial:
  port: /dev/ttyUSB0              # WAJIB pakai ttyUSB0, bukan symlink by-id
  adapter: zstack                 # wajib untuk Sonoff V2 (CC2652P)

frontend:
  enabled: true
  port: 8080
  host: 0.0.0.0

advanced:
  log_level: info
  channel: 25
```

> **Penting:** Gunakan `/dev/ttyUSB0` bukan path `/dev/serial/by-id/...`.
> Path symlink tidak bisa di-pass langsung ke dalam Docker container.

Simpan dengan `Ctrl+X` → `Y` → `Enter`.

---

## Step 6 — Jalankan Container Zigbee2MQTT

```bash
docker run -d \
  --name zigbee2mqtt \
  --restart=unless-stopped \
  --device=/dev/ttyUSB0:/dev/ttyUSB0 \
  --group-add dialout \
  --network host \
  -v /opt/zigbee2mqtt/data:/app/data \
  -e TZ=Asia/Jakarta \
  koenkk/zigbee2mqtt:latest
```

> Jangan mapping `/dev/serial/by-id/...` sebagai device — itu symlink dan tidak bekerja di dalam container.

---

## Step 7 — Cek Log

```bash
docker logs -f zigbee2mqtt
```

Output sukses yang diharapkan:

```
info: z2m: Starting Zigbee2MQTT version x.x.x
info: z2m: Starting zigbee-herdsman
info: z2m: zigbee-herdsman started
info: z2m: Coordinator firmware version: {"type":"znp","meta":{"revision":...}}
info: z2m: Currently 0 devices are joined
info: z2m: Zigbee2MQTT started!
```

---

## Step 8 — Akses Frontend

Buka browser dan akses:

```
http://<IP-RaspberryPi>:8080
```

---

## Troubleshooting

### Error: `SRSP - SYS - ping after 6000ms`

Penyebab paling umum:

| Penyebab | Solusi |
|---|---|
| Serial port salah di config | Ganti ke `/dev/ttyUSB0` |
| Symlink by-id dipakai di Docker | Hapus dari `--device`, pakai `ttyUSB0` |
| `brltty` / `ModemManager` merebut port | Disable kedua service (Step 2) |
| Adapter type tidak di-set | Tambah `adapter: zstack` di config |
| Permission serial port | Tambah user ke group `dialout` (Step 3) |

---

### Cek Proses yang Menempati Port

```bash
sudo lsof /dev/ttyUSB0
# atau
sudo fuser /dev/ttyUSB0
```

Kalau ada proses lain, kill terlebih dahulu.

---

### Install Ulang Bersih (Clean Install)

```bash
# Hentikan dan hapus container
docker stop zigbee2mqtt
docker rm zigbee2mqtt

# Hapus image
docker rmi koenkk/zigbee2mqtt:latest

# Backup data lama (opsional)
sudo cp -r /opt/zigbee2mqtt/data /opt/zigbee2mqtt/data.bak

# Hapus data lama
sudo rm -rf /opt/zigbee2mqtt/data
sudo mkdir -p /opt/zigbee2mqtt/data

# Ulangi dari Step 5
```

---

## Referensi

- [Zigbee2MQTT Official Docs](https://www.zigbee2mqtt.io)
- [Troubleshooting fails to start](https://www.zigbee2mqtt.io/guide/installation/20_zigbee2mqtt-fails-to-start_crashes-runtime.html)
- [Supported Adapters](https://www.zigbee2mqtt.io/guide/adapters/)
