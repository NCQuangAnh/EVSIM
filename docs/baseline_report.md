# Baseline điều phối đội xe điện Green SM tại Hà Nội (B1, B2)

Nhóm 2 – EV Fleet Dispatching & Real-time Optimization · Cập nhật 03/10/2026

Tài liệu mô tả hai baseline điều phối, toàn bộ tham số của mô phỏng, nguồn của từng tham số và kết quả chạy ở quy mô Hà Nội. Đây là mốc để so sánh với phương pháp battery-aware (B3) sau này.

## 0. Quy ước nguồn

Mỗi tham số được gắn một trong bốn nhãn:

| Nhãn | Ý nghĩa |
|---|---|
| **[Nguồn N]** | Lấy từ nguồn công khai, số N ở mục 8. Nhóm đã tự mở trang và đối chiếu ngày 30/09/2026. |
| **[Nguồn thứ cấp N]** | Lấy từ đại lý, báo hoặc bản tổng hợp. Chưa đối chiếu được với trang chính thức. |
| **[Nhóm cung cấp]** | Thông tin nhóm thu thập hoặc được mentor kể, chưa có văn bản công khai. |
| **[Mô phỏng]** | Giả định của mô hình, không có nguồn. Cần kiểm chứng bằng dữ liệu GSM hoặc chạy phân tích độ nhạy. |

## 1. Phạm vi mô phỏng

- **Khu vực:** nội thành Hà Nội và hành lang tới sân bay Nội Bài (vĩ độ 20,95–21,24; kinh độ 105,74–105,93). [Mô phỏng]
- **Loại xe:** chỉ Green SM Car, dùng VinFast VF5. Không mô phỏng xe máy. [Mô phỏng]
- **Thời gian:** 3 ngày liên tục, mỗi 30 giây ghép xe một lần. Chạy 5 seed, báo cáo trung bình ± độ lệch chuẩn. [Mô phỏng]
- **Quy mô:** 5.080 xe [Nhóm cung cấp: ước lượng số xe GSM trong vùng, chưa rõ nguồn gốc]. 118.533 lượt đặt/ngày, bằng khoảng 23 lượt/xe/ngày [Mô phỏng: giữ tỷ lệ xe/khách của các lần chạy trước]. Để đối chiếu, GSM công bố khoảng 1 triệu chuyến/ngày trên toàn hệ thống, gồm cả xe máy và nhiều tỉnh thành [Nguồn thứ cấp 13].

## 2. Hai baseline

### B1 – GSM hiện tại (`gsm_baseline`)

Theo mô tả của mentor [Nhóm cung cấp]: hệ thống lấy một batch tài xế và một batch khách, dựng ma trận chi phí gồm quãng đường, khả năng khách huỷ và một số yếu tố khác, ghép bằng thuật toán Hungarian, rồi gửi yêu cầu đón khách. **Hệ thống không dùng thông tin pin.**

Cách hiện thực trong mô phỏng. Cấu trúc (quãng đường + khả năng khách huỷ + Hungarian) theo mô tả của mentor. Các trọng số 5; 0,2; 0,1, độ kiên nhẫn 20 phút và bán kính 2,5 km là [Mô phỏng], vì chưa biết trọng số thật GSM dùng.

