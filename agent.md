# AGENT CONTEXT & INSTRUCTIONS: SOKOBAN PROJECT

Tài liệu này cung cấp toàn bộ ngữ cảnh kiến trúc, quy ước thiết kế và hướng dẫn vận hành dự án Game Sokoban dành cho các AI Agent (Antigravity, Cursor, Copilot, ChatGPT,...).

---

## 1. Tổng Quan Dự Án (Project Overview)

- **Ngôn ngữ & Thư viện chính**: Python 3.10+ (Pygame).
- **Mục tiêu**: Trò chơi Sokoban hoàn chỉnh trên Desktop với tính năng Undo/Redo không giới hạn, lưu tiến độ chơi an toàn (atomic save), tích hợp AI Solver (thuật toán tìm kiếm A* và Hill Climbing), giao diện tự động co giãn (responsive), và âm thanh hiệu ứng tự tổng hợp (không phụ thuộc asset audio ngoài).

---

## 2. Kiến Trúc Thư Mục (Directory Architecture)

Toàn bộ mã nguồn chính của ứng dụng được đóng gói trong thư mục `src/`, phân tách rõ ràng thành 3 tầng trách nhiệm (Separation of Concerns):

```text
Sokoban/
├── main.py                      # Entry point khởi chạy ứng dụng Pygame
├── benchmark.py                 # Công cụ CLI đo đạc hiệu năng của AI Solver
├── requirements.txt             # Thư viện phụ thuộc (chỉ cần pygame)
├── README.md                    # Tài liệu hướng dẫn người dùng
├── agent.md                     # Tài liệu đặc tả kỹ thuật dành cho AI Agent
├── .gitignore                   # Cấu hình bỏ qua git (__pycache__, data/*.tmp,...)
│
├── src/                         # [CORE SOURCE PACKAGE]
│   ├── __init__.py
│   ├── config.py                # Cấu hình tập trung (BASE_DIR, kích thước màn hình, tốc độ)
│   │
│   ├── core/                    # TẦNG LOGIC GAME THUẦN (Độc lập 100% với Pygame)
│   │   ├── __init__.py
│   │   ├── game.py              # Class Game: Quản lý bàn cờ, nước đi, deadlock, undo/redo
│   │   └── progress.py          # Class Progress: Quản lý save/load progress.json, kỷ lục điểm
│   │
│   ├── ai/                      # TẦNG TRÍ TUỆ NHÂN TẠO & THUẬT TOÁN
│   │   ├── __init__.py
│   │   ├── ai_solver.py         # Thuật toán tìm kiếm A* (tối ưu push), Hill Climbing
│   │   └── solutions.py         # Hàm valid_path: Thẩm định tính hợp lệ của chuỗi nước đi
│   │
│   └── ui/                      # TẦNG GIAO DIỆN & ĐỒ HỌA (Phụ thuộc Pygame)
│       ├── __init__.py
│       ├── renderer.py          # Vẽ bàn cờ, modal kết quả, danh sách level, tính toán scale
│       └── audio.py             # Bộ tổng hợp âm thanh 16-bit procedurally generated
│
├── assets/                      # Hình ảnh sprite pixel-art: box.png, floor.png, goal.png, player.png, wall.png
├── data/                        # File dữ liệu tiến trình người chơi: progress.json
├── levels/                      # 11 bản đồ màn chơi đánh số thứ tự (level01_first_step.txt -> level11_final_challenge.txt)
├── tests/                       # Unit tests: test_game.py (kiểm thử luật), test_app.py (kiểm thử UI/App)
├── test-artifacts/              # Kết quả benchmark.json & ảnh chụp màn hình tự động
└── logs/                        # Nhật ký hệ thống
```

---

## 3. Chi Tiết Từng Module (Module Specifications)

### 3.1. `src/config.py`
- `BASE_DIR`: Tính toán `Path(__file__).resolve().parent.parent` trỏ chính xác về thư mục gốc của project.
- Mọi đường dẫn tài nguyên (`levels/`, `assets/`, `data/`) **bắt buộc** phải được tạo từ `BASE_DIR`.
- `LEVEL_FILE`: Trỏ đến map mở màn mặc định `levels/level01_first_step.txt`.
- `level_files()`: Quét toàn bộ `levels/level*.txt` theo thứ tự tự nhiên (từ `level01_` đến `level11_`).

### 3.2. `src/core/game.py` (Rất quan trọng)
- **Hoàn toàn độc lập với Pygame**: Có thể import và chạy trong môi trường headless, web server hoặc unit test.
- `Game.load_level(filepath)`: Đọc và parse cú pháp map, kiểm tra tính hợp lệ:
  - Phải có chính xác 1 người chơi (`@` hoặc `+`).
  - Số lượng hộp (`$`, `*`) phải bằng số lượng đích (`.`, `+`, `*`) và lớn hơn 0.
  - Vùng chơi phải được bao kín hoàn toàn bởi tường `#`.
  - Mọi hộp và đích phải nằm trong vùng sàn mà người chơi có thể tiếp cận được.
