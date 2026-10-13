# Bộ theo dõi hành vi tài xế (driver behaviour tracker): thiết kế

*Bản nháp 2026-10-11, ý tưởng của nhóm. Mọi số liệu là mô phỏng.*

## 0. Mục tiêu

Học thói quen dùng pin của **từng** tài xế từ dữ liệu nền tảng quan sát được, rồi dùng dự báo đó để:

- ghép cuốc phù hợp với thói quen pin của tài xế;
- nhắc sạc đúng người, đúng lúc;
- tăng lợi nhuận mà không làm kém luật dispatch gốc.

Hệ có hai pha:

- **Pha 1, theo dõi (shadow):** mô hình dự báo và được chấm điểm, nhưng chưa được dùng để ra quyết định.
- **Pha 2, điều phối:** dự báo được dùng thật, kèm cơ chế tự quay về pha 1 khi dự báo kém đi.

Câu hỏi nghiên cứu:

1. **Trần lợi ích:** nếu biết hoàn hảo thói quen từng tài xế (oracle) thì hơn mô hình chung của cả đội xe (pooled) bao nhiêu?
2. **Tốc độ học:** cần bao nhiêu ngày quan sát để thu hẹp được bao nhiêu phần của khoảng cách đó (đường cong học)?
3. **Độ bền:** khi hành vi đổi, khi có tài xế mới, khi mô hình sai dạng, hệ có còn không kém luật gốc không?

## 1. Dữ liệu quan sát được

Bộ theo dõi chỉ được dùng thứ nền tảng thật sự thấy, **không** đọc tham số ẩn của tài xế trong mô phỏng.

| Sự kiện | Trường dữ liệu |
|---|---|
| Mời cuốc | thời điểm; SOC lúc mời; SOC sau chuyến (ước tính); km đón; km chở; điểm đến; thời gian còn lại của ca; giá cuốc; **nhận / từ chối** |
| Tài xế tự đi sạc | thời điểm, SOC lúc rời khỏi trạng thái rảnh để đi sạc. Telemetry thấy xe đi tới trạm và cắm sạc |
| Rảnh mà không đi sạc | SOC lúc rảnh (quan sát bị kiểm duyệt: tài xế *chưa* muốn sạc ở mức SOC này) |
| Phiên sạc | trạm; SOC lúc cắm; **SOC lúc rút**; thời gian chờ; có phải do nhắc hay không |
| Nhắc sạc | thời điểm, SOC, khoảng cách tới trạm trống, **có làm theo trong X phút hay không** |
| Ca làm | giờ online/offline, giờ nghỉ, SOC cuối ca, SOC đầu ca hôm sau (để suy ra có sạc qua đêm) |
| Vận hành | km chạy theo giờ, tức tốc độ tiêu hao SOC của từng tài xế theo giờ trong ngày |

Lượng dữ liệu (B1, quy mô thật): mỗi tài xế mỗi ngày có khoảng **23 lần được mời cuốc, 1,7 lần từ chối (0,5 lần do pin), 1,1 lần sạc**. Dữ liệu cá nhân thưa, nên bắt buộc phải mượn sức mạnh của cả đội xe (mô hình phân tầng).

## 2. Các mô hình con

Ý chính: mỗi tài xế có một **ngưỡng pin cá nhân θ_i** (biến ẩn). Ngưỡng này giải thích **đồng thời** hai hành vi:

- khi nào tài xế tự đi sạc (M1);
- khi nào tài xế từ chối cuốc vì pin (M3).

Hai nguồn dữ liệu cùng góp vào một posterior của θ_i, nên học nhanh hơn và nhất quán hơn so với học hai mô hình rời.