```
# Chi phí khi ghép XE i với KHÁCH j (điểm càng THẤP thì cặp càng tốt).
# Đơn vị chung là "km quy đổi": mọi yếu tố được đổi ra tương đương bao nhiêu km đi đón.

chi_phí(i, j) =   quãng_đường_đón                  # (1) số km xe i chạy rỗng tới chỗ khách j (theo mạng đường OSM)
                + 5 × rủi_ro_khách_huỷ             # (2) phạt nếu xe tới chậm, khách dễ huỷ
                − 0,2 × phút_khách_đã_chờ           # (3) thưởng cho khách đã chờ lâu (ưu tiên họ trước)
                − 0,1 × phút_tài_xế_đã_rảnh         # (4) thưởng cho tài xế đã rảnh lâu (chia cuốc công bằng)

# (2) Rủi ro khách huỷ, là một xác suất từ 0 đến 1:
rủi_ro_khách_huỷ = 1 − e^(−ETA / 20 phút)          # ETA = số phút xe i cần để tới chỗ khách j
                                                    # ETA = 0 phút  -> rủi ro 0%  (xe tới ngay)
                                                    # ETA = 5 phút  -> rủi ro 22%
                                                    # ETA = 10 phút -> rủi ro 39%
                                                    # 20 phút = độ kiên nhẫn trung bình của khách (giả định)

# (4) phút_tài_xế_đã_rảnh tối đa chỉ tính 30 phút, để thưởng này không lấn át các yếu tố khác.

# Luật loại bỏ: nếu xe ở quá xa thì cặp này không được ghép.
nếu quãng_đường_đón > bán_kính_tìm_xe  =>  chi_phí = ∞   # (vô cùng, tức là cấm ghép)
bán_kính_tìm_xe = 2,5 km + 1 km × phút_khách_đã_chờ     # khách chờ càng lâu thì tìm xe càng xa
                  (tối đa 5 km)                          # 0 phút: 2,5 km; 1 phút: 3,5 km; từ 2,5 phút: 5 km

# Sau khi tính chi_phí cho MỌI cặp (xe rảnh × khách đang chờ), thuật toán Hungarian
# chọn cách ghép sao cho TỔNG chi phí của tất cả các cặp là nhỏ nhất.
# Mỗi xe nhận tối đa 1 khách, mỗi khách nhận tối đa 1 xe.
```

**Ví dụ.** Khách J đã chờ 2 phút, nên bán kính tìm xe là 2,5 + 2 = 4,5 km. Có hai xe rảnh:

| | Xe A | Xe B |
|---|---|---|
| (1) Quãng đường đón | 1,5 km | 3,0 km |
| ETA (tốc độ 22 km/h) | 4,1 phút | 8,2 phút |
| (2) 5 × rủi ro huỷ | 5 × 18,5% = **+0,93** | 5 × 33,6% = **+1,68** |
| (3) 0,2 × 2 phút khách chờ | **−0,40** | **−0,40** |
| (4) 0,1 × phút tài xế rảnh | rảnh 10 phút: **−1,00** | vừa rảnh: **0** |
| **Tổng chi phí** | **1,03** | **4,28** |

Xe A có chi phí thấp hơn nên được ưu tiên ghép với khách J: vừa ở gần hơn, vừa là tài xế đã chờ cuốc lâu hơn.

**Ý nghĩa từng thành phần:**
- **(1) Quãng đường đón:** yếu tố chính ("cost hội tụ distance" theo mentor). Xe càng gần thì càng ít km chạy rỗng và khách chờ càng ít.
- **(2) Rủi ro huỷ:** ứng với phần "cancellation" trong mô tả của mentor. Phạt nặng những xe tới chậm, vì nếu khách huỷ thì xe đã chạy rỗng một đoạn vô ích.
- **(3) Khách đã chờ:** giống nhau cho mọi xe khi xét cùng một khách, nên không quyết định *xe nào* đón khách đó. Nó quyết định *khách nào được phục vụ trước* khi thiếu xe.
- **(4) Tài xế đã rảnh:** giúp chia cuốc đều hơn giữa các tài xế.
- **Pin không xuất hiện ở bất kỳ thành phần nào.** Đây là điểm B3 (battery-aware) sẽ bổ sung.

Các phần sau cũng là giả định mô phỏng, vì chưa biết GSM có hay không:
- Tài xế được từ chối cuốc (xem mục 3.4).
- Trong giờ cuối của ca (chế độ về nhà), hệ thống chỉ gửi những chuyến đưa tài xế lại gần nhà.

### B2 – B1 + forward dispatch + repositioning (`gsm_fwd_repo`)

Hai tính năng phổ biến ở các nền tảng gọi xe; **chưa rõ GSM có dùng hay không** [Mô phỏng]:
- **Forward dispatch:** ghép thêm những xe sẽ trả khách trong vòng 5 phút. Cost cộng thêm thời gian chờ xe trả khách xong. Kết quả ghép này là tạm thời: mỗi lượt được tính lại, nếu có xe rảnh tốt hơn thì chuyển cho xe đó.
- **Repositioning:** cứ 5 phút, xe rảnh quá 5 phút ở vùng thừa xe được gợi ý chuyển tới vùng dự báo thiếu xe trong 30 phút tới. Tài xế làm theo với xác suất `0,7 × exp(−km/8)`. Nếu từ chối thì 15 phút sau mới được gợi ý lại.

