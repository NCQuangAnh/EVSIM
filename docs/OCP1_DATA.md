# Kịch bản Vinhomes Ocean Park 1 (OCP1): dữ liệu và thiết lập mô phỏng (bản thống nhất với `evsim`)

*Bản 2026-10-12. Thay thế phần thiết lập trong `SOC-REPORT.pdf` (repo VRIC_Dispatching_SOC). Kịch bản OCP1 nay chạy bằng **cùng engine `evsim`** và **cùng lớp pin v2.1** đã được đánh giá ở quy mô Hà Nội, để bản đồ demo và kết quả trong báo cáo nhất quán với nhau.*

*Mọi con số trong tài liệu là mô phỏng. Tài liệu này không chép kết quả của mô phỏng cũ; kết quả ở mục 7 được chạy lại bằng `evsim`.*

Nhãn nguồn dùng trong các bảng:

- **[Nguồn]**: có tài liệu hoặc dữ liệu công khai.
- **[Kế thừa]**: giống thiết lập mô phỏng Hà Nội đã chạy (`hanoi_full`).
- **[Giả định]**: giả định của nhóm, cần kiểm chứng.

## 1. Mục đích

- Dựng một kịch bản nhỏ, nhìn được bằng mắt (60 xe, một khu đô thị) để **demo trên bản đồ**.
- Hai bản đồ chạy song song, **cùng nhu cầu và cùng tài xế** (cùng seed, common random numbers):
  - **Trái:** luật ghép kiểu GSM (B1), không dùng thông tin pin.
  - **Phải:** B1 + lớp pin v2.1.
- Kết quả chính của dự án vẫn là đánh giá ở quy mô Hà Nội (`outputs/eval_main_report.md`). OCP1 là kịch bản minh hoạ.

## 2. Dữ liệu đầu vào

### 2.1 Mạng đường và không gian

| Mục | Giá trị | Nhãn |
|---|---|---|
| Đồ thị đường | 1.110 nút, 1.517 cạnh hai chiều, tổng 144,2 km, bbox 20,9841–21,0048 / 105,9334–105,9629 (`data/ocp1/ocp1_graph.json`, lấy từ OSM ngày 09/10/2026) | [Nguồn] OSM |
| Định tuyến | Đường ngắn nhất theo cạnh (Dijkstra) giữa các nút. Điểm bất kỳ được gắn vào nút gần nhất. | Mới cho OCP1 |
| Tốc độ | Hồ sơ tốc độ theo giờ của mô hình Hà Nội: giờ cao điểm 7–9h và 17–19h chậm hơn. Tốc độ theo cấp đường của OSM (15–60 km/h) có trong dữ liệu nhưng chưa dùng. | [Kế thừa] |
| Hồ San Hô | Các cạnh mặt nước {120, 206, 551, 552, 871, 923} bị loại khỏi đồ thị | Theo dữ liệu gốc |
| Cổng Đông | Đoạn cụt bị cô lập (Dijkstra = ∞): không sinh xe, không gán khách | Theo dữ liệu gốc |
| Zone | 9 neo: 8 neo của dữ liệu gốc (Vincom, Vinschool, Depot, cổng Bắc / Nam / Tây, Sapphire 1, Sapphire 2; bỏ cổng Đông) và thêm 1 neo khu dân cư phía nam trung tâm (cụm trạm sạc st09/st10). Mỗi neo có trọng số nhu cầu, điểm được rải ±250 m quanh neo. | Theo dữ liệu gốc + [Giả định] trọng số |

### 2.2 Đội xe và tài xế

| Mục | Giá trị | Nhãn |
|---|---|---|
| Số xe | 60 | Theo dữ liệu gốc |
| Loại xe | **Chỉ VinFast VF5**: pin 37,23 kWh, tiêu thụ 0,16 kWh/km | [Kế thừa] (bản gốc trộn VF e34; engine chưa hỗ trợ nhiều loại xe) |
| Ca làm | Phân bố ca theo γ(t) của mô hình Hà Nội; online 8–14 giờ; tối đa lái 10 giờ/ngày và 4 giờ liên tục; có nghỉ ăn | [Kế thừa] |
| Ngưỡng tự đi sạc | Mỗi tài xế một ngưỡng U(8%, 25%) | [Kế thừa] |
| Mức rút sạc | 90% tài xế rút ở 60–80%, 10% ở 80–100%; 50% sạc đầy qua đêm | [Kế thừa], quyết định của nhóm ngày 03/10 |
| Hành vi đa dạng | Ngưỡng có nhiễu (độ lệch 3%) và tăng thêm tới 10% trong 2 giờ cuối ca; luật từ chối riêng cho từng tài xế; mức nghe lời nhắc sạc ~ Beta, trung bình 60% | [Kế thừa] (`driver_hetero`) |
| Từ chối cuốc | Theo SOC sau chuyến so với ngưỡng riêng; thêm lý do khác khi điểm đón xa hơn 3 km | [Kế thừa] |
| Sạc trước khi về nhà | Không đủ pin về nhà mà vẫn giữ 5% dự trữ thì sạc trước | [Kế thừa] |

