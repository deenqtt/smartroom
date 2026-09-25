# SmartRoom - Home Assistant + Zigbee2MQTT Setup

## Arsitektur

```
[Zigbee Device]
      |
  (Zigbee RF)
      |
[RPi 2 - 192.168.0.171]
Zigbee Coordinator + Zigbee2MQTT (Docker)
      |
  (MQTT - port 1883)
      |
[RPi 1 - 192.168.0.121]
Mosquitto Broker + Home Assistant (Docker)
      +
  HACS + LocalTuya
      |
  (Tuya Local / Cloud API)
      |
[Tuya WiFi Devices]
```

---

## Prasyarat

- Docker & Docker Compose sudah terinstall di kedua RPi
- RPi 1 dan RPi 2 terhubung satu jaringan LAN
- Akun Smart Life / Tuya app di HP
- Akun Tuya IoT Platform (`https://iot.tuya.com`)

---

## RPi 1 — Home Assistant Setup

### Spesifikasi

- **IP**: `192.168.0.121`
- **Services**: Home Assistant + Mosquitto MQTT Broker (Docker)

### 1. Install Docker (jika belum ada)

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

Cek versi:

```bash
docker --version
docker compose version
```

### 2. Sync Waktu System

Pastikan jam RPi sudah benar sebelum pull image Docker (penting, kalau salah akan gagal pull):

```bash
sudo timedatectl set-ntp true
timedatectl
```

Pastikan `System clock synchronized: yes`. Jika belum sync, set manual:

```bash
sudo date -s "YYYY-MM-DD HH:MM:SS"
```

### 3. Pull Image Home Assistant

```bash
docker pull ghcr.io/home-assistant/home-assistant:stable
```

### 4. Buat Struktur Folder

```bash
mkdir ~/smartroom && cd ~/smartroom
mkdir -p mosquitto/config
```

### 5. Buat Config Mosquitto

```bash
nano mosquitto/config/mosquitto.conf
```

Isi:

```
listener 1883 0.0.0.0
allow_anonymous true
```

### 6. Buat docker-compose.yml

```bash
nano docker-compose.yml
```

Isi:

```yaml
services:
  homeassistant:
    container_name: homeassistant
    image: ghcr.io/home-assistant/home-assistant:stable
    volumes:
      - ./ha-config:/config
      - /etc/localtime:/etc/localtime:ro
    restart: unless-stopped
    privileged: true
    network_mode: host
```

> **Catatan:** Jika Mosquitto sudah berjalan di container lain (cek dengan `docker ps | grep mosquitto`), hapus service `mosquitto` dari compose file agar tidak konflik port 1883.

### 7. Jalankan Container

```bash
docker compose up -d
```

Cek status:

```bash
docker ps
```

Harusnya ada 2 container running: `homeassistant` dan `mosquitto`.

Akses Home Assistant: `http://192.168.0.121:8123`

### 8. Setup Awal Home Assistant

1. Buka `http://192.168.0.121:8123`
2. Buat akun admin (nama, username, password)
3. Isi detail rumah → **Finish**

---

## RPi 1 — MQTT Integration di Home Assistant

1. **Settings** → **Devices & Services** → **+ Add Integration**
2. Search **MQTT** → pilih **MQTT**
3. Isi:
   - Broker: `localhost`
   - Port: `1883`
   - Username: (kosong)
   - Password: (kosong)
4. **Submit**

---

## RPi 2 — Konfigurasi Zigbee2MQTT

### Spesifikasi

- **IP**: `192.168.0.171`
- **Services**: Zigbee2MQTT (Docker, sudah running)
- **Zigbee Adapter**: `/dev/ttyAMA1` (zboss)

### 1. Cari Lokasi Config

```bash
docker inspect zigbee2mqtt | grep -A5 Mounts
```

Path config: `/opt/stacks/zigbee2mqtt/zigbee2mqtt-data/`

### 2. Edit configuration.yaml

```bash
sudo nano /opt/stacks/zigbee2mqtt/zigbee2mqtt-data/configuration.yaml
```

Ubah `mqtt.server` dari lokal ke IP RPi 1:

```yaml
mqtt:
  base_topic: zigbee2mqtt
  server: mqtt://192.168.0.121:1883 # arahkan ke RPi 1

homeassistant:
  enabled: true # aktifkan auto discovery ke HA
```

### 3. Restart Zigbee2MQTT

```bash
docker restart zigbee2mqtt
```

Cek log:

```bash
docker logs zigbee2mqtt --tail 20
```

Pastikan ada log `MQTT publish` ke topic `homeassistant/...` — artinya sudah konek ke HA.

---

## RPi 1 — Tuya Integration (Official)

Untuk device WiFi berbasis Tuya. Konek via cloud Tuya.

### 1. Setup Tuya IoT Platform

1. Login ke `https://iot.tuya.com`
2. **Cloud** → **Development** → **Create Cloud Project**
   - Project Name: bebas (misal `SmartRoom`)
   - Industry: `Smart Home`
   - Development Method: `Smart Home`
   - Data Center: sesuai region akun app (lihat catatan di bawah)
3. Klik **Create** → **Authorize**

> **Catatan Data Center untuk Indonesia:**
>
> - Akun Smart Life dibuat **setelah 3 Juni 2025** → pilih **Singapore**
> - Akun Smart Life dibuat **sebelum 3 Juni 2025** → pilih **Central Europe**
> - Referensi: https://developer.tuya.com/en/docs/iot/oem-app-data-center-distributed?id=Kafi0ku9l07qb

