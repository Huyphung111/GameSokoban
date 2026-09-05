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

---

## 7. Trạng Thái Bàn Giao Hiện Tại (2026-09-05)

Các thay đổi dưới đây đã được triển khai và cần được bảo tồn trong những lần sửa tiếp theo:

### 7.1. Animation người chơi bốn hướng

- Sprite nguồn nằm tại `assets/player_directions.png.jpg`, gồm thứ tự khung: xuống, lên, trái, phải.
- `src/ui/renderer.py` tách sprite nguồn thành bốn hướng và tạo bốn frame cho từng trạng thái `idle`, `walk`, `push`.
- Hướng nhìn được giữ theo lần di chuyển gần nhất. Khi đứng yên, animation thở tiếp tục chạy; khi đi hoặc đẩy thùng, animation hành động chạy trong `PLAYER_ACTION_MS` rồi trở về idle.
- Thời gian animation nằm trong `src/config.py`:
  - `PLAYER_ACTION_MS = 160`
  - `PLAYER_IDLE_FRAME_MS = 220`
- Luôn scale sprite bằng nearest-neighbor (`pygame.transform.scale`) để giữ pixel art sắc nét.

### 7.2. Hệ thống đánh giá sao

- Màn đã giải luôn nhận tối thiểu 1 sao, kể cả vượt yêu cầu số move.
- Đạt giới hạn move tương ứng sẽ nhận 2 hoặc 3 sao. Các ngưỡng được cấu hình tại `STAR_MOVE_TARGETS` trong `src/config.py` theo dạng `(giới hạn 3 sao, giới hạn 2 sao)`.
- `src/core/progress.py` lưu kỷ lục sao tốt nhất và vẫn tương thích với save cũ.
- Popup hoàn thành và danh sách level chỉ hiển thị biểu tượng sao; không hiển thị thêm dòng giải thích yêu cầu move.

### 7.3. Chuyển và chọn level

- `App.select_level()` trong `main.py` luôn tạo một ván mới từ trạng thái ban đầu.
- Chọn level trong danh sách hoặc dùng Previous/Next không được phục hồi trạng thái đã thắng và không tự mở popup `Level complete`.
- Thành tích đã lưu như sao, best score và trạng thái completed vẫn được giữ trong `Progress`.

### 7.4. Popup hoàn thành

- Animation hiện gồm: nền tối fade-in, popup trượt/phóng có overshoot nhẹ, glow, tiêu đề và thống kê xuất hiện tuần tự, từng ngôi sao pop, sau đó các nút xuất hiện.
- Không sử dụng confetti/pháo giấy. Không thêm lại nếu chưa có yêu cầu mới từ người dùng.
- Để giữ 60 FPS, renderer cache nền bàn chơi, nền đã làm tối và hình nút; chỉ dựng và scale surface nhỏ quanh popup. Khi sửa popup, tránh tạo nhiều surface toàn màn hình trong mỗi frame.
- Kết quả đo headless gần nhất:
  - `900x760`: khoảng `4.49 ms/frame` (`222.9 FPS` rendering capacity).
  - `1920x1080`: khoảng `5.64 ms/frame` (`177.3 FPS` rendering capacity).
- Timeline kiểm tra hình ảnh: `test-artifacts/completion-animation-timeline.png`.

### 7.5. Kiểm thử và trạng thái Git

- Bộ test hiện có `41` test và lần chạy gần nhất đều thành công:
  ```powershell
  python -m unittest discover -s tests
  ```
- Kiểm tra biên dịch gần nhất thành công:
  ```powershell
  python -m compileall -q main.py src tests
  ```
- Trước khi tiếp tục, chạy `git status --short`. Worktree hiện có các thay đổi tính năng chưa commit; không dùng `git reset --hard`, `git checkout --` hoặc ghi đè các file đang sửa.
- Các test liên quan trực tiếp nằm tại:
  - `tests/test_app.py`: reset level, popup completion, layout responsive và animation lifecycle.
  - `tests/test_game.py`: ngưỡng sao, tối thiểu 1 sao và tương thích save cũ.

## 8. Checklist Cho Phiên Code Tiếp Theo

1. Đọc `agent.md`, kiểm tra `git status --short` và xem diff trước khi sửa.
2. Chạy test nền để xác nhận trạng thái ban đầu.
3. Giữ logic game trong `src/core/` độc lập với Pygame.
4. Khi sửa UI/animation, kiểm tra tối thiểu ba kích thước cửa sổ: `480x520`, `900x760`, `1200x800`.
5. Sau thay đổi, chạy toàn bộ 41 test, `git diff --check` và xem trực tiếp screenshot/frame nếu có thay đổi hình ảnh.