Cả B1 và B2 đều **không dùng pin khi ghép**. Pin chỉ ảnh hưởng qua hành vi của tài xế: tự đi sạc, hoặc từ chối cuốc khi pin yếu.

## 3. Tham số và nguồn

### 3.1 Xe và năng lượng

| Tham số | Giá trị | Nguồn |
|---|---|---|
| Dung lượng pin khả dụng VF5 | 37,23 kWh | [Nguồn thứ cấp 10] |
| Tiêu thụ công bố | 13 kWh/100 km (quãng đường NEDC 326,4 km) | [Nguồn thứ cấp 10] |
| Tiêu thụ dùng trong mô phỏng | **16 kWh/100 km** (cộng thêm điều hoà, kẹt xe) | [Mô phỏng] |
| Công suất sạc tối đa của xe | DC 50 kW, AC 6,6 kW; sạc 10→70% khoảng 33 phút | [Nguồn thứ cấp 10] |
| Công suất sạc hiệu dụng (trạm không có dữ liệu) | 40 kW dưới 80% SOC, 15 kW trên 80% | [Mô phỏng]. Mức 40 kW khớp với "10→70% trong 33 phút" của nguồn 10 (≈ 22 kWh / 33 phút). |
| Hiệu suất sạc | 90% | [Mô phỏng] |
| SOC ban đầu (khi không sạc đêm) | phân phối chuẩn cắt trong [0, 1], trung bình 0,6, độ lệch 0,2 | [Mô phỏng] |

**Lưu ý:** bản chạy trong mục 5 dùng trần sạc của xe là 60 kW DC và 7,4 kW AC, vì con số spec (50 / 6,6 kW) được cập nhật sau khi bản chạy đã bắt đầu. Trần này chỉ áp dụng cho 19/248 trạm có công suất thật từ Google, nên ảnh hưởng tới kết quả rất nhỏ. Config hiện đã dùng 50 / 6,6 kW.

### 3.2 Trạm sạc

| Tham số | Giá trị | Nguồn |
|---|---|---|
| Vị trí trạm | 248 trạm cho ô tô trong vùng mô phỏng (480 trạm trên toàn Hà Nội) | [Nguồn 12] Google Places API, lấy ngày 30/09/2026 |
| Số cổng: trạm có dữ liệu Google | theo Google (28/480 trạm) | [Nguồn 12] |
| Số cổng: các trạm còn lại | ước lượng theo loại trạm: hub 20–40, TTTM/chung cư 8–16, trạm nhỏ 2–6. Nếu không nhận ra loại thì theo vùng: trong Vành đai 3 là 6–8, ngoài là 15–25. Tổng 3.315 cổng trong vùng. | [Nhóm cung cấp] phân loại quy mô trạm; [Mô phỏng] cách nhận diện bằng từ khoá và xấp xỉ Vành đai 3 bằng bán kính 7,5 km |
| Công suất trạm có dữ liệu | DC: min(công suất trạm, trần của xe) × 0,8; AC: min(công suất trạm, trần của xe) | [Nguồn 12] + [Mô phỏng] |
| Tỷ lệ cổng bị xe cá nhân chiếm | 20–60% tuỳ giờ | [Mô phỏng] |
| Giá điện | 3.858 đ/kWh (áp dụng từ 19/03/2024) | [Nguồn 9] |
| Sạc siêu nhanh (từ 250 kW) | V-Green giới hạn SOC ở 80% | [Nguồn 9] (không ảnh hưởng VF5) |
| Chính sách sạc cho tài xế | miễn phí sạc đêm, giảm 50% sạc ngày | [Nguồn 6, 7] |

### 3.3 Tài xế và ca làm việc

