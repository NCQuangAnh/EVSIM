# Cập nhật theo góp ý của anh Huy Hoàng: black box + module pin, lý do mô hình hoá, ablation

*Ngày 04/10/2026. Toàn bộ số liệu ở đây là kết quả **mô phỏng** (simulator `evsim`, Hà Nội). Chưa có dữ liệu thật của GSM.*

Anh Hoàng góp ý 3 điểm, và cả 3 đã được làm:

1. **Lý do mô hình hoá cho từng thành phần** → xem Mục 2.
2. **Coi hàm cost của GSM là black box, chỉ cộng thông tin pin lên trên** → xem Mục 1.
3. **Ablation study** → xem Mục 3 và 4.

Ghi chú về phiên bản: bản Docs trước đây đã cũ so với simulator đang chạy. Thói quen sạc hiện tại là:
- 90% tài xế rút sạc ở mức cá nhân trong khoảng 60–80%;
- 10% tài xế sạc tới 80–100%;
- sạc qua đêm thì đầy 100%.

---

## 1. Pipeline mới: black box + module pin

![Pipeline black box + module pin](figures/pipeline_battery_addon.png)

**Công thức** (ghép mỗi 30 giây, giải bằng Hungarian):

```
C'_ij = C^GSM_ij + λ · ΔP_từchối(SOC sau chuyến_ij)    # (b) chi phí kỳ vọng do tài xế từ chối vì pin
C'_ij = ∞   nếu sau chuyến xe không đủ pin tới trạm sạc gần nhất (giữ dự phòng 5%)   # (a)
(c) Nhắc sạc theo giờ cho xe rảnh pin thấp — nằm ngoài cost, không đổi C'
```

**C^GSM là black box.**
- Hàm cost thật của GSM chưa biết, nên trong mô phỏng dùng bản xấp xỉ **B1**: quãng đón + rủi ro huỷ + ưu tiên khách chờ lâu + công bằng thời gian rảnh, cùng thang đo "km tương đương".
- Module pin **không sửa** C^GSM, chỉ cộng thêm vào.
- Để kiểm tra module không phụ thuộc vào một black box cụ thể, cùng module được gắn lên 2 black box khác:
  - **B2:** B1 + forward dispatch + repositioning;
  - **B4c:** value-based kiểu DiDi (Xu et al., KDD 2018), có thêm yếu tố huỷ.

## 2. Lý do mô hình hoá (modeling rationale)