### 2.3 Nhu cầu

| Mục | Giá trị | Nhãn |
|---|---|---|
| Số lượt đặt | Trung bình 1.276 lượt/ngày; đặt lại sau khi huỷ được tính thêm | Theo dữ liệu gốc |
| Theo giờ | Hồ sơ giờ của mô hình Hà Nội (đỉnh 7–9h và 17–19h) | [Kế thừa] |
| Không gian | 65% chuyến nội khu: quãng lognormal trung vị 1,6 km, cắt trong 0,5–3,5 km. 35% chuyến ra cửa ngõ (cổng Bắc / Nam / Tây): trung vị 10 km, cắt trong 6–16 km; phần ngoài bản đồ đi theo đường chim bay × hệ số đường vòng 1,3 | Theo dữ liệu gốc |
| Kiên nhẫn của khách | Phân phối mũ, trung bình 20 phút; 5% huỷ sớm; đặt lại 50–60%, tối đa 3 lần, mỗi lần kiên nhẫn × 0,7 | [Kế thừa] |

### 2.4 Trạm sạc: 40 cổng (kịch bản có áp lực)

Dữ liệu gốc có 30 điểm. 10 điểm là trạm xe máy điện nên bị bỏ. Còn lại 96 cổng DC cho ô tô. Kịch bản demo **chỉ giữ 40 cổng**, để việc sạc trở thành nút thắt như ở quy mô Hà Nội (0,65 cổng/xe ở Hà Nội; ở đây 0,67 cổng/xe).

| Trạm | Loại | Cổng (gốc → demo) | Công suất danh định |
|---|---|---|---|
| st03 Vincom Mega Mall | Trung tâm thương mại | 12 → 8 | 60 kW |
| st04 VinBus Depot | Depot | 12 → 8 | 60 kW |
| st05, st09, st10, st17, st25, st27 | Khu dân cư, rải đều toàn khu | 4 → 4 mỗi trạm | 30 kW |

- File: `data/ocp1/ocp1_stations_demo40.json`.
- Công suất hiệu dụng [Kế thừa]: bị giới hạn bởi xe (DC tối đa 50 kW × hệ số đường cong 0,8). Từ 80% SOC trở lên chỉ còn 15 kW. Hiệu suất sạc 0,9.
- Một phần cổng bị xe tư nhân chiếm theo giờ, theo bảng của dữ liệu gốc (20% về đêm, 60% giữa trưa) [Giả định].

### 2.5 Kinh tế

| Mục | Giá trị | Nhãn |
|---|---|---|
| Cước | Green SM Car Hà Nội: 30.500 đ cho 2 km đầu; 14.700 đ/km tới km 12; 13.800 đ/km tới km 25; 11.900 đ/km sau đó; phụ phí đêm (22–6h) 20.000 đ | [Nguồn] greensm.com |
| Điện | 3.858 đ/kWh (V-Green) | [Nguồn] |
| Tài xế | Lương cứng 5,31 triệu đ/tháng + hoa hồng 25% doanh thu | [Nguồn] FAQ greensm.com |
| Lợi nhuận | Doanh thu − trả tài xế − tiền điện − cứu hộ. **Điều chỉnh theo năng lượng tồn trong pin cuối kỳ.** Chưa trừ khấu hao xe và chi phí cố định. | [Kế thừa] |

## 3. Điều phối và lớp pin

- **Black box B1**, ghép mỗi 30 giây bằng Hungarian:

  ```
  F_ij = km đón + km chờ xe rảnh + 5·P(huỷ | ETA) − 0,2·phút khách đã chờ − 0,1·phút tài xế đã rảnh
  ```

  Bán kính tìm xe tăng dần theo thời gian khách chờ. B1 không dùng pin.
- **Lớp pin v2.1** (khoá ngày 11/10, `docs/protocol.md`):
  - (a) Cấm cặp xe–khách nếu sau chuyến xe không tới được trạm nào mà vẫn còn 5% pin. Kèm nhắc sạc khi SOC không đủ cho một chuyến 30 km.
  - (b) G = F + λ · s_F · q, với λ = 0,5. s_F là IQR của F trong batch, nên phần pin không phụ thuộc đơn vị của F. q là xác suất từ chối tăng thêm do pin.
  - (c) Nhắc sạc theo giờ cho xe đang rảnh: dưới **70% trong 2,5 giờ trước mỗi cao điểm**, dưới 15% trong cao điểm, dưới 30% ở giờ khác. Tài xế có thể bỏ qua và tự chọn trạm.
- **Khác với bản gốc:**
  - Bỏ dạng F + B với E_ij và O_ij tính bằng đồng. Dạng này trộn đơn vị km với đồng, nên phần pin lấn át F.
  - Bỏ việc cấm theo SOC < max(0,15; θ_i), vì nền tảng không biết θ_i của từng tài xế.

## 4. Thay đổi so với `SOC-REPORT.pdf` và lý do