| | Dự báo | Dạng mô hình | Cập nhật |
|---|---|---|---|
| **M1** tự đi sạc | P(đi sạc ngay \| SOC, giờ, thời gian còn của ca) | Ngưỡng θ_i với xác suất "trượt" ε (cho phép nhiễu): đi sạc khi SOC < θ_i. Quan sát "rảnh ở SOC s mà không đi sạc" cho biết θ_i ≤ s (kiểm duyệt). | **Posterior trên lưới** θ ∈ [0, 40%], 81 điểm; nhân likelihood sau mỗi sự kiện. Rẻ, có độ bất định rõ ràng, xử lý được kiểm duyệt. |
| **M2** rút sạc, sạc đêm | Mức rút τ_i; xác suất sạc qua đêm π_i | τ_i ~ Normal (mean riêng, phương sai chung); π_i ~ Beta-Bernoulli | Liên hợp (Normal-Normal, Beta-Binomial) |
| **M3** từ chối cuốc | P(từ chối \| SOC sau chuyến, km đón, km chở, giờ, thời gian còn của ca) | Logistic: σ((θ_i + m − SOC_sau)/s) cho phần do pin + β·max(0, km đón − 3) + … cho phần khác. **Dùng chung θ_i với M1.** | θ_i: cập nhật cùng lưới với M1. m, s, β: hồi quy gộp toàn đội xe, fit lại hằng ngày. |
| **M4** làm theo nhắc sạc | P(làm theo \| SOC, khoảng cách tới trạm trống, chờ dự kiến, thời gian còn của ca) | Bản đầu: Beta-Binomial riêng mỗi tài xế. Bản sau: logistic với hệ số chặn riêng. | Liên hợp, hoặc cập nhật online |
| **M5** tiêu hao, ca | Tốc độ tiêu hao SOC/giờ r_i(h); giờ kết thúc ca; vị trí nhà | Trung bình trượt theo giờ trong ngày, có co về trung bình đội xe | Trung bình mũ |

**Phân tầng (empirical Bayes):**

- Prior của từng tài xế là phân phối của cả đội xe, ước lượng lại hằng ngày từ posterior của mọi tài xế.
- Tài xế mới bắt đầu bằng prior của đội xe, nên không có "giai đoạn chết".
- Dữ liệu cá nhân càng nhiều thì posterior càng lệch khỏi prior về phía hành vi thật.

**Quên dần:** bằng chứng cũ được giảm trọng số với half-life 14 ngày, để theo kịp thói quen thay đổi.

## 3. "Theo dõi đúng": cổng chuyển pha theo từng tài xế và từng mô hình con

Việc chuyển pha **không** áp dụng cho cả đội xe cùng lúc. Mỗi cặp (tài xế, mô hình con) có một trạng thái riêng:

```
S0 Shadow ──(đủ điều kiện)──▶ S1 Trusted ──(drift)──▶ S2 Degraded ──(học lại xong)──▶ S1
   dùng mô hình chung          dùng mô hình riêng       quay về mô hình chung,
   + vẫn log, vẫn chấm điểm                             tăng tốc độ quên
```

**Chấm điểm theo kiểu prequential** (dự báo trước, quan sát sau, rồi mới cập nhật). Đây chính là định nghĩa chính xác của "dự đoán đúng hành vi tiếp theo".

**Điều kiện S0 → S1**, phải đạt cả bốn:

1. **Đủ dữ liệu:** ít nhất n_min sự kiện, ví dụ 20 lần mời cuốc khi SOC sau chuyến < 35%, hoặc 5 lần tự đi sạc.
2. **Đủ chắc:** khoảng tin cậy 80% của θ_i hẹp hơn 5 điểm SOC.
3. **Tốt hơn mô hình chung:** tổng log-likelihood ratio của mô hình riêng so với mô hình chung trên K sự kiện gần nhất vượt ngưỡng A, theo kiểu kiểm định tuần tự SPRT.
4. **Hiệu chuẩn tốt:** ECE (expected calibration error) < 0,05 trên các sự kiện gần đây.

**Điều kiện S1 → S2:** kiểm định Page-Hinkley (hoặc CUSUM) trên chênh lệch log-loss giữa hai mô hình báo động. Khi đó quay về mô hình chung và học lại với tốc độ quên cao hơn.

**Khám phá và đo liên tục:**

