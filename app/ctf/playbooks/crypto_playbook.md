# BQA Extreme Crypto Playbook (Deterministic Cryptanalysis & Solver Engine)

> **Mục tiêu tối thượng:** Biến người giải bài (AI/Human) thành một **Chuyên gia Mật mã học Thực chiến (Professional Cryptanalyst)**.
> Tuyệt đối không đoán mò, không brute-force bừa bãi, không thử random attacks theo cảm tính.
> Mọi bước giải đều phải bắt nguồn từ **Bằng chứng Thực nghiệm (Evidence)**, được mô hình hóa thành **Phương trình Toán học (Mathematical Model)** và kiểm chứng bằng **Kiểm thử Tất định (Deterministic Local Verification)**.

---

## 1. Quy trình 5 Giai đoạn Bắt buộc (The 5-Phase Enforced Crypto Discipline)

Khi giải bất kỳ bài toán Crypto nào trong BotQuangAnh MCP, bạn **BẮT BUỘC** phải tuân theo 5 giai đoạn sau:

```
[ Phase 1: Parameter & Scheme Triage ]
                  │
                  ▼
[ Phase 2: Mathematical Modeling (notes/math_model.md) ]
                  │
                  ▼
[ Phase 3: Attack Vector Selection (Attack Router Matrix) ]
                  │
                  ▼
[ Phase 4: Deterministic Local Verification (script/solve.py) ]
                  │
                  ▼
[ Phase 5: Solution Promotion & Hoarding (solver/ + flag.txt) ]
```

### Phase 1: Parameter & Scheme Triage (Định dạng & Trích xuất)
1. Đọc kỹ mã nguồn (`challenge/*.py`, `challenge/*.sage`) và file dữ liệu (`output.txt`, transcript).
2. Trích xuất toàn bộ tham số công khai:
   - Modulus $n$, số mũ công khai $e$, ciphertext $c$, chữ ký $(r, s)$.
   - Đường cong Elliptic: $p, a, b, G, n, h$.
   - Bộ sinh PRNG: hạt giống, ma trận chuyển trạng thái, số lượng outputs đã lộ.
   - Chế độ mã hóa khối (AES-CBC/ECB/CTR/GCM), IV, nonce, tag.
