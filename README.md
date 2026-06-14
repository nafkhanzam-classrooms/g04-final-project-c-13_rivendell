[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/90Mprfp5)
# Network Programming - Final Project [G04]

## Anggota Kelompok
| Nama                 | NRP          | Kelas     |
| -------------------- | ------------ | ----------|
| Justin Valentino   | 5025241234   | C         |
| Farrel Jatmiko Aji     | 5025241193   | C         |
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

Program ini telah memenuhi dan mengimplementasikan seluruh fitur wajib proyek pemrograman jaringan sebagai berikut:

#### A. Real-time Update
Client melakukan pengiriman snapshot status lokal secara berkala setiap 50 ms (20 Hz) ke server. Penerimaan data dilakukan secara asinkron dalam background thread agar main thread Pygame tetap berjalan lancar pada 60 FPS.

*   **Background Threading (Client)**:
    ```python
    # tetris/network/network_client.py
    self.thread = threading.Thread(target=self._run, name="tetris-websocket", daemon=True)
    self.thread.start()
    ```
*   **Tick-Rate Update Sending (Client)**:
    ```python
    # tetris/game.py
    if self.network_mode:
        self.network_snapshot_timer += dt
        if self.network_snapshot_timer >= 0.05: # 20 Hz
            self.network_snapshot_timer = 0
            self.send_local_snapshot()
    ```

---

#### B. Game State Synchronization
Sinkronisasi seed permainan acak yang adil dikirimkan oleh server saat inisialisasi game agar urutan tetromino (7-bag randomizer) kedua pemain sinkron dan identik. Update board dan skor pemain dikirimkan dan di-render berdampingan secara real-time.

*   **Synchronized Seed Initialization (Client)**:
    ```python
    # tetris/game.py
    self.shared_sequence = PieceSequence(seed)
    self.p1 = PlayerUI("You", BOARD_1_X, BOARD_Y, self.p1_keys)
    self.p2 = PlayerUI("Opponent", BOARD_2_X, BOARD_Y, {})
    self.p1.state.init_pieces(self.shared_sequence, index_offset=0)
    self.p2.state.init_pieces(self.shared_sequence, index_offset=0)
    ```
*   **Binary Snapshot Packing (Client)**:
    ```python
    # tetris/network/protocol.py
    metadata = SNAPSHOT_META_STRUCT.pack(
        slot, PIECE_TO_CODE[current.type], current.x, current.y, current.rotation,
        *next_codes, held_code, int(player.can_hold), max(0, player.score), ...
    )
    return metadata + pack_board(player.board.grid)
    ```

---

#### C. Reconnect Handling (Session Recovery)
Jika salah satu pemain terputus dari jaringan, server menangguhkan pertandingan secara otomatis (*pause*) dan memberikan batas toleransi (*grace period*) selama 15 detik bagi client untuk melakukan rekoneksi menggunakan token sesi 16-byte unik tanpa merusak state pertandingan saat ini.

*   **Grace Period Timer Registration (Server)**:
    ```python
    # tetris/network/server.py
    timer = threading.Timer(
        RECONNECT_GRACE_SECONDS,
        self.expire_disconnected_session,
        args=(session.slot, session.token, generation),
    )
    timer.daemon = True
    timer.start()
    ```
*   **Session Resumption Handler (Server)**:
    ```python
    # tetris/network/server.py
    session = self._resume_session(reconnect_token, connection)
    if session is None:
        session = self._claim_disconnected_session(reconnect_token, connection)
    ```

---

#### D. Ping/Latency Indicator
Mengukur nilai latensi bolak-balik (RTT) menggunakan frame ping-pong bawaan WebSocket. Latensi dihitung dalam milidetik dan langsung di-render pada UI utama permainan.

*   **Client RTT Monitoring**:
    ```python
    # tetris/network/network_client.py
    now = time.monotonic()
    if now >= next_latency_update:
        latency = connection.latency
        if latency > 0:
            self.incoming.put(("latency", latency * 1000.0)) # Convert to ms
        next_latency_update = now + 0.5
    ```

---

#### E. Logging Aktivitas Player
Server mencatat setiap kejadian dan aktivitas kritis yang dilakukan pemain ke dalam *standard output* (stdout) konsol server demi kebutuhan audit log.

*   **Console Event Logging (Server)**:
    ```python
    # tetris/network/server.py
    print(f"[server] match started with seed {seed}", flush=True)
    print(f"[server] player {session.slot} reconnected", flush=True)
    print(f"[server] player {session.slot} topped out; player {winner} wins", flush=True)
    print(f"[server] player {session.slot} forfeited; player {winner} wins", flush=True)
    ```

---

#### F. Anti-Invalid Packet Sederhana
Server dan client memvalidasi struktur header data biner yang masuk dan secara ketat menolak paket yang rusak. Di sisi lain, server melakukan proteksi anti-cheat dengan memastikan nilai game-state seperti skor dan baris terhapus bersifat monoton naik (tidak boleh berkurang).

*   **Binary Header Validation (Protocol)**:
    ```python
    # tetris/network/protocol.py
    if magic != MAGIC:
        raise ProtocolError("invalid packet magic")
    if version != PROTOCOL_VERSION:
        raise ProtocolError(f"unsupported protocol version: {version}")
    if len(data) != HEADER_SIZE + size:
        raise ProtocolError("packet length doesn't match payload size")
    ```
*   **Monotonic State Verification (Anti-Cheat Server)**:
    ```python
    # tetris/network/server.py
    if snapshot["score"] < previous["score"]:
        raise ProtocolError("score cannot decrease during a match")
    if snapshot["lines_cleared"] < previous["lines_cleared"]:
        raise ProtocolError("line count cannot decrease during a match")
    ```

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