- Một tỷ lệ nhỏ quyết định, ví dụ 5% số batch hoặc tài xế, vẫn dùng hành động của mô hình chung. Xác suất của từng quyết định được log lại.
- Mục đích thứ nhất: tránh việc mô hình "mù" ở vùng nó tự né. Ví dụ, khi không còn mời tài xế pin thấp nhận cuốc xa, mô hình không bao giờ thấy họ từ chối hay không nữa.
- Mục đích thứ hai: có sẵn một nhóm đối chứng A/B liên tục khi triển khai thật.

## 4. Điều phối: dùng dự báo ở pha 2

Ánh xạ vào các thành phần của framework (`docs/framework_spec.md`):

### 4.1 Trong ghép cuốc (G)

- **(b) rủi ro từ chối cá nhân:** q_ij = P̂_i(từ chối \| SOC sau chuyến_ij, …) − P̂_i(từ chối \| pin cao). Lấy trung bình theo posterior của θ_i, không chỉ dùng giá trị trung bình.
- **(d) thưởng trả khách gần trạm cá nhân:** trọng số = P̂_i(SOC sau chuyến < θ_i), tức xác suất tài xế sẽ **tự đi sạc ngay sau khi trả khách**. Chỉ khi đó điểm trả gần trạm còn cổng trống mới có giá trị.
- **Forward dispatch:** không giao trước cuốc cho xe mà mô hình dự báo sẽ đi sạc sau chuyến hiện tại.
- **(a) giữ nguyên là ràng buộc vật lý.** Mô hình hành vi **không bao giờ được dùng để nới** ràng buộc an toàn.

### 4.2 Trong hành động sạc (c): nhắc sạc thông minh

1. **Dự báo thời điểm tự sạc:** t̂_i = thời điểm SOC_i − r_i(h)·Δt chạm θ̂_i.
2. **Chỉ nhắc khi có lợi:** nếu t̂_i rơi vào giờ cao điểm sắp tới, và phiên sạc tới mức τ̂_i (M2) xong trước khi cao điểm bắt đầu (cộng thời gian chạy tới trạm và thời gian chờ dự kiến), thì nhắc **ngay bây giờ**. Xe sẽ tự sạc sau cao điểm thì để yên.
3. **Ưu tiên người hay nghe:** sắp xếp theo P̂_i(làm theo) × lợi ích. Giới hạn số lần nhắc mỗi tài xế mỗi ngày để tránh làm phiền.
4. **Không làm tắc trạm:** dự báo tải của mỗi trạm = số xe được nhắc + **số xe mà M1 dự báo sẽ tự tới**. Không nhắc vượt số cổng trống dự kiến.

### 4.3 Bộ lập lịch sạc cuộn (bản nâng cao, cần L2/L3)

Mỗi 5 phút, với mỗi xe rảnh i:

```
Lợi ích_i = P̂_i(làm theo) × [mất nguồn cung giờ cao điểm tránh được nếu không sạc trong cao điểm]
          − [giá trị của xe trên đường lúc này]   ← từ V (L3) hoặc tỷ lệ cầu/cung theo vùng (L2)
          − [chi phí chờ sạc dự kiến]             ← từ dự báo tải trạm
```

Sau đó chọn tập xe có lợi ích dương, với ràng buộc số cổng trống. Có thể giải bằng greedy hoặc Hungarian xe → khung giờ sạc. Tài xế vẫn tự chọn trạm.

### 4.4 Rào chắn

- Fallback về mô hình chung bất cứ khi nào có drift hoặc thiếu dữ liệu.
- Không dùng mô hình để nới ràng buộc an toàn.
- **Công bằng:** không tài xế nào bị giảm quá X% số cuốc tốt chỉ vì bị dự báo là "hay từ chối". Theo dõi `driver_earn_cv` và thu nhập của nhóm tài xế hay từ chối.

## 5. Đánh giá trong mô phỏng

### 5.1 Trần lợi ích: oracle (batch dev3, đã code)

Chế độ `driver_model`:

- **legacy:** đường cong chung, quy tắc cố định (module v1).
- **pooled:** chỉ biết phân phối θ của đội xe.
- **oracle:** biết θ_i thật và luật từ chối thật của từng người.

Chế độ `nudge_mode=smart` (mục 4.2, bước 1–2 với θ đã biết):