- `reverse_distances(floors, goals)`: Sử dụng BFS kéo ngược từ các đích về sàn trống để tính khoảng cách tối thiểu, từ đó xác định danh sách các ô chết cố định `dead_squares`.
- `is_deadlocked(boxes)`: Phát hiện góc chết:
  1. Hộp nằm trên `dead_squares` (ô chết tĩnh).
  2. Bẫy khối 2x2: Khối vuông 4 ô gồm các hộp chưa vào đích và tường mà không thể đẩy giải tỏa được.

### 3.3. `src/ai/ai_solver.py`
- `solve_a_star(game, cancel, max_seconds, max_states)`:
  - Tối ưu hóa **số lần đẩy (pushes)** thay vì số bước đi bộ của người chơi.
  - Giữa các lần đẩy, người chơi tìm đường đi bộ ngắn nhất qua BFS.
  - Sử dụng hàm heuristic admissible tính từ `reverse_distances`.
  - Hỗ trợ cơ chế ngắt sớm (`cancel` event) khi người chơi di chuyển hoặc bấm nút huỷ.
- `solve_hill_climbing_full(game, ...)`: Thuật toán tham lam (Greedy Search) dùng cho mục đích giáo dục hoặc tạo gợi ý nước đi tiếp theo.

### 3.4. `src/ui/renderer.py` & `src/ui/audio.py`
- `Renderer`: Tự động tính toán `tile_size` dựa trên kích thước cửa sổ để hiển thị bàn cờ ở kích thước tối ưu nhất mà không làm vỡ điểm ảnh pixel art (nearest-neighbor sampling).
- `Audio`: Sinh trực tiếp sóng sin âm thanh hiệu ứng (bước đi, đẩy hộp, vào đích, thắng màn) qua `pygame.mixer`, không cần bất kỳ file âm thanh MP3/WAV bên ngoài nào.

---

## 4. Tiêu Chuẩn Thiết Kế Bản Đồ (Level Design Guidelines)

Khi thiết kế hoặc thêm bản đồ mới vào `levels/`:

1. **Định dạng ký tự**:
   - `#`: Tường
   - ` `: Sàn trống
   - `@`: Người chơi trên sàn
   - `+`: Người chơi đang đứng trên ô đích
   - `$`: Hộp trên sàn
   - `*`: Hộp đã nằm trên ô đích
   - `.`: Ô đích trống

2. **Quy tắc bắt buộc**:
   - Bản đồ phải được bao kín bởi tường `#`.
   - Chính xác 1 người chơi, `len(boxes) == len(goals) > 0`.
   - **Không được xuất hiện góc chết tĩnh ngay khi mở màn**: Không được để bất kỳ hộp nào nằm trên `dead_squares` lúc bắt đầu.
   - **100% Phải giải được (Solvable)**: Kiểm tra lại bằng lệnh:
     ```powershell
     python -c "from src.core.game import Game; from src.ai.ai_solver import solve_a_star; g = Game('levels/<ten_map>.txt'); print(solve_a_star(g).status)"
     ```
     Kết quả bắt buộc phải là `solved`.

3. **Nguyên lý tiến trình độ khó (Progression Curve)**:
   - Các màn mới nên có số bước đẩy (pushes) và số trạng thái duyệt (states) tăng tiến dần.
   - Tránh việc độ khó nhảy vọt đột ngột từ 3 pushes lên 20 pushes mà không có các màn trung gian.

---

## 5. Các Lệnh Thao Tác Thường Dùng Cho AI (CLI Commands)

1. **Khởi chạy game**:
   ```powershell
   python main.py
   ```

2. **Chạy toàn bộ bài kiểm tra Unit Tests**:
   ```powershell
   python -m unittest discover -s tests
   # hoặc kiểm tra logic game:
   python -m unittest tests/test_game.py
   ```

3. **Chạy công cụ đo hiệu năng (Benchmark)**:
   ```powershell
   python benchmark.py --seconds 2.0 --output test-artifacts/benchmark.json
   ```

---

## 6. Quy Tắc Lập Trình Dành Cho AI Khi Can Thiệp Code

- **Không vi phạm tính đóng gói**: Tuyệt đối không import thư viện đồ họa `pygame` vào trong `src/core/` hoặc `src/ai/`.
- **Cấu hình đường dẫn**: Luôn import và sử dụng `config.BASE_DIR` thay vì dùng đường dẫn tương đối cứng (`./` hoặc `../`).
- **Bảo tồn Unit Test**: Khi thực hiện refactor hoặc thêm tính năng, luôn chạy lại `python -m unittest tests/test_game.py` để đảm bảo không làm hỏng tính đúng đắn của logic game và hệ thống màn chơi hiện có.
