<img width="741" height="547" alt="image" src="https://github.com/user-attachments/assets/5d535b53-9195-48b9-bbce-5cd8c2138173" />[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/90Mprfp5)
# Network Programming - Final Project [G04]

## Anggota Kelompok
| Nama                 | NRP          | Kelas     |
| -------------------- | ------------ | ----------|
| Farrel Jatmiko Aji   | 5025241234   | C         |
| Justin Valentino     | 5025241193   | C         |
| Aminudin Wijaya      | 5025241242   | C         |

## Link Youtube (Unlisted)
Link ditaruh di bawah ini
```
https://youtu.be/Q5KekyjSu9w
```

## Penjelasan Program

**Tetris Duo** adalah game Tetris multiplayer real-time berbasis jaringan yang dikembangkan dengan bahasa pemrograman **Python**, library **Pygame** untuk rendering UI grafis, dan pustaka **Websockets** untuk komunikasi antar pemain secara real-time. Program ini mendukung dua mode permainan utama:

1. **Solo Player**: Permainan single-player lokal secara offline.
2. **Duo Player (Lokal Jaringan / LAN / Localhost)**: Mode multiplayer 2 pemain menggunakan arsitektur Client-Server berbasis WebSocket. Pemain dapat bertanding di komputer yang sama (melalui IP `127.0.0.1` / localhost dengan membuka dua jendela game) atau antar komputer yang berada dalam satu jaringan lokal (LAN) yang sama.

### 1. Arsitektur Jaringan (Client-Server)
Game ini menggunakan model arsitektur **Client-Server** yang beroperasi secara asinkronus menggunakan koneksi WebSocket:
* **Server (`network/server.py`)**:
  - Berfungsi sebagai mediator lobby permainan. Server membatasi kapasitas maksimal lobby sebanyak 2 pemain.
  - Mengatur siklus permainan (game lifecycle) secara aman, membangkitkan *random seed* sinkron untuk memastikan urutan *tetromino piece* kedua pemain identik (menggunakan algoritma 7-bag generator).
  - Melakukan koordinasi terhadap aksi global seperti jeda permainan (*pause/resume*), penyelesaian pertandingan (*match finished*), dan aksi menyerah (*forfeit*).
  - **Sistem Rekoneksi (Session Recovery)**: Server mengimplementasikan fitur toleransi pemutusan jaringan yang kuat. Saat client terhubung pertama kali, server memberikan token sesi 16-byte unik. Jika client mengalami putus koneksi di tengah permainan, server mem-pause permainan secara otomatis dan memberikan toleransi waktu rekoneksi (*grace period*) selama 15 detik. Client dapat menggunakan kembali token tersebut untuk melanjutkan game dari state terakhir tanpa kehilangan progress.
* **Client (`network/network_client.py`)**:
  - Berkomunikasi dengan server menggunakan koneksi WebSocket binary.
  - Untuk menghindari *UI blocking/freezing* akibat latensi jaringan, client memproses antrean paket data secara asinkron di dalam *background thread* terpisah dan menyediakannya untuk di-*poll* oleh thread utama Pygame pada siklus frame berikutnya.
  - Mengirimkan *snapshot* state game lokal ke server setiap 50 ms (20 Hz) untuk diperbarui dan ditampilkan di sisi lawan secara real-time.

### 2. Protokol Jaringan (Custom Binary Protocol)
Untuk efisiensi bandwidth yang maksimal dan meminimalkan latensi (*packet size optimization*), game ini menggunakan protokol biner kustom yang dirancang menggunakan modul `struct` Python:
* **Struktur Header (18 Byte)**:
  - `MAGIC` (2 byte): Penanda validitas paket (`\xAA\x55`).
  - `VERSION` (1 byte): Versi protokol jaringan.
  - `MESSAGE_TYPE` (1 byte): Tipe pesan (misal: `MSG_HELLO`, `MSG_WELCOME`, `MSG_STATE_UPDATE`, dll.).
  - `FLAGS` (1 byte): Flag bitwise opsional.
  - `PAYLOAD_SIZE` (2 byte): Ukuran payload pesan dalam byte.
  - `SEQ` (4 byte): Sequence number untuk mendeteksi urutan paket.
  - `ACK` (4 byte): Acknowledgment number.
  - `TICK` (4 byte): Timestamp lokal pengiriman paket.