| Bản gốc | Bản này | Lý do |
|---|---|---|
| Engine riêng, nhịp ghép 2 phút | `evsim`, nhịp 30 giây | Thống nhất với mọi kết quả đã đánh giá |
| Hàm cost F + B tính bằng đồng | B1 + lớp pin v2.1, chuẩn hoá theo IQR | Không trộn đơn vị; đúng framework G(F, B) |
| 30 trạm, 156 cổng (gồm 60 cổng xe máy) | 8 trạm, 40 cổng ô tô | Bỏ trạm xe máy; tạo áp lực sạc để demo có ý nghĩa |
| VF5 + VF e34 | Chỉ VF5 | Engine chưa hỗ trợ nhiều loại xe; giống mô hình Hà Nội |
| Ca 70% ngày / 10% chiều / 20% đêm | Phân bố γ(t) của mô hình Hà Nội | Thống nhất |
| Mức rút sạc 70% ở 80%, 20% ở 90%, 10% ở 100% | 90% ở 60–80%, 10% ở 80–100% | Quyết định của nhóm ngày 03/10 |
| Điều hoà hao 1,2 kW khi xe đỗ chờ | Không mô hình hoá | Chưa có trong engine; đánh dấu là phần mở rộng |
| 7 seed × 20 ngày, SEM theo ngày | Ghép cặp theo seed, có CRN, khoảng tin cậy theo seed | Các ngày trong cùng seed không độc lập |
| Lợi nhuận theo tiền điện đã mua | Lợi nhuận điều chỉnh theo năng lượng tồn trong pin | So sánh công bằng giữa các nhánh |

## 5. Đầu ra

- **Chỉ số** (giống mô hình Hà Nội):
  - service level, kể cả riêng giờ cao điểm;
  - thời gian chờ trung bình và P90;
  - tỷ lệ từ chối và phần do pin;
  - số xe đang sạc lúc cao điểm;
  - hàng chờ sạc, số xe hết pin;
  - km rỗng, tiền điện đã điều chỉnh, lợi nhuận đã điều chỉnh, thu nhập tài xế.
- **Quỹ đạo cho bản đồ**, mỗi nhánh một file JSON:
  - mỗi chặng của mỗi xe: thời điểm bắt đầu và kết thúc, dãy nút đi qua, loại chặng, SOC đầu và cuối;
  - các sự kiện khách: đặt, ghép, đón, trả, huỷ;
  - trạng thái từng trạm theo phút: số cổng đang dùng và hàng chờ.

## 6. Hạn chế

- Nhu cầu và hành vi tài xế là mô phỏng. Chuyến ra cửa ngõ đi ngoài bản đồ theo đường chim bay × hệ số đường vòng.
- Không mô hình hoá: giao thông vi mô (đèn, nút giao), điều hoà khi đỗ, suy giảm pin, nhiệt độ.
- 40 cổng là lựa chọn để tạo áp lực cho demo, không phải số liệu thật về hạ tầng OCP1.

## 7. Kết quả OCP1 (`evsim`, 2026-10-12)

20 seed (1000–1019), mỗi lượt chạy 48 giờ, ghép cặp theo seed, có CRN. Nguồn: `outputs/ocp1/ocp1_stats.md`, sinh bằng `scripts/ocp1_demo.py stats`.

| Chỉ số | B1 | B1 + v2.1 | Chênh lệch (khoảng tin cậy 95%) | Số seed có lợi |
|---|---|---|---|---|
| Service level | 77,33% | 78,16% | **+0,83 pt (± 0,24)** | 90% |
| Service giờ cao điểm | 74,47% | 76,03% | **+1,56 pt (± 0,61)** | 90% |
| Chờ P90 (phút) | 16,71 | 16,27 | −0,44 (± 0,42) | |
| Phần từ chối do pin | 34,3% | 17,4% | −16,9 pt | |
| Xe đang sạc lúc cao điểm | 4,60% | 2,52% | −2,1 pt | |
| Hàng chờ sạc (phút) | 0,40 | 0,64 | +0,24 | |
| Xe hết pin | 0 | 0 | 0 | |
| Tiền điện đã điều chỉnh (đ/ngày, cả đội) | 6,41 triệu | 6,52 triệu | +0,11 triệu | |
| **Lợi nhuận đã điều chỉnh (đ/xe/ngày)** | 651,6k | 658,1k | **+6,5k (± 2,1k)** | 90% |

- Kết quả cùng chiều với đánh giá ở quy mô Hà Nội: B1 + v2.1 tăng 0,69 pt service và 10,4k đ/xe/ngày.
- **Seed demo là 1002.** Đây là seed có mức tăng gần trung vị nhất trên cả ba chỉ số (service, service giờ cao điểm, lợi nhuận), nên nó cho thấy một ngày điển hình chứ không phải ngày đẹp nhất.
- Bản đồ phát lại: `web/replay.html`. Dữ liệu phát lại sinh bằng `scripts/ocp1_demo.py export --seed 1002`.