3. Xác định quy tắc biểu diễn dữ liệu:
   - Byte-order (Big-endian vs Little-endian).
   - Padding (PKCS#7, OAEP, ANSI X.923).
   - Biểu diễn số nguyên: `int.from_bytes(..., 'big')`, hex, base64, PEM.

### Phase 2: Mathematical Modeling (Mô hình hóa Toán học)
- Mở file `notes/math_model.md` và viết tường minh:
  - **Tập hợp / Cấu trúc Đại số:** Vành $\mathbb{Z}/N\mathbb{Z}$, Trường hữu hạn $\mathbb{F}_p$, Nhóm điểm $E(\mathbb{F}_p)$, Lưới $\mathcal{L} \subset \mathbb{Z}^m$, Không gian vector $\mathbb{F}_2^n$.
  - **Biến chưa biết (Unknowns):** Biến nào chứa flag? Biến nào là nonce ngẫu nhiên?
  - **Chặn cận (Bounds):** Các biến ẩn có nhỏ hơn giá trị nào không (ví dụ $d < \frac{1}{3}N^{1/4}$, $|m| < 2^{256}$)?
  - **Hệ phương trình (Equations):** Viết ra các đồng dư thức và ràng buộc đẳng thức.

### Phase 3: Attack Vector Selection (Chọn Vector Tấn công từ Bảng Tra cứu)
- Tra cứu bảng **Attack Router Matrix** dưới đây để chọn đúng 1 thuật toán giải quyết trực diện hệ phương trình.
- Ghi rõ thuật toán được chọn và lý do toán học vào `script/analysis.md`.
- **Tuyệt đối không chạy thử danh sách các công cụ tự động (attack-all tools) khi chưa chứng minh được điều kiện tiên quyết của thuật toán.**

### Phase 4: Deterministic Local Verification (Viết Solver Cục bộ)
- Triển khai code giải toán vào `script/solve.py` (hoặc `script/solve.sage`).
- Cấu trúc script phải gồm 3 hàm rõ ràng:
  - `parse_data()`: Trích xuất chính xác tham số từ input.
  - `derive_secret()`: Giải hệ phương trình (dùng SageMath, SymPy, Z3, gmpy2, fpylll).
  - `verify()`: Thế nghiệm tìm được vào lại **toàn bộ** phương trình ban đầu.
- Nếu bài toán có server tương tác (remote instance), hãy kiểm chứng solver với dữ liệu giả lập (mock local oracle) thành công trước khi kết nối mạng.

### Phase 5: Solution Promotion & Hoarding
- Chạy script qua MCP tool `host_run_command("python3 script/solve.py")`.
- Khi exit code 0 và in ra flag:
  - Hệ thống BQA Harness sẽ tự động promote code sang `solver/solve.py`.
  - Tự động tạo `solver/WRITEUP.md` chuẩn form.
  - Tự động lưu flag sạch vào `flag.txt` và cơ sở dữ liệu SQLite (`verified = true`).

---

## 2. Attack Router Matrix (Bảng Nhận diện Tín hiệu Mật mã)

| Dấu hiệu Quan sát được | Kiểm tra Tiên quyết | Thuật toán / Vector Tấn công Tương ứng |
|---|---|---|
| RSA $e=3$ hoặc rất nhỏ, $c < n$ | Tính $m = \lfloor c^{1/e} \rfloor$, kiểm tra $m^e \stackrel{?}{=} c$ | **Integer $e$-th Root** (không cần modulo) |
| RSA $n$ chung, 2 cặp khóa $(e_1, c_1)$ và $(e_2, c_2)$, $\gcd(e_1, e_2) = 1$ | Bézout identity: $a\cdot e_1 + b\cdot e_2 = 1$ | **Common Modulus Attack**: $m \equiv c_1^a \cdot c_2^b \pmod n$ |
| Nhiều modulus $n_1, n_2, \dots$ | Tính $\gcd(n_i, n_j)$ theo cặp hoặc Batch GCD | **Factoring via Shared Factor**: $p = \gcd(n_i, n_j)$ |
| $p$ và $q$ rất gần nhau ($|p - q| < n^{1/4}$) | Kiểm tra $\lceil \sqrt{n} \rceil^2 - n$ | **Fermat Factorization** |
| $p-1$ chỉ có các ước nguyên tố nhỏ (smooth) | Chọn $B \approx 10^6$, tính $a^{B!} - 1 \pmod n$ | **Pollard's $p-1$ Factorization** |
| RSA private exponent $d$ nhỏ ($d < \frac{1}{3} n^{1/4}$) | Phân số liên tục (Continued Fractions) của $\frac{e}{n}$ | **Wiener's Attack** |
| RSA private exponent $d < n^{0.292}$ | Lưới Coppersmith đa thức 2 biến $ed - k\phi(n) = 1$ | **Boneh-Durfee Attack** |
| 2 ciphertext của 2 tin nhắn có quan hệ $m_2 = a\cdot m_1 + b$ | Lập đa thức $f_1(x) = x^{e_1} - c_1$, $f_2(x) = (ax+b)^{e_2} - c_2$ | **Franklin-Reiter Related Message Attack** ($\gcd$ đa thức) |
| Biết một phần tin nhắn (Stereotyped Message, padding cố định) | Phần ẩn $x_0 < n^{1/e}$ | **Coppersmith Small Roots** (hàm `small_roots` trong SageMath) |
| Biết các bit cao hoặc bit thấp của thừa số $p$ | Lộ $\ge \frac{1}{4}$ số bit của $p$ | **Coppersmith's Partial Key Exposure** ($f(x) = p_0 + x \pmod p$) |
| ECDSA/DSA dùng chung số ngẫu nhiên nonce $k$ | Chữ ký có cùng giá trị $r$ ($r_1 = r_2$) | **Repeated Nonce Attack**: $k = \frac{z_1 - z_2}{s_1 - s_2} \pmod q$, $d = \frac{s_1 k - z_1}{r} \pmod q$ |
| ECDSA lộ một số bit của $k$ (Biased Nonce) | $k_i = 2^b t_i + a_i$ với $|a_i| < B$ | **Hidden Number Problem (HNP)** qua lưới CVP / Babai Nearest Plane |
| Bậc của đường cong Elliptic hoặc Modulus $p-1$ là số trơn (smooth) | Phân tích thừa số của bậc $|E(\mathbb{F}_p)| = \prod p_i^{e_i}$ | **Pohlig-Hellman Algorithm** |
| Đường cong Anomalous: $|E(\mathbb{F}_p)| = p$ | Trace of Frobenius $t = 1$ | **Smart's Attack** ($p$-adic elliptic logarithm) |
| Đường cong Singular ($y^2 = x^3 + ax^2 + bx + c$ có nghiệm bội) | Delta discriminant $\Delta = 0$ | Ánh xạ đồng cấu về $\mathbb{F}_p^*$ (Node) hoặc $\mathbb{F}_p^+$ (Cusp) |
| Bậc nhóm nhỏ hoặc bài toán DLP trong phạm vi $2^{40} - 2^{50}$ | $g^x = h$ | **Baby-step Giant-step (BSGS)** hoặc **Pollard's Rho** |
| Hệ phương trình tuyến tính đồng dư có sai số nhỏ (Noisy Modular Eq.) | $a_i \cdot x - b_i \equiv e_i \pmod q$ với $|e_i| < B$ | **Lattice CVP / LLL / Kannan Embedding** |
| Bài toán Subset Sum / Knapsack với mật độ $d < 0.9408$ | $\sum s_i a_i = S, s_i \in \{0, 1\}$ | **CLOS / Coster-Joux-van de Lune Lattice Reduction** |
| LCG PRNG: $X_{n+1} = a X_n + c \pmod m$ (Lộ toàn bộ state) | Biết 3 output liên tiếp | $a = (X_3 - X_2)(X_2 - X_1)^{-1} \pmod m$, $c = X_2 - a X_1 \pmod m$ |
| Truncated LCG (Chỉ lộ các bit cao của output) | $y_i = \lfloor X_i / 2^k \rfloor$ | **Lattice Reduction (Frieze-Kannan / Stern)** |
| Mersenne Twister (MT19937) | Lộ đủ 624 outputs 32-bit | **Untemper Algorithm** $\to$ Khôi phục 100% internal state array |
| Truncated MT19937 hoặc thiếu output | Biết một phần bit của nhiều output | **Z3 SMT Solver** (mô hình hóa bit-vector 32-bit) |
| LFSR (Linear Feedback Shift Register) | Biết $2L$ bit output liên tiếp | **Thuật toán Berlekamp-Massey** $\to$ Khôi phục đa thức phản hồi |
| Stream Cipher / OTP dùng lại Keystream | $C_1 = P_1 \oplus K, C_2 = P_2 \oplus K$ | $C_1 \oplus C_2 = P_1 \oplus P_2$ (Known-plaintext recovery) |
| AES-CBC cho biết lỗi Padding (Padding Oracle) | Server trả về lỗi padding khác với lỗi giải mã | **Padding Oracle Attack** (giải mã từng byte từ cuối lên đầu) |
| AES-CBC không có kiểm tra toàn vẹn MAC | Cần thay đổi dữ liệu giải mã tại khối $i$ | **CBC Bit-Flipping Attack**: $C_{i-1}' = C_{i-1} \oplus P_i \oplus P_i'$ |
| AES-ECB | Các khối 16 byte giống nhau cho ciphertext giống nhau | **Byte-at-a-time ECB Decryption** (bẫy padding và tra từ điển) |
| AES-GCM dùng lại nonce | 2 ciphertext có cùng Nonce/IV và khác nhau | **GHASH Key Recovery** (giải nghiệm đa thức trên $\mathbb{F}_{2^{128}}$ để tìm khóa xác thực $H$) |
| Hash MAC dạng $H(key \| message)$ với MD5/SHA-1/SHA-256 | Biết $H(key \| m_1)$ và độ dài của $key$ | **Length Extension Attack** (tiếp tục hash state mà không cần biết key) |

---

## 3. Cẩm nang Kỹ thuật Thực chiến Chi tiết

### 3.1. RSA Deep-Dive
- **Wiener's Attack:**
  Khi $d < \frac{1}{3} n^{1/4}$, số hữu tỉ $\frac{k}{d}$ là một phân số hội tụ (convergent) của phân số liên tục của $\frac{e}{n}$.
  Ta tính các convergents $\frac{k}{d}$, kiểm tra $ed - 1$ chia hết cho $k$, tính $\phi = \frac{ed - 1}{k}$, và giải phương trình bậc hai $X^2 - (n - \phi + 1)X + n = 0$.
- **Coppersmith Small Roots:**
  Cho đa thức monic $f(x)$ bậc $\delta$ modulo $n$. Nếu tồn tại nghiệm $|x_0| < n^{1/\delta}$, thuật toán Coppersmith sử dụng LLL sẽ tìm ra nghiệm đó trong thời gian đa thức.
  Trong SageMath: `f.small_roots(X=bound, beta=1.0)`.

### 3.2. Elliptic Curves Deep-Dive
- **ECDSA Repeated Nonce:**
  Phương trình ký: $s_i \equiv k^{-1}(z_i + r d) \pmod q$.
  Khi $k_1 = k_2$, suy ra $s_1 - s_2 \equiv k^{-1}(z_1 - z_2) \pmod q \implies k \equiv \frac{z_1 - z_2}{s_1 - s_2} \pmod q$.
  Sau khi có $k$, ta tính khóa riêng: $d \equiv \frac{s_1 k - z_1}{r} \pmod q$.
- **Smart's Attack (Anomalous Curves):**
  Áp dụng khi $|E(\mathbb{F}_p)| = p$. Ta nâng đường cong lên vành $p$-adic $\mathbb{Q}_p$ (Hensel lifting), ánh xạ điểm thông qua hàm $p$-adic elliptic logarithm $E(\mathbb{Q}_p) \to p\mathbb{Z}_p$, biến bài toán DLP thành phép chia số học đơn giản: $x \equiv \frac{\log_E(Q)}{\log_E(P)} \pmod p$.

### 3.3. Lattice Discipline (Quy chuẩn Lưới 6 Bước)
1. **Centering:** Biểu diễn các phần dư trong khoảng đối xứng $[-\lfloor q/2 \rfloor, \lfloor q/2 \rfloor)$ thay vì $[0, q - 1]$.
2. **Scaling Factor:** Cân bằng trọng số giữa các ẩn số và sai số sao cho các thành phần của vector mục tiêu có cùng độ lớn (cùng norm).
3. **Basis Matrix Setup:** Xác định rõ ma trận xây dựng theo hàng (row vectors) hay theo cột (column vectors). Trong SageMath, hàm `.LLL()` mặc định coi mỗi hàng là một vector cơ sở.
4. **Reduction:** Chạy LLL trước tiên. Nếu số chiều lớn và LLL chưa đạt, dùng BKZ với block size tăng dần (ví dụ 10, 20, 30).
5. **Vector Identification:** Lấy vector ngắn nhất hoặc áp dụng Babai Nearest Plane để giải CVP.
6. **Strict Validation:** Không bao giờ kết luận chỉ vì vector có norm nhỏ; phải thế ngược lại vào hệ phương trình ban đầu để xác thực 100%.

---

## 4. Checklist Kỷ luật Tự Đánh giá (Self-Audit Gate)
Trước khi kết luận đã giải xong:
- [ ] Script solver có chạy hoàn toàn độc lập, không phụ thuộc vào input ngẫu nhiên bên ngoài không?
- [ ] Nghiệm tìm được có thỏa mãn **tất cả** các phương trình và chặn cận ban đầu không?
- [ ] Flag đã được format chuẩn (`FLAG{...}`), ghi ra file `flag.txt` và lưu vào cơ sở dữ liệu BQA chưa?
- [ ] File `solver/WRITEUP.md` đã có đầy đủ 4 phần (Tóm tắt, Các bước tái lập, Bằng chứng thực thi, Flag) theo chuẩn `AGENTS.md` chưa?
