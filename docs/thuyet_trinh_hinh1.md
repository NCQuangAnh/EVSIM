# Kịch bản thuyết trình Figure 1 (khoảng 2 phút)

Hình: `docs/figures/fw_fig1_overview.svg` (chữ tiếng Anh; cũng nằm trong `framework_figures.html`).
Vị trí xe, khách và trạm là toạ độ thật trên Ocean Park 1; quãng đón là quãng đường thật trên mạng đường của mô
phỏng.

## Đọc hình trong 10 giây

- Ba hàng từ trên xuống là ba thời điểm trong một ngày: Round t, 20 phút sau, 17:00 cao điểm.
- Mỗi hàng đọc từ trái sang phải: bản đồ → candidate pairs → dispatch rule (1. battery layer, 2. company
  matcher) → dispatch result.
- Mũi tên xám từ kết quả của hàng trên vòng xuống bản đồ của hàng dưới: kết quả vòng này thành tình huống vòng sau.

## Kịch bản nói

**[Hàng 1, bản đồ]**
"Đây là Ocean Park 1, tia sét là các trạm sạc. Ở vòng ghép t có ba xe: v1 còn 80% pin, v2 30%, v3 chỉ 10%; và
ba khách p1, p2, p3."

**[Hàng 1, candidate pairs]**
"Viết lại dưới dạng cặp: khách bên trái kèm độ dài chuyến (p1 3 km, p2 12 km, p3 2 km), xe bên phải kèm thanh pin.
Mỗi đường xanh nhạt là một cặp có thể ghép."

**[Hàng 1, dispatch rule]**
"Luật điều phối có hai bước. Bước 1 là lớp pin của nhóm: nó tính pin còn lại sau chuyến, tính cả quãng đi đón và
quãng tới trạm sạc. v3 đứng gần p2 nhất, cách 0,9 km, nhưng p2 đi 12 km nên v3 tới trạm chỉ còn khoảng 4%, dưới
mức dự trữ 5%. Lớp pin cấm cặp v3–p2. Bước 2 là bộ ghép của công ty, có ổ khoá vì nhóm không sửa: nó vẫn chọn xe
gần nhất như thường, chỉ là không còn cặp bị cấm để chọn."

**[Hàng 1, dispatch result]**
"Kết quả: đường đỏ có dấu X là cặp bị cấm. v2 còn 30% nhận chuyến 12 km, về còn khoảng 24%; v3 nhận p3, đón cách
1,3 km, chở 2 km, vẫn còn khoảng 9%. Không xe nào cạn pin giữa đường."

**[Mũi tên xuống hàng 2]**
"2,5 giờ sau, 15:30, sắp vào cao điểm chiều. Tài xế tự sạc khi pin xuống ngưỡng riêng của họ, khoảng 8–25%, nên
v1 còn 48% sẽ chưa đi sạc; nhiều khả năng nó chạm ngưỡng đúng giữa giờ cao điểm. Bước 1 của lớp pin lúc này nâng
mức nhắc lên 70% để sạc bù trước cao điểm, nhưng chỉ rút xe khi dư: có ba xe rảnh mà chỉ một khách, dư hai xe,
nên rút tối đa một xe, là xe pin thấp nhất v1. Bước 2 giao khách p1 cho xe gần nhất là v3."

**[Mũi tên xuống hàng 3]**
"Đến 17:00 cao điểm, v1 đã sạc xong, cả đội đều trên mức nhắc của giờ cao điểm (15%), nên lớp pin không làm gì,
bộ ghép ghép như thường và các xe nhận được chuyến dài 9 đến 15 km. Không xe nào phải bỏ giờ cao điểm đi sạc."

**[Kết]**
"Tóm lại, ở mọi vòng luật điều phối luôn là hai bước: lớp pin chen vào trước để cấm cặp làm xe cạn pin hoặc nhắc
xe sạc bù trước cao điểm lúc dư xe, rồi bộ ghép của công ty ghép như cũ. Vì không sửa bộ ghép nên cùng một lớp pin dùng được cho
nhiều bộ ghép. Nhóm thử với 7 bộ ghép và không bộ nào kém đi; trung bình tỉ lệ phục vụ tăng khoảng 0,56 điểm phần
trăm và lợi nhuận tăng khoảng 8.100 đến 8.300 đồng mỗi xe mỗi ngày, lặp lại trên hai bộ seed độc lập."