| Tham số | Giá trị | Nguồn |
|---|---|---|
| Giới hạn lái xe | tối đa 10 giờ/ngày, lái liên tục không quá 4 giờ | [Nhóm cung cấp] (quy định nội bộ) |
| Thời gian online | 11–13 giờ/ngày; mất 1,5–2,5 giờ cho sạc, chờ cuốc, rửa xe | [Nhóm cung cấp] |
| Cơ cấu ca | 70% ca ngày (~6h→19h, 13 giờ), 10% ca muộn (~10h→22h), 20% ca đêm (~19h→7h30) | [Mô phỏng], hiệu chỉnh theo mục tiêu γ(t) [Nhóm cung cấp] |
| Nghỉ | nghỉ ăn 45 phút (khoảng 10–13h), nghỉ/rửa xe 40 phút (khoảng 14–16h), nghỉ 30 phút khi gần chạm giới hạn 4 giờ | [Mô phỏng] |
| Ngưỡng tự đi sạc | 8–25% SOC, khác nhau giữa các tài xế | [Mô phỏng] |
| Mức rút sạc ở trạm công cộng | 90% tài xế dừng ở một mức riêng trong khoảng 60–80%; 10% sạc lên 80–100%. Sạc qua đêm vẫn sạc đầy. | [Nhóm cung cấp] (quyết định của nhóm ngày 03/10/2026); con số cụ thể chờ dữ liệu phiên sạc của GSM |
| Sạc trong giờ nghỉ ăn | khi pin dưới 60% | [Mô phỏng] |
| Tỷ lệ tài xế sạc qua đêm | 50% | [Mô phỏng] |
| Chọn trạm | trong 5 trạm gần nhất, chọn trạm có tổng (đường đi + chờ + sạc) nhỏ nhất | [Mô phỏng] |
| Số tài xế mỗi xe | 1 | [Mô phỏng]. Cần hỏi GSM có dùng 2 tài xế/xe theo ca không. |

So sánh tỷ lệ xe trên đường theo giờ, γ(t), giữa mục tiêu và mô phỏng:

| Khung giờ | Mục tiêu [Nhóm cung cấp] | Mô phỏng |
|---|---|---|
| 7–9h | 75–85% | 72% |
| 9h30–16h30 | 50–60% | 62% |
| 17–19h | 75–85% | 71% |
| 23–5h | 15–20% | 14% |

### 3.4 Hành vi tài xế khi nhận cuốc

| Tham số | Giá trị | Nguồn |
|---|---|---|
| Từ chối vì lý do khác | 5%, cộng 3% cho mỗi km đón vượt quá 3 km | [Mô phỏng] |
| Từ chối vì pin | `sigmoid((ngưỡng + 0,05 − SOC_sau_chuyến) / 0,02)`; tài xế từ chối thì đi sạc luôn | [Mô phỏng] |
| Thời gian bấm nhận cuốc | trung bình 8 giây | [Mô phỏng] |
| Tài xế thấy điểm đến trước khi nhận | có | [Mô phỏng] |

### 3.5 Nhu cầu và khách hàng

| Tham số | Giá trị | Nguồn |
|---|---|---|
| Phân bố không gian | 8 điểm nóng nội thành (Hoàn Kiếm, Ba Đình, Đống Đa, Cầu Giấy, Hai Bà Trưng, Thanh Xuân, Tây Hồ, Long Biên) + 3% chuyến sân bay | [Mô phỏng] |
| Phân bố theo giờ | hai cao điểm 7–9h và 17–19h | [Mô phỏng] |
| Độ kiên nhẫn của khách | phân phối mũ, trung bình 20 phút | [Mô phỏng] |
| Huỷ sớm vì lý do khác (sai địa chỉ, đổi ý) | 5% | [Mô phỏng] |
| Đặt lại sau khi huỷ | 50–60%, tối đa 3 lần, lần sau kém kiên nhẫn hơn (×0,7) | [Mô phỏng] |
| Phí huỷ | không có | [Nguồn 4]: website không nêu phí huỷ cho ô tô; khách được huỷ khi chuyến chưa bắt đầu |
| Tốc độ di chuyển | 15 km/h giờ cao điểm, 22 km/h ban ngày, 32 km/h ban đêm | [Mô phỏng] |
| Quãng đường | đường ngắn nhất trên mạng đường OSM giữa các ô lưới ~1,1 km | [Nguồn 11]. Tỷ lệ so với đường chim bay có trung vị 1,32. |

### 3.6 Kinh tế