### 2. Link Akun App ke IoT Platform

1. Di project → tab **Devices** → **Link Tuya App Account**
2. Klik **Add App Account** → muncul QR Code
3. Buka **Smart Life app** di HP → scan QR Code → Confirm

> Jika error "Data centers inconsistency" → ganti region di pojok kanan atas IoT Platform sampai cocok dengan akun app.

### 3. Ambil User Code

Di **Smart Life app**:

1. **Me** → **Settings** → **Account and Security** → **User Code**
2. Copy kodenya

### 4. Install Tuya Integration di HA

1. **Settings** → **Devices & Services** → **+ Add Integration**
2. Search **Tuya** → pilih **Tuya**
3. Masukkan **User Code** → **Submit**

---

## RPi 1 — LocalTuya Integration (via HACS)

Untuk kontrol device Tuya secara **lokal tanpa cloud** — lebih cepat dan tidak tergantung internet.

### 1. Install HACS

Masuk ke container HA di RPi 1:

```bash
docker exec -it homeassistant bash
```

Download dan jalankan installer HACS:

```bash
wget -O - https://get.hacs.xyz | bash -
```

Keluar dari container lalu restart HA:

```bash
exit
docker restart homeassistant
```

### 2. Aktifkan HACS di HA

1. **Settings** → **Devices & Services** → **+ Add Integration**
2. Search **HACS** → ikuti wizard setup
3. Login dengan akun **GitHub** saat diminta

### 3. Install LocalTuya via HACS

1. Klik **HACS** di sidebar kiri
2. Search **LocalTuya** → klik → **Download**
3. Setelah selesai, restart HA: **Settings** → **System** → **Restart**

### 4. Konfigurasi Cloud API LocalTuya

1. **Settings** → **Devices & Services** → **+ Add Integration**
2. Search **LocalTuya** → pilih **LocalTuya**
3. Isi form **Cloud API**:
   - **API server region**: pilih sesuai data center (EU / US / IN / Singapore jika tersedia)
   - **Client ID**: IoT Platform → project → Overview → **Access ID**
   - **Secret**: IoT Platform → project → Overview → **Access Secret**
   - **User ID**: IoT Platform → project → tab **Link Tuya App Account** → klik akun → lihat **User ID**
   - **Username**: email/username akun Smart Life

> Jika error `cross-region access`: ganti region sampai cocok dengan data center project IoT Platform.

### 5. Tambah Device

1. Klik **Add Device** di LocalTuya
2. Pilih device dari list (auto-detect jika Cloud API berhasil)
3. Isi detail:
   - **Host**: IP device di jaringan lokal
   - **Device ID**: dari IoT Platform → Devices
   - **Local Key**: dari IoT Platform → Devices
   - **Protocol Version**: coba `3.3` (paling umum)

---

## Catatan Penting

### Zigbee vs Tuya WiFi

|               | Zigbee Device (misal Arbit Switch) | Tuya WiFi Device                     |
| ------------- | ---------------------------------- | ------------------------------------ |
| **Protokol**  | Zigbee                             | WiFi                                 |
| **Konek via** | Zigbee2MQTT → HA                   | Tuya Cloud/Local → HA                |
| **Tuya App**  | Butuh Tuya Zigbee Gateway          | Langsung bisa                        |
| **Internet**  | Tidak perlu                        | Perlu (Official) / Tidak (LocalTuya) |

Device berlabel **"Tuya Compatible"** yang berprotokol Zigbee tetap konek via Zigbee2MQTT, **bukan** via Tuya app langsung.

### Official Tuya vs LocalTuya

|                 | Official Tuya             | LocalTuya                     |
| --------------- | ------------------------- | ----------------------------- |
| **Koneksi**     | Via cloud Tuya            | Langsung ke device (LAN)      |
| **Internet**    | Wajib                     | Tidak perlu                   |
| **Kecepatan**   | Lambat (cloud round-trip) | Cepat                         |
| **Reliability** | Tergantung server Tuya    | Stabil                        |
| **Setup**       | Mudah                     | Lebih ribet (butuh local key) |

Untuk production SmartRoom → **LocalTuya lebih recommended**.

### Menambah Device Tuya WiFi Baru

1. Buka Smart Life app → **+** → pair device
2. Setelah terpair di app → otomatis muncul di HA
3. Jika tidak muncul: **Settings** → **Devices & Services** → **Tuya** → **Reload**

### Menambah Device Zigbee Baru

1. Buka Zigbee2MQTT frontend: `http://192.168.0.171:8080`
2. Klik **Permit Join** → put device ke pairing mode
3. Device otomatis muncul di HA via MQTT discovery

### Troubleshooting

| Error                                       | Solusi                                                        |
| ------------------------------------------- | ------------------------------------------------------------- |
| Docker pull gagal (certificate expired)     | Sync waktu: `sudo timedatectl set-ntp true`                   |
| Port 1883 already allocated                 | Mosquitto sudah running, hapus service mosquitto dari compose |
| Data centers inconsistency (Tuya)           | Ganti region di pojok kanan atas IoT Platform                 |
| Cross-region access not allowed (LocalTuya) | Ganti API server region di form LocalTuya                     |
| Device Zigbee tidak muncul di HA            | Cek log Z2M: `docker logs zigbee2mqtt --tail 20`              |
# smartroom