## Câu hỏi thầy có thể hỏi

| Câu hỏi | Trả lời ngắn |
|---|---|
| v3 đi đón p3 xa 1,3 km thì có đủ pin không? | Có. Đón 1,3 km + chở 2 km = 3,3 km, tốn khoảng 1,4% pin (0,16 kWh/km, pin 37,23 kWh), còn khoảng 8,6%; đi tiếp 0,6 km tới trạm còn khoảng 8,3%, trên mức dự trữ 5%. Lớp pin luôn tính cả quãng đón, quãng chở và quãng tới trạm. |
| Sao không sửa luôn bộ ghép? | Công ty không giao bộ ghép, nên nhóm coi nó là hộp đen. Lớp bọc ngoài chạy được với mọi bộ ghép; nhóm đã thử 7 bộ, gồm greedy, kiểu GSM và kiểu DiDi theo giá trị. |
| Ngoài cấm còn gì? | Phạt nhẹ các cặp có rủi ro tài xế từ chối vì pin (xem Hình 2 và 3). |
| Tài xế ngoài đời tự tắt app đi sạc khi gần hết pin, nhắc sạc có thừa không? | Mô phỏng đã có hành vi này: mỗi tài xế tự đi sạc khi pin xuống ngưỡng riêng (8–25%), có người sạc muộn; kết quả đo là phần cải thiện cộng thêm trên nền đó. Nhắc sạc không nhằm vào xe sắp hết pin mà nhằm đổi thời điểm sạc: sạc bù khi đang dư xe trước cao điểm, để xe không chạm ngưỡng giữa cao điểm. Số đo: tỉ lệ xe đang sạc trong cao điểm giảm 1,5–2,9 điểm, phục vụ giờ cao điểm tăng 0,6–2,2 điểm (eval2). |
| Tài xế còn 48% không muốn sạc, muốn chạy gần hết rồi sạc một thể cuối ca thì sao? Có bị ngừng ghép khách không? | Không bị phạt gì: bỏ qua lời nhắc thì vẫn được ghép như mọi xe, chỉ không bị nhắc lại trong 15 phút. Mặt nạ chỉ chặn đúng những cặp mà chạy xong xe về tới trạm còn dưới 5%; ở 48% (chạy được khoảng 100 km) không chuyến nào bị chặn. Khi pin thấp dần, xe vẫn nhận chuyến ngắn vừa sức; chỉ chuyến chạy xong sẽ kẹt giữa đường mới bị chặn, việc này cũng bảo vệ chính tài xế. Mô phỏng đã có đúng kiểu tài xế này: mức nghe lời mỗi người khác nhau (trung bình 60%, nhiều người gần như không bao giờ nghe), người sắp hết ca trong 1 giờ không bị nhắc, và tài xế được sạc trước khi về nếu không đủ pin về nhà. Kết quả +0,56 điểm đã tính với những tài xế này; thử riêng khi chỉ 30% lời nhắc được nghe vẫn giữ khoảng 2/3 mức lời. |
| Nhắc sạc có ép tài xế không? | Không. Tài xế tự quyết; mô phỏng có xác suất chấp nhận khác nhau cho từng tài xế. |
| Rút xe đi sạc có làm thiếu xe không? | Có cổng dư xe: chỉ rút tối đa 0,5 × (số xe rảnh − số khách chờ). Thiếu xe thì không rút. |
| Số liệu trong hình là thật không? | Vị trí và quãng đường là thật trên bản đồ OCP1; tình huống là ví dụ minh hoạ, tính đúng theo công thức của mô phỏng. Kết quả định lượng nằm ở bảng đánh giá: 20 seed, 7 bộ ghép, hai bộ seed độc lập. |
| Trên OCP1 kết quả thế nào? | Với bộ ghép B1, tỉ lệ phục vụ tăng 0,83 ± 0,24 điểm, lợi nhuận +6.500 đ/xe/ngày; kịch bản khắc nghiệt +0,85 điểm. |