| Tham số | Giá trị | Nguồn |
|---|---|---|
| Cước Green SM Car Hà Nội | 30.500 đ (2 km đầu); 14.700 đ/km (km 3–12); 13.800 đ/km (km 13–25); 11.900 đ/km (từ km 26). Đã gồm VAT và bảo hiểm hành khách. | [Nguồn 1] |
| Phụ phí đêm 22:00–06:00 | +20.000 đ/chuyến | [Nguồn 1] |
| Giờ chờ, thêm/đổi điểm đến | 60.000 đ/giờ; 10.000 đ/điểm (**chưa mô phỏng**) | [Nguồn 1] |
| Chuyến sân bay | 189.000 đ cho tối đa 20 km, sau đó 9.500 đ/km | [Nguồn 2] |
| Phụ phí giờ cao điểm cho Car | không có số công bố ("phụ thu nếu có, tại từng thời điểm"); **chưa mô phỏng** | [Nguồn 1] |
| Lương cứng tài xế | 5.310.000 đ/tháng (trang ghi "tới 5.310.000") | [Nguồn 6] |
| Hoa hồng tài xế | 25% doanh thu ("chưa bao gồm hoa hồng lên đến 25% tổng doanh thu") | [Nguồn 3] |
| Kiểm tra chéo thu nhập tài xế | công bố: đảm bảo 15–18 triệu/tháng, tối đa 25 triệu. Mô phỏng: 20,7–21,0 triệu/tháng. | [Nguồn 6, 7] |
| Mô hình chia 60–62% doanh thu (dùng cho phân tích độ nhạy) | "chia sẻ doanh số lên đến 60% / 62%" | [Nguồn 6, 7]. Không khớp thu nhập công bố: nếu chia 62% thì tài xế nhận ~34 triệu/tháng. |
| Bảo dưỡng định kỳ | công ty trả | [Nguồn 3] |
| Chi phí khác/km (lốp, khấu hao, bảo hiểm) | 0 đ | [Mô phỏng]. Chưa có số công khai. |
| Phí cứu hộ khi xe hết pin | 800.000 đ/lần | [Mô phỏng] |

**Công thức lợi nhuận** (góc nhìn GSM):

```
Lợi nhuận = Cước các chuyến đã phục vụ
          − 25% hoa hồng tài xế − lương cứng (5,31 triệu / 30 ngày / tài xế)
          − Tiền điện (kWh sạc trạm + sạc đêm) × 3.858 đ
          − Chi phí khác/km − Phí cứu hộ
```

Con số này **chưa trừ khấu hao hoặc tiền thuê xe, bảo hiểm, VAT và chi phí quản lý**. Vì vậy nó chỉ dùng để **so sánh giữa các policy**, không phải lợi nhuận thật của GSM.

## 4. Metric đánh giá

Toàn bộ metric là do nhóm tự chọn [Mô phỏng]. Chưa có thông tin GSM dùng metric nào; câu hỏi này đã nằm trong danh sách gửi mentor.

- **Service level:** % hành trình cuối cùng được phục vụ. Một hành trình có thể gồm nhiều lần đặt nếu khách huỷ rồi đặt lại.
- **Thời gian chờ đón:** tính từ lần đặt **đầu tiên** tới lúc xe tới (trung bình, P90, riêng giờ cao điểm).
- **Tỷ lệ từ chối cuốc:** tổng, và phần do pin.
- **Km rỗng:** tỷ lệ km rỗng, và km rỗng lãng phí do khách huỷ sau khi đã gán xe.
- **Sạc:** thời gian chờ ở trạm, % xe đang sạc giờ cao điểm, số lần xe hết pin giữa đường.
- **Tài xế:** utilization (% thời gian online có khách), thu nhập tài xế.
- **Tiền:** doanh thu bị mất, lợi nhuận/xe/ngày.

## 5. Kết quả: kịch bản `hanoi_full`

5.080 xe, 118.533 lượt đặt/ngày, 3 ngày, 5 seed (0–4), trung bình ± độ lệch chuẩn. Mã lần chạy `20261003-210943_hanoi_full`: tra từng seed trong `outputs/runs/index.csv` và `outputs/runs/20261003-210943_hanoi_full/`. Toàn bộ số liệu trong mục này là **[Mô phỏng]**.