| Thành phần | Mô hình hoá cái gì | Vì sao đưa vào | Dạng / tham số | Nguồn tham số | Kiểm tra bằng |
|---|---|---|---|---|---|
| Black box C^GSM | Hàm ghép hiện tại của GSM | Mentor mô tả: batch + cost (khoảng cách, huỷ, …) + Hungarian, không dùng pin. Giữ nguyên thì dễ giải thích, dễ triển khai, dễ so sánh. | B1: `km đón + 5·P(huỷ) − 0,2·phút chờ − 0,1·phút rảnh` | Mô tả của mentor; trọng số là giả định mô phỏng | Thay bằng B2, B4c (nhóm E) |
| (a) Ràng buộc khả thi | Xe không được nhận chuyến nếu sau chuyến không còn đủ pin tới trạm sạc gần điểm trả | Hết pin giữa đường là sự cố nặng: cứu hộ, mất khách, ảnh hưởng thương hiệu. Đây là ràng buộc an toàn, không phải đánh đổi, nên đặt dạng cứng (C' = ∞). | Dự phòng 5% SOC; tiêu hao theo km đường | Dự phòng 5% là giả định; tiêu hao theo thông số xe | Bật/tắt (A, B); khi tài xế không tự tránh (F1) |
| (b) Chi phí từ chối do pin | Xác suất tài xế từ chối thêm vì SOC sau chuyến thấp | Ở baseline, 1/3 đến 2/3 số lần từ chối là do pin. Mỗi lần từ chối, khách phải chờ thêm một vòng ghép và dễ huỷ hơn. Cộng **kỳ vọng** thì cùng đơn vị với black box và không cấm hẳn. | `λ·[P(từ chối\|SOC sau) − P(từ chối\|pin cao)]`; đường cong đơn điệu, P nền = 5,1%; ở SOC 20% là 36,5%; ở 10% là 91,7% | Fit từ log nhận/từ chối **mô phỏng** của B1 (seed 200–201). Khi có log thật của GSM thì fit lại. | Bật/tắt (A, B); quét λ = 0,5–8 (C) |
| λ | Giá của một lần từ chối kỳ vọng, tính theo đơn vị của black box | Đơn vị của C^GSM thật chưa biết, nên λ phải quét chứ không cố định | λ = 1 (≈ 1 km đón) | Chọn trên seed tuning 100–101, tách khỏi seed đánh giá | Nhóm C |
| (c) Nhắc sạc theo giờ | Xe đang rảnh và SOC dưới ngưỡng thì được gợi ý đi sạc ngay | Sạc vào giờ cao điểm là tốn nhất (mất xe đúng lúc thiếu xe). Nạp trước cao điểm thì vào cao điểm đủ pin. | Trước cao điểm (6–7h, 15h30–17h): < 50%; trong cao điểm: < 15%; giờ khác: < 30%; không nhắc nếu còn < 60 phút là hết ca | Ngưỡng là giả định; giờ cao điểm lấy từ γ(t) | Bật/tắt (A, B) |
| Chất lượng SOC | Nền tảng biết SOC chính xác tới đâu | Telemetry thật có thể nhiễu, báo trễ hoặc chỉ báo theo mức | exact / nhiễu sd 5% / báo mỗi 5 phút / theo dải 25% | Giả định | Nhóm D |
| Hành vi tài xế | Tài xế có tự quản lý pin không | Lợi ích của (a) và (b) phụ thuộc vào việc tài xế đã tự tránh chuyến khi pin thấp hay chưa | Không từ chối vì pin; hoặc đi sạc muộn (ngưỡng 3–12% thay vì 8–25%) | Giả định, cần log GSM để xác nhận | Nhóm F |

## 3. Thiết kế thí nghiệm

- **Hai quy mô.**
  - Quy mô thật: 5.080 xe, 118.533 chuyến/ngày; chạy nhóm A và E.
  - Quy mô nhỏ: 1.000 xe, 23.333 chuyến/ngày; chạy nhóm A–D và F.
  - Mỗi lần chạy mô phỏng 72 giờ.
- **Tách seed.**
  - Seed 0–4: chỉ dùng để đánh giá.
  - Seed 100–101: chọn λ.
  - Seed 200–201: fit đường cong từ chối và value của DiDi.
- **So sánh theo cặp.** Cùng một seed thì cùng nhu cầu và cùng tài xế, chỉ khác chính sách. Báo cáo chênh lệch trung bình ± độ lệch chuẩn, kèm p-value của paired t-test (n = 5).
- **Các nhóm ablation:**
  - **A — cộng dồn:** black box → +(a) → +(a)(b) → +(a)(b)(c).
  - **B — bỏ từng phần:** bỏ (a); bỏ (b); chỉ giữ (c).
  - **C — quét λ:** 0,5; 1; 2; 4; 8.
  - **D — chất lượng SOC:** nhiễu, báo trễ, theo dải.
  - **E — đổi black box:** B2, B4c.
  - **F — hành vi tài xế:** F1 tài xế không bao giờ từ chối vì pin; F2 tài xế đi sạc muộn.
- Mọi lần chạy đều được lưu theo seed (`outputs/runs/index.csv`) và chạy lại cho kết quả giống hệt.

## 4. Kết quả

Cách đọc ô: `giá trị (chênh lệch so với black box ± sd, p-value)`. Đơn vị "pt" là điểm phần trăm.

### 4.1 Quy mô thật (5.080 xe): nhóm A và E

| Cấu hình | Service level (%) | Service giờ cao điểm (%) | Chờ P90 (phút) | Tỷ lệ từ chối do pin (%) | Xe đang sạc lúc cao điểm (%) | Hàng chờ sạc (phút) | Chi phí điện | Lợi nhuận/xe/ngày (nghìn đ) |
|---|---|---|---|---|---|---|---|---|
| Black box B1 | 82,19 | 78,26 | 16,07 | 31,7 | 3,66 | 2,4 | — | 1.275,2 |
| + (a) | −0,08 (p=0,030) | −0,02 (p=0,71) | +0,00 | −0,1 | −0,02 | +0,0 | −0,2% | −1,45 (p=0,048) |
| + (a)(b) | −0,08 (p=0,005) | −0,09 (p=0,19) | −0,01 | −0,3 | −0,01 | +0,3 | −0,4% | −1,73 (p=0,002) |
| **+ (a)(b)(c) đầy đủ** | **+0,21 (p=0,004)** | **+0,78 (p<0,001)** | **−0,32 (p=0,006)** | **−17,7** | **3,66 → 2,68** | +2,5 | +2,2% | +1,39 (p=0,082) |
| Black box B2 | 83,15 | 80,46 | 15,51 | 59,8 | 2,98 | 2,2 | — | 1.294,9 |
| B2 + module | **+0,17 (p=0,033)** | **+0,41 (p=0,009)** | **−0,20 (p=0,002)** | −19,8 | 2,98 → 2,49 | +2,5 | +2,7% | +0,31 (p=0,76) |
| Black box B4c | 84,05 | 79,62 | 11,44 | 59,7 | 3,10 | 2,6 | — | 1.298,3 |
| B4c + module | **+0,36 (p=0,001)** | **+0,71 (p<0,001)** | **−0,22 (p=0,006)** | −16,9 | 3,10 → 2,54 | +1,6 | +1,8% | **+4,50 (p=0,007)** |

### 4.2 Quy mô nhỏ (1.000 xe), black box B1: nhóm A–D

| Cấu hình | Service (%) | Service cao điểm | Chờ P90 | Từ chối do pin | Lợi nhuận/xe/ngày |
|---|---|---|---|---|---|
| Black box B1 | 78,35 | 72,65 | 17,73 | 31,8% | 1.194,0 |
| + (a) | −0,03 (p=0,77) | +0,22 (p=0,39) | +0,16 | −0,0 | +0,13 (p=0,93) |
| + (a)(b) | −0,10 (p=0,42) | −0,16 (p=0,27) | +0,14 | −0,2 | −1,64 (p=0,29) |
| + (a)(b)(c) đầy đủ | **+0,34 (p=0,023)** | **+1,33 (p=0,003)** | **−0,30 (p=0,018)** | −17,6 | +3,97 (p=0,077) |
| Bỏ (a) | +0,35 (p=0,019) | +1,47 (p<0,001) | −0,29 | −17,2 | +4,68 (p=0,027) |
| Bỏ (b) | +0,29 (p=0,055) | +1,28 (p=0,001) | −0,24 | −16,9 | +2,93 (p=0,10) |
| Chỉ (c) | +0,29 (p=0,045) | +1,25 (p=0,001) | −0,29 | −17,1 | +2,70 (p=0,11) |
| λ = 0,5 / 2 / 4 / 8 | +0,25 / +0,29 / +0,36 / +0,35 | +1,1 đến +1,3 | −0,2 đến −0,4 | −17 đến −18 | +3,3 đến +4,3 |
| SOC nhiễu sd 5% | +0,30 (p=0,037) | +1,31 | −0,22 | −19,0 | +2,85 |
| SOC báo mỗi 5 phút | +0,36 (p=0,012) | +1,33 | −0,33 | −17,3 | +4,43 |
| SOC theo dải 25% | +0,34 (p=0,030) | +1,29 | −0,24 | −16,5 | +3,73 |

### 4.3 Hành vi tài xế (1.000 xe): nhóm F

| Cấu hình | Service (%) | Service cao điểm | Xe hết pin/ngày | Từ chối do pin | Lợi nhuận/xe/ngày |
|---|---|---|---|---|---|
| F1: tài xế **không bao giờ** từ chối vì pin, black box | 78,77 | 73,55 | **2,00** | 0% | 1.201,2 |
| F1 + (a) | −0,19 (p=0,023) | −0,08 | **0,00 (p=0,008)** | 0% | −0,49 (p=0,73) |
| F1 + module đầy đủ | +0,04 (p=0,60) | **+0,65 (p=0,002)** | **0,07 (p=0,009)** | 0% | +0,36 (p=0,61) |
| F2: tài xế **sạc muộn** (ngưỡng 3–12%), black box | 78,63 | 73,42 | 0,00 | 21,0% | 1.201,5 |
| F2 + module đầy đủ | **+0,28 (p=0,016)** | **+0,74 (p=0,002)** | 0,00 | −16,4 pt | +1,56 (p=0,23) |

Bảng đầy đủ (thêm chờ trung bình, tỷ lệ từ chối, hàng chờ sạc, chi phí điện) có trong `outputs/ablation/full_table.md` và `small_table.md`.

## 5. Kết luận

1. **Module pin cải thiện black box một cách nhất quán.**
   - Áp lên cả 3 black box, service level đều tăng, có ý nghĩa thống kê: B1 +0,21 pt, B2 +0,17 pt, B4c +0,36 pt.
   - Giờ cao điểm tăng +0,4 đến +0,8 pt; thời gian chờ P90 giảm 0,2–0,3 phút.
   - Tỷ lệ từ chối do pin giảm khoảng 17–20 pt.
2. **Gần như toàn bộ lợi ích đến từ (c) nhắc sạc theo giờ.**
   - Chỉ dùng (c) đã đạt gần bằng module đầy đủ.
   - Cơ chế: xe được nạp trước cao điểm, nên trong cao điểm ít xe phải đi sạc (3,7% → 2,7% đội xe).
   - Cái giá phải trả: chi phí điện tăng khoảng 2%, hàng chờ sạc tăng khoảng 2,5 phút.
   - Lợi nhuận tăng nhưng chỉ có ý nghĩa thống kê với B4c (+4,5 nghìn đ/xe/ngày).
3. **(a) và (b) đứng riêng không giúp, thậm chí hơi giảm (−0,08 pt) khi tài xế đã tự quản lý pin.**
   - Lý do: trong mô phỏng, tài xế đã tự từ chối chuyến khi pin thấp rồi đi sạc. Ràng buộc phía ghép chỉ bớt lựa chọn của Hungarian.
   - λ hầu như không ảnh hưởng trong khoảng 0,5–8.
4. **(a) là lớp an toàn, giá trị của nó phụ thuộc vào hành vi tài xế (nhóm F).**
   - Nếu tài xế **không** tự tránh chuyến khi pin thấp, black box để xảy ra khoảng 2 xe hết pin/ngày trên 1.000 xe.
   - (a) đưa con số này về 0, đổi lại service giảm 0,19 pt.
   - Module đầy đủ giữ hết pin ở mức 0,07 xe/ngày, đồng thời service cao điểm vẫn tăng +0,65 pt.
   - Với tài xế sạc muộn, module vẫn tăng service +0,28 pt.
   - Muốn biết GSM rơi vào trường hợp nào thì cần log thật.
5. **Không cần SOC chính xác.**
   - Nhiễu 5%, báo mỗi 5 phút, hay chỉ biết theo dải 25% đều cho kết quả gần như module có SOC chính xác.
   - Hệ quả thực tế: GSM không phải đầu tư thêm telemetry mới triển khai được.

## 6. Hạn chế

- **Toàn bộ là mô phỏng.**
  - Hàm cost B1 chỉ là xấp xỉ của GSM.
  - Đường cong từ chối được fit từ dữ liệu mô phỏng, chưa phải log thật.
  - Ngưỡng nhắc sạc, giờ cao điểm và số cổng sạc ở các trạm là giả định.
- **Mức cải thiện tuyệt đối nhỏ** (0,2–0,4 pt service), nhưng ổn định qua seed và qua các black box.
  - Ở 118.533 chuyến/ngày, +0,21 pt tương đương khoảng 250 chuyến/ngày được phục vụ thêm.
- **Chưa mô hình hoá:**
  - phản ứng của tài xế khi được nhắc sạc: hiện giả định họ luôn làm theo;
  - chi phí cứu hộ khi hết pin;
  - giá điện theo giờ.
- **Một chi tiết còn mở:** ở quy mô thật, module đầy đủ vẫn để 0,27 xe hết pin/ngày (bằng black box), trong khi (a) đứng riêng đưa về 0. Cần kiểm tra thêm nguồn gốc (có thể từ chuyến đi sạc theo nhắc). So với 5.080 xe thì con số này rất nhỏ.

## 7. Dữ liệu cần từ GSM (anh Thanh) để thay giả định bằng số thật

1. Log gửi cuốc → nhận/từ chối, kèm SOC của xe lúc nhận cuốc. Dùng để fit lại (b) và kiểm tra tài xế có tự tránh chuyến khi pin thấp hay không (nhóm F).
2. Sự cố hết pin hoặc cứu hộ mỗi ngày, và chi phí mỗi sự cố. Dùng để định giá (a).
3. Phân bố SOC lúc tài xế bắt đầu và kết thúc sạc, theo giờ trong ngày.
4. Tần suất và độ chính xác của telemetry SOC.
5. Mô tả các thành phần trong hàm cost hiện tại (không cần trọng số), để chọn black box xấp xỉ sát hơn.

## 8. Những chỗ cần sửa trong bản Docs cũ

- Thay sơ đồ pipeline cũ bằng `figures/pipeline_battery_addon.png`.
- Sửa ví dụ Hungarian: tổng cost tối ưu là **6,5**.
- Cập nhật thói quen sạc: 90% rút ở 60–80%, 10% sạc tới 80–100%, qua đêm đầy 100%.
- Thay bảng kết quả cũ bằng Mục 4.
- Ghi chú lại hai ý trong bản cũ: "VinFast miễn phí sạc 3 năm" và quy định của Vinhomes. Cần nêu rõ phạm vi áp dụng và nguồn, hoặc ghi là chưa xác minh.