- **oracle − pooled** = trần giá trị của bộ theo dõi.
- **pooled − legacy** = giá trị của việc dùng đúng dạng mô hình.

### 5.2 Làm hành vi tài xế "người" hơn

Tài xế mô phỏng hiện theo công thức, nên học lại quá dễ và lợi ích sẽ bị thổi phồng. Cần thêm:

- nhiễu theo từng lần ra quyết định;
- ngưỡng thay đổi theo giờ, theo độ mệt, theo thời gian còn của ca;
- mức rút sạc dao động;
- **mức làm theo nhắc sạc khác nhau giữa các tài xế** (Beta, phụ thuộc khoảng cách và thời gian chờ);
- thói quen sạc đêm khác nhau.

### 5.3 Thử nghiệm độ bền

- **Drift:** giữa kỳ, 20% tài xế đổi ngưỡng.
- **Tài xế mới:** 10% đội xe thay mới mỗi tuần.
- **Mô hình sai dạng:** luật thật khác dạng logistic.
- **Tuân thủ thấp.**

### 5.4 Chạy nhiều ngày

- 21 ngày liên tục với cùng tài xế: 14 ngày học (pha 1 ở đầu, chuyển dần sang pha 2), 7 ngày cuối để đánh giá.
- Vẽ **đường cong học:** % khoảng cách đóng được = (learned − pooled)/(oracle − pooled), theo số ngày quan sát.
- 1.000 xe × 21 ngày ≈ 7 lần một lượt chạy 72 giờ, nên chạy trên Kaggle.

### 5.5 Chỉ số

- **Dự báo:** log-loss, Brier, ECE (từ chối, làm theo nhắc sạc); MAE của θ_i; sai số thời điểm tự sạc.
- **Vận hành:** service level, service giờ cao điểm, lợi nhuận đã điều chỉnh, % xe sạc trong giờ cao điểm, hàng chờ sạc, số lần hết pin.
- **Công bằng:** độ phân tán thu nhập tài xế.

## 6. Rủi ro

- **Vòng tròn mô phỏng:** đã nêu ở 5.2. Kết luận cuối phải được kiểm chứng bằng log thật của GSM.
- **Vòng phản hồi:** đã nêu ở mục 3 (khám phá ε).
- **Tài xế chiến lược:** tài xế có thể học cách "giả vờ" pin thấp để được cuốc ngắn. Cần theo dõi bất thường.
- **Dữ liệu cá nhân:** tài xế GSM là nhân viên. Việc lập hồ sơ hành vi cần căn cứ pháp lý và sự đồng ý theo quy định bảo vệ dữ liệu cá nhân (Nghị định 13/2023/NĐ-CP và các quy định mới hơn), cần minh bạch mục đích, và chỉ dùng cho tối ưu vận hành.

## 7. Lộ trình và cổng quyết định

| Bước | Việc | Cổng để đi tiếp |
|---|---|---|
| **T0** | Oracle (dev3): legacy / pooled / oracle × 3 thế giới tài xế | oracle − pooled ≥ 0,1 pt service **hoặc** ≥ 2.000 đ/xe/ngày ở ít nhất một thế giới. Nếu không đạt thì dừng cá nhân hoá, giữ pooled. |
| **T1** | Hành vi tài xế "người" hơn (5.2) + log sự kiện quan sát được + chạy nhiều ngày | Chạy lại T0 trên hành vi mới, cổng giữ nguyên |
| **T2** | Xây M1–M5 + chấm điểm prequential, **chỉ ở chế độ shadow** | MAE θ_i < 3 điểm SOC sau 14 ngày; ECE < 0,05 |
| **T3** | Pha 2: cổng S0/S1/S2, dùng dự báo trong (b), (d) và nhắc sạc thông minh | Đường cong học đóng được ≥ 50% khoảng cách oracle − pooled |
| **T4** | Độ bền: drift, tài xế mới, sai dạng, tuân thủ thấp | Không kém hơn luật gốc (biên trong protocol) ở mọi kịch bản |
| **T5** | Gộp vào framework làm khối "Mô hình tài xế", đánh giá cuối theo `docs/protocol.md` | |