| Metric | B1: GSM hiện tại | B2: + Forward + Repo | Chênh lệch |
|---|---|---|---|
| Service level | 82,2% ± 0,2 | **83,1%** ± 0,2 | +0,9 điểm |
| Service level giờ cao điểm | 78,3% ± 0,3 | **80,5%** ± 0,5 | +2,2 điểm |
| Chờ đón trung bình / P90 (phút) | 5,74 / 16,1 | **5,51 / 15,5** | −0,2 / −0,6 |
| Chờ đón giờ cao điểm (phút) | 7,55 | **6,98** | −0,6 |
| Khách đặt lại / ngày | 21.409 | 21.111 | −1,4% |
| Khách huỷ sau khi gán / khi chưa gán | 8,8% / 21,4% | 12,5% / 16,8% | |
| Tỷ lệ tài xế từ chối cuốc | 7,2% | 11,7% | +4,5 điểm |
| **Phần từ chối do pin** | **31,7%** | **59,8%** | **gần gấp đôi** |
| Tỷ lệ km rỗng | 8,9% | 8,2% | |
| Km rỗng lãng phí do khách huỷ / ngày | 6.172 | 5.180 | −16% |
| Tỷ lệ gợi ý reposition được làm theo | — | 31,5% | |
| Mức SOC lúc rút sạc / thời gian một lần sạc | 70,9% / 21,4 phút | 71,0% / 21,6 phút | |
| Chờ ở trạm sạc (phút) | 2,4 | 2,2 | |
| % xe đang sạc giờ cao điểm | 3,7% | 3,0% | |
| Số lần xe hết pin / ngày (toàn đội) | 0,27 | 0,33 | |
| Utilization | 54,5% | 55,4% | +0,9 điểm |
| Thu nhập tài xế (triệu đ/tháng) | 20,9 | 21,1 | +0,9% |
| Doanh thu cước / ngày | 10,57 tỷ | 10,70 tỷ | +1,2% |
| Doanh thu bị mất / ngày | 2,37 tỷ | 2,24 tỷ | −130 triệu |
| Tiền điện / ngày | 547 triệu | 546 triệu | ≈ 0 |
| **Lợi nhuận / xe / ngày** | **1,275 triệu** | **1,295 triệu** | **+1,5%** (~100 triệu/ngày toàn đội) |

Thời gian online trung bình 13,0 giờ/tài xế/ngày, thời gian lái 7,8–7,9 giờ, thời gian đi sạc và sạc khoảng 0,5 giờ.

### Nhận xét

1. **B2 tốt hơn B1 ở mọi metric chính, nhưng mức cải thiện nhỏ** (+0,9 điểm service level, +1,5% lợi nhuận). Độ lệch chuẩn giữa các seed rất nhỏ, nên chênh lệch này là có thật, không phải nhiễu ngẫu nhiên.
2. **Bằng chứng chính cho battery-aware:** ở B2, **60% số lượt tài xế từ chối cuốc là vì pin**, gần gấp đôi B1. Forward dispatch không biết pin nên nối chuyến cho xe sắp cạn pin; tài xế từ chối và khách phải chờ thêm một lượt ghép.
3. **Xe gần như không hết pin giữa đường** (0,3 lần/ngày trên 5.080 xe), vì tài xế tự tính pin khi nhận cuốc. Lợi ích của battery-aware vì vậy phải đến từ việc giảm số lần từ chối và sạc đúng thời điểm, không phải từ việc tránh xe hết pin.
4. **Khách huỷ vì chưa được ghép xe (17–21%) là khoản mất lớn nhất**, khoảng 2,2–2,4 tỷ cước/ngày.
5. **Tiền điện gần như không đổi giữa các policy** (khoảng 5% doanh thu), nên lợi nhuận đến từ việc phục vụ thêm khách, không đến từ tiết kiệm điện.

## 6. Độ nhạy và hạn chế