* **State Compression (Snapshot 124 Byte)**:
  Setiap *update state* pemain dikompresi menjadi payload berukuran tetap (124 byte):
  - **Board State (100 byte)**: Grid board berukuran 10x20 dikompresi dengan menyandikan setiap cell (warna block) menggunakan skema 4-bit per cell (setengah byte). Dengan demikian, 200 cell dapat dikirim hanya dalam 100 byte.
  - **Metadata (24 byte)**: Menyimpan informasi status permainan seperti ID Slot, tipe piece aktif, posisi koordinat X/Y, rotasi piece, 3 jenis piece berikutnya, jenis piece yang di-hold, status hold, skor, total baris terhapus, tingkat level, combo, flag back-to-back, indeks piece, status game over, serta berbagai timer internal (fall timer, lock timer, das timer).

### 3. Skema Kontrol (Control Schemes)
Game ini mendukung keyboard kontrol dengan konfigurasi sebagai berikut:

* **Player 1 (Solo / Local Duo / Jaringan)**:
  - Gerak Kiri / Kanan: `A` / `D`
  - Putar Searah Jarum Jam (CW): `W`
  - Putar Berlawanan Jarum Jam (CCW): `Q`
  - Jatuh Perlahan (Soft Drop): `S`
  - Jatuh Instan (Hard Drop): `SPACE`
  - Simpan Balok (Hold): `LEFT SHIFT`
  - Jeda Game (Pause): `ESC` atau `P`
  - Keluar dari Game Online / Menyerah (Forfeit): Tahan tombol `ESC` selama 2 detik saat game terputus atau dijeda.

* **Player 2 (Hanya untuk Lokal Duo)**:
  - Gerak Kiri / Kanan: `LEFT` / `RIGHT`
  - Putar Searah Jarum Jam (CW): `UP`
  - Putar Berlawanan Jarum Jam (CCW): `.` (titik)
  - Jatuh Perlahan (Soft Drop): `DOWN`
  - Jatuh Instan (Hard Drop): `ENTER`
  - Simpan Balok (Hold): `RIGHT SHIFT`

---

### 4. Cara Menjalankan Program secara Lokal

1. Pastikan Anda memiliki **Python 3.10+** terinstall.
2. Install pustaka yang diperlukan:
   ```bash
   pip install -r requirements.txt
   ```
3. **Jalankan Game**:
   ```bash
   python tetris/tetris.py
   ```
   * **Mode Solo**: Pilih **Solo Player** pada menu utama.
   * **Mode Duo (Multiplayer)**:
     - **Pemain 1 (Host)**: Pilih **Duo Player** pada menu utama -> klik tombol **Create** di panel kanan. Client game akan otomatis menjalankan server di latar belakang dan menghubungkan Anda. Bagikan IP Address dan Port yang tertera di layar ke Pemain 2.
     - **Pemain 2 (Join)**: Masukkan IP Address dan Port Pemain 1 pada kolom input sebelah kiri, lalu klik **Join**.

## Screenshot Hasil

<img width="1293" height="469" alt="image" src="https://github.com/user-attachments/assets/bc5a48c0-5272-4493-9364-3a6bc06cf8f7" />

<br>

<img width="1429" height="642" alt="image" src="https://github.com/user-attachments/assets/f6d0a406-f803-467d-ab5f-a725228dd6b4" />

<br>

<img width="741" height="547" alt="image" src="https://github.com/user-attachments/assets/7c1677af-d754-43c4-9331-92bc7229b7da" />

<br>

<img width="1008" height="525" alt="image" src="https://github.com/user-attachments/assets/030aaeb2-f7e2-4a3e-85c0-d007ce7e5cf8" />