- **Thói quen sạc của tài xế.** So với giả định cũ "luôn sạc đầy 100%" (bản chạy ngày 30/09): thời gian chờ trạm giảm từ 10,6 xuống 2,4 phút và service level của B1 tăng từ 81,4% lên 82,2%. Đổi lại, xe chạy ở mức pin thấp hơn nên phần từ chối cuốc do pin tăng (B1: 23,6% → 31,7%; B2: 47,6% → 59,8%). Thứ hạng B1 < B2 không đổi.
- **Số cổng sạc là giả định quan trọng nhất.** Chạy thử 2 ngày với B1: 977 cổng cho service level 71% và thời gian chờ trạm 224 phút; 3.315 cổng cho service level 82% và thời gian chờ trạm khoảng 20 phút.
- **Quy mô đội xe ảnh hưởng mạnh.** Cùng tỷ lệ xe/khách, 300 xe cho service level 73%, còn 1.000 xe cho 79%. Đội xe nhỏ làm kết quả bi quan hơn.
- **Nhu cầu là dữ liệu tổng hợp**, chưa có log chuyến đi thật của GSM.
- **Chưa mô phỏng:** 2 tài xế dùng chung 1 xe, depot sạc riêng của GSM, khách vẫy xe ngoài đường, hàng đợi FIFO ở sân bay, phụ phí giờ cao điểm, khuyến mãi, xe máy.
- **Trạm sạc Google:** tên trạm sạc xe máy và ô tô VinFast trùng nhau, nên có thể đã lẫn trạm xe máy vào danh sách trạm ô tô.

## 7. Chạy lại

```
.venv/Scripts/python run_baseline.py --scenario hanoi_full --seeds 5 --jobs 5 --policies gsm_baseline gsm_fwd_repo
```

- Kết quả được ghi vào `outputs/hanoi_full/comparison.csv`.
- Chạy thử thì thêm `--tag test` để không ghi đè kết quả chính thức.
- Khoảng 35 phút trên máy 8 nhân.
- Tham số nằm trong `evsim/config.py`, kịch bản `SCENARIOS["hanoi_full"]`.

## 8. Nguồn

Các nguồn 1–9 được truy cập và đối chiếu ngày 30/09/2026. Bảng giá được đọc trực tiếp từ dữ liệu gốc của trang.

1. Green SM – Green SM Car, bảng giá theo tỉnh/thành và phụ phí: https://www.greensm.com/vn-vi/greensm-car
2. Green SM – Green Airport, giá trọn gói sân bay: https://www.greensm.com/vn-vi/green-airport
3. Green SM – Tài xế ô tô, FAQ lương cố định, hoa hồng 25%, bảo dưỡng: https://www.greensm.com/vn-vi/driver-car
4. Green SM – Trung tâm hỗ trợ, huỷ chuyến: https://www.greensm.com/vn-vi/helps
5. Green SM – Giới thiệu (5 thị trường, 80.000+ nhân sự): https://www.greensm.com/vn-vi/about
6. Green SM – Tuyển tài xế taxi (lương cứng tới 5.310.000 đ, chia sẻ tới 60%, đảm bảo 15–18 triệu/tháng, miễn phí sạc đêm): https://tuyentaixe.greensm.com/taxi
7. Green SM – Tuyển tài xế ô tô (chia sẻ tới 62%, thu nhập tới 25 triệu/tháng): https://tuyentaixe.greensm.com/oto
8. Green SM – Thuê xe (chia sẻ 85%): https://tuyentaixe.greensm.com/thuexe
9. V-Green – Chính sách sạc pin (3.858 đ/kWh từ 19/03/2024, phí chiếm chỗ, giới hạn 80% với trụ từ 250 kW): https://vgreen.net/vi/san-pham-dich-vu
10. Thông số VF5 (nguồn thứ cấp; trang chính thức của VinFast chặn truy cập tự động): https://tinbanxe.vn/oto/vinfast/vf5/ , https://vinfastvietnam.com.vn/vinfast-vf-5/
11. OpenStreetMap contributors, mạng đường bộ Hà Nội, giấy phép ODbL, tải bằng osmnx.
12. Google Places API (New), Text Search, loại `electric_vehicle_charging_station`, lấy ngày 30/09/2026 (`data/stations_google.csv`).
13. VTC News, "Cứ 1 giây, có 11 chuyến xe công nghệ sạch Xanh SM lăn bánh" (1 triệu chuyến/ngày). Nhóm cung cấp; chưa đối chiếu bài gốc.
