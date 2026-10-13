## Báo Cáo Kỹ Thuật & Tài Liệu Bàn Giao: Mô Phỏng SoC Đội Xe GreenSM

Phân vùng Vinhomes Ocean Park 1 (OCP1) · V-RIC Team · Bàn giao nhóm Baseline & 3D Simulation · Tháng 10/2026

## 1. Bản chất Input & Output của hệ thống

Hệ thống mô phỏng bài toán điều phối đội xe điện (Electric Vehicle Fleet Dispatching) phục vụ hành khách tại khu đô thị Vinhomes Ocean Park 1 (Gia Lâm, Hà Nội). Quy mô thử nghiệm gồm 60 xe điện VinFast vận hành trong 20 ngày liên tục, chạy trên 7 seed ngẫu nhiên độc lập (tổng cộng 280 ngày mô phỏng, 140 ngày/nhánh).

## 1.1. Dữ liệu đầu vào (Input)

- M¡ng l°Ûi °Ýng: 1.110 nút giao lÙ và 1.517 o¡n °Ýng hai chiÁu (tÕng chiÁu dài tim đường 144,2 km) trích xuất từ OpenStreetMap thực tế (file data/ocp1_graph.json).

- ‑Ùi xe (Fleet): 60 xe ‑iÇn gÓm 2 dòng chç lñc cça VinFast là VF5 (pin kh£ dång 37,23 kWh, tiêu thụ 0,163 kWh/km) và VF e34 (pin khả dụng 42,0 kWh, tiêu thụ 0,184 kWh/km), đo chuẩn theo chu kỳ NEDC/WLTP.

- Dòng nhu c§u (Demand): Trung bình 1.276 cuÑc gÍi m×i ngày, phân bÕ theo quy lu­t 65% cuốc nội khu OCP1 (khoảng cách lognormal trung vị 1,6 km) và 35% cuốc gateway đi trung tâm Hà Nội (khoảng cách lognormal trung vị 10,0 km, mốc cầu Vĩnh Tuy 9,3 km).

- H¡ t§ng tr¡m s¡c: 30 vË trí tr¡m vÛi 156 cÕng s¡c DC chu©n VinFast. Mall/Depot: 12 cổng 60 kW; Cụm căn hộ: 4 cổng 30 kW.

- BiÃu giá & Chi phí: Khung c°Ûc Green SM Car Hà NÙi (mß cía 30.500 – cho 2 km đầu, các bậc 14.700 đ, 13.800 đ, 11.900 đ/km, phụ phí đêm 20.000 đ); giá điện sạc 3.858 đ/kWh; lương cứng tài xế 5,31 tr.đ/tháng và hoa hồng 25%.

- Hành vi & —Ùng lñc hÍc: Khách kiên nh«n theo hàm mi tau = 20 phút (5% hçy sÛm, 55% rebook); hao hụt điều hòa khi xe đỗ chờ 1,2 kW liên tục; phân bổ tài xế 70% ca Ngày, 10% ca Chiều, 20% ca Đêm.

## 1.2. Dữ liệu đầu ra (Output)

- ChÉ sÑ v­n hành: Km ch¡y r×ng (deadhead_km), t÷ lÇ km r×ng (deadhead_fraction), thời gian khách chờ xe đón (pickup_wait_min), thời gian chờ sạc (charger_wait_min), tỷ lệ phục vụ (match_rate), số xe cạn pin dọc đường (stranded_min = 0).


- ChÉ sÑ kinh t¿: Doanh thu c°Ûc m×i ngày (revenue_vnd), chi phí –iÇn n¡p thñc t¿ (energy_vnd), lợi nhuận xe/ngày (profit_per_vehicle_day), chi phí lãng phí do khách hủy cuốc giữa chừng (wasted_km).

- Ùng lñc hÍc pin: Quù ¡o bi¿n thiên SoC trung bình theo giÝ (05h23h), phân bÑ pin mở đầu ngày hôm sau (overnight carryover mean shift).

## 1.3. Bảng đối chiếu kết quả Baseline vs Policy

| Chỉ số vận hành Baseline (F) Policy (F+B) Mức chênh lệch (Δ) (KPI) |
| --- |
| Km chạy rỗng mỗi 1.371,3 ± 4,8 km 1.331,0 ± 4,8 km Giảm 40,3 km/ngày ngày (Deadhead km) (−2,94%) Tỷ lệ km rỗng 17,97% ± 0,04% 17,65% ± 0,04% Giảm 0,32 điểm % (Deadhead fraction) (tiết kiệm rỗng) Tiền điện sạc đội xe 5.902.756 đ 5.835.098 đ Tiết kiệm 67.658 mỗi ngày đ/ngày (−1,15%) Khách hủy trước khi 190,8 đơn/ngày 187,2 đơn/ngày Giảm 3,6 đơn/ngày tài xế nhận (−1,88%) Khách hủy giữa đường 225,5 đơn/ngày 220,0 đơn/ngày Giảm 5,5 đơn/ngày khi xe đang đón (−2,44%) Km lãng phí do hủy 270,6 ± 2,1 km 261,1 ± 2,1 km Giảm 9,5 km/ngày đón (wasted_km) (−3,51%) Lợi nhuận ròng đội xe 94,13 tr.đ/ngày 93,66 tr.đ/ngày Giữ vững 99,5% (Accounting) (phẳng theo trần) Tỷ lệ khớp chuyến 99,78% ± 0,12% 99,72% ± 0,12% Đạt 99,7% (không (Match rate) rớt cuốc) Sự cố cạn pin chết 0 xe (0 phút) 0 xe (0 phút) 0 sự cố (sàn 0,15 bảo đường (Stranded) vệ an toàn) |


*Hình 1: Đối chiếu hiệu quả vận hành giữa Baseline và Policy (Km rỗng, tiền điện, đơn hủy và cự*

*ly lãng phí).*

## 2. Nguồn gốc và phương pháp thu thập dữ liệu

Tất cả các số liệu trong mô phỏng đều có nguồn gốc rõ ràng, được thu thập thông qua các phương pháp kỹ thuật tiêu chuẩn:

## M¡ng l°Ûi giao thông thñc t¿:

Sử dụng OpenStreetMap API v0.6 tải trích xuất dữ liệu thô dạng XML của khu vực OCP1 (bbox 20.9841, 105.9334 đến 21.0048, 105.9629). Kịch bản Python scripts/build_ocp1_graph.py dùng thư viện xml.etree lọc các thẻ highway thuộc mạng lưới có thể chạy xe, loại bỏ đường đi bộ, gộp các chuỗi nút bậc 2 (degree-2 chains) để thu gọn đồ thị từ 4.682 đoạn thô về 1.517 cạnh với chiều dài tính theo công thức haversine.

## Thông sÑ v­n hành dñ án:

Sử dụng python-docx phân tích trực tiếp file tài liệu gốc BASELIND_AND_DATA_REQUEST.docx để lấy 10 bảng tham số: Bảng 3 (đặc tính sạc), Bảng 4 (quy mô trạm sạc), Bảng 5 (ca trực tài xế), Bảng 6 (tốc độ và nhu cầu), Bảng 7 (cước phí và lương), Bảng 8 (phương trình lợi nhuận), Bảng 9 (chỉ số đối chuẩn B1/B2). Mọi tham số đều được gắn thẻ nguồn (source) và kiểm tra tự động qua scripts/verify_ocp1_params.py.

## Thông sÑ kù thu­t xe VinFast:


Dung lượng pin thực tế và mức tiêu thụ điện được đối soát từ thông số kỹ thuật xuất xưởng của VinFast (VinFast Product Specifications) theo chu kỳ thử nghiệm NEDC/WLTP.

## BiÃu giá c°Ûc thñc t¿ GSM:

Biểu cước chi tiết được đối soát trực tiếp từ bảng giá niêm yết chính thức đang áp dụng của Green SM Car tại thị trường Hà Nội.

## Cñ ly tuy¿n cía ngõ (Gateway):

Khoảng cách kết nối từ các cửa ngõ OCP1 ra các đầu mối giao thông lớn tại Hà Nội (như cầu Vĩnh Tuy, nút giao Cổ Linh) được đo đạc và kiểm chứng qua Open Source Routing Machine (OSRM).

## 3. Hệ thống công thức toán học và thuật toán điều phối

Mô hình điều phối giải bài toán gán cặp cực tiểu trên đồ thị hai phía (Minimum Weight Bipartite Matching) ở mỗi chu kỳ tick (2 phút):

## 3.1. Bài toán gán cặp Hungarian

Tại mỗi tick t, với tập xe rỗi V và tập yêu cầu cuốc đang chờ R, ma trận chi phí C_ij được xác định để giải bài toán quy hoạch nguyên:

## Ràng buộc:

## 3.2. Ma trận chi phí Baseline (F form) vs Policy (F+B form)

Nhánh Baseline (F) chỉ xét chi phí đón xe và thời gian chờ của khách, mù hoàn toàn trạng thái pin:

Điều kiện biên an toàn:


Trong đó Dist_ij là cự ly đường bộ đón khách (km), ETA_ij là thời gian đón (phút), τ = 20 phút là thời gian kiên nhẫn, θ_i là ngưỡng tự đi sạc của tài xế.

Nhánh Policy (F+B) tích hợp thêm thành phần chi phí cơ hội pin B_ij:

Chi phí điện năng thực tế:

Chi phí cơ hội pin cạn:

Ý nghĩa: E_ij là chi phí tiền điện thực tế của cuốc xe. O_ij là chi phí cơ hội cạn pin: xe có SoC thấp (1 - SoC lớn) nếu nhận cuốc đường dài (TripDist lớn) sẽ bị phạt rất nặng, buộc thuật toán phải giữ xe pin thấp lại chạy các cuốc ngắn nội khu và ưu tiên xe pin cao nhận cuốc đi xa.

## 3.3. Biểu thức tính cước phân tầng (Tiered Fare Formula)

Cước chuyến đi được tính theo các bậc cự ly thực tế:

## 3.4. Xác suất hủy chuyến và cơ chế hủy giữa đường

Hành khách rời hàng đợi theo quy luật hàm mũ dựa trên thời gian chờ W:

Quy tắc giải phóng xe khi khách hủy giữa chừng (cancelafter):

v.busyuntil = t + Trem

(nhả xe ngay tại vị trí hiện tại)

wastedkm += TravelDist (ghi nhận cự ly lãng phí)


## 3.5. Đặc tuyến sạc nhanh 2 cấp và hao hụt điều hòa khi dừng đỗ

Công suất sạc nhanh DC được mô hình hóa theo 2 bậc phụ thuộc vào ngưỡng nhiệt BMS 80%:

Hiệu suất nạp lưới: η = 0.90 ΔSoC = (Pcharge · η · Δt) / BatteryCapacity

Hao hụt điều hòa nhiệt độ cabin khi xe đỗ chờ khách hoặc chờ điều phối:

ΔSoCidle = − (1.2 kW · Δt) / BatteryCapacitykWh (Xe VinFast VF5 pin 37.23 kWh mất 3.22% SoC mỗi giờ dừng chờ)

## 4. Hạn chế của mô phỏng và mức độ tin cậy

## 4.1. Các hạn chế kỹ thuật cốt lõi

- LuÓng nhu c§u là mô phÏng (Synthetic demand): Nhu c§u cuÑc xe —°ãc sinh ng«u nhiên từ phân phối Lognormal và Poisson, chưa phản ánh các biến động bất thường ngoài thực tế như sự kiện lễ hội, mưa ngập đột ngột hay giờ tan tầm cục bộ tại từng tòa nhà.

- Mô hình v­n tÑc trung bình: TÑc Ù xe °ãc gán cÑ Ënh theo c¥p °Ýng (1540 km/h), chưa mô phỏng xung đột giao thông vi mô (microscopic traffic) như dừng chờ đèn đỏ, xe cộ chen chúc tại vòng xuyến hay kẹt xe giờ cao điểm.

- Gi£ Ënh pin lý t°ßng: Pin xe °ãc coi là ho¡t Ùng ß iÁu kiÇn nhiÇt Ù tiêu chu©n (25°C), chưa xét đến suy giảm dung lượng hóa học (battery degradation) và tổn hao nhiệt độ khắc nghiệt (nắng nóng 40°C mùa hè hoặc lạnh 10°C mùa đông Hà Nội).

- Chi¿m dång tr¡m s¡c t° nhân: T÷ lÇ chi¿m dång các tr¡m s¡c t° nhân -°ãc gán theo bảng giờ giả định (từ 20% ban đêm đến 60% giữa trưa) do chưa có API dữ liệu thời gian thực từ hệ thống trạm sạc V-Green.

## 4.2. Mức độ tin cậy (Reliability & Robustness)


- ‒Ù tin c­y thÑng kê cao: MÍi k¿t lu­n ‒Áu dña trên 140 ngày mô phÏng m×i nhánh (7 seed ngẫu nhiên độc lập x 20 ngày). Sai số chuẩn của giá trị trung bình (SEM) ở các chỉ số then chốt cực nhỏ: Km rỗng sai số ±4,8 km/ngày (< 0,36%), doanh thu sai số ±0,23 tr.đ (< 0,23%). Cả 7/7 seed đều cho kết quả nhất quán giảm km rỗng và tiết kiệm điện, loại bỏ hoàn toàn khả năng kết quả do may rủi ngẫu nhiên.

- KiÃm soát sai sÑ b±ng gate tñ Ùng: HÇ thÑng °ãc b£o vÇ bßi 28 bài kiÃm thí ¡n vË tự động (scripts/test_gsm_sim.py), kiểm tra nghiêm ngặt tính bất biến của luồng nhu cầu, không rò rỉ dữ liệu giữa các ngày và tái lập bit-identical chính xác tuyệt đối trên baseline ngày 0.

## 5. Đánh giá đối chuẩn ngành (Industry Baseline Validation)

Hệ thống Baseline (F form) trong nghiên cứu này chính là Baseline chuẩn mực kinh điển của ngành công nghiệp gọi xe và quản lý đội xe điện:

## 5.1. Tại sao là Baseline ngành?

- Chu©n mñc ‑iÁu phÑi theo cñ ly ‑ón: KÃ të công trình cça Harold W. Kuhn (1955), giải thuật Hungarian để tìm cặp ghép cực tiểu cự ly đón khách là phương pháp chuẩn mực được áp dụng phổ biến nhất trong mọi hệ thống điều phối taxi và ride-hailing công nghiệp (Alonso-Mora et al., 2017; Bertsimas et al., 2019).

- C¡ ch¿ 'Mù pin kèm sàn an toàn' (Battery-blind with SoC floor): Trong thñc t¿ triÃn khai đội xe điện của các hãng lớn (như Didi Chuxing, Grab, Uber Green và GreenSM giai đoạn đầu), phần mềm điều phối cuốc thường kế thừa nguyên vẹn từ nền tảng xe xăng truyền thống: ghép xe có thời gian đón nhanh nhất, chỉ kiểm tra thêm điều kiện biên là mức pin trên ngưỡng an toàn (thường là 15% - 20%). Tài xế tự quyết định thời điểm đi sạc dựa trên kinh nghiệm cá nhân.

## 5.2. Bằng chứng học thuật và tài liệu tham khảo (Citations & References)

- [1] Kuhn, H. W. (1955). 'The Hungarian method for the assignment problem'. Naval Research Logistics Quarterly, 2(1-2), 83-97. -> Nền tảng toán học của thuật toán gán cặp tối ưu cự ly đón.

- [2] Alonso-Mora, J., Samaranayake, S., Wallar, A., Frazzoli, E., & Rus, D. (2017). 'On-demand high-capacity ride-sharing via dynamic trip-vehicle routing'. PNAS, 114(3), 462-467. -> Tiêu chuẩn vàng chứng minh hiệu quả của bipartite matching trong điều phối xe theo thời gian thực.

- [3] Yan, P., Yu, K., Chao, X., & Chen, Z. (2023). 'An online reinforcement learning approach to charging and order-dispatching optimization for an e-hailing electric vehicle fleet'. European Journal of Operational Research, 310(1), 173-188.


https://doi.org/10.1016/j.ejor.2023.03.039 -> Khẳng định rõ thực tế ngành: 'The common practice is to dispatch EVs to serve orders by heuristic matching methods but enable EV drivers to independently make charging decisions based on their experiences' — đây chính là luận điểm gốc chứng minh Baseline trong mô phỏng phản ánh chính xác thực tế vận hành.

- [4] Chen, L., Hamedmoghadam, H., Jalili, M., & Ramezani, M. (2023). 'Electric Vehicle E-hailing Fleet Dispatching and Charge Scheduling'. arXiv:2302.12650. -> Phân tích khoảng cách hiệu quả giữa điều phối truyền thống không xét pin và điều phối có xét pin.

- [5] Maciejewski, M., Bischoff, J., & Nagel, K. (2016). 'An Assignment-based Approach for Simulating Electric Taxi Fleets'. Transportation Research Procedia, 19, 117-128. -> Mô hình benchmark chuẩn được tích hợp trong nền tảng mô phỏng MATSim kết hợp ngưỡng pin tối thiểu.

## 6. Phần bàn giao chuyên biệt cho các nhóm phát triển

## 6.1. Bàn giao cho nhóm Mô phỏng 3D (Spatial & Routing)

Các thông số hình học và quy tắc định tuyến phục vụ dựng cảnh 3D:

- M¡ng l°Ûi °Ýng:1.110 nút giao lÙ, 1.517 o¡n °Ýng, chiÁu dài tim °Ýng 144,2 km (file data/ocp1_graph.json).

- TÑc Ù °Ýng:¡i lÙ chính 40 km/h; °Ýng nhánh 35 km/h; °Ýng gom 30 km/h; đường khu chung cư 20 km/h; đường dịch vụ 15 km/h.

- H¡ t§ng tr¡m s¡c:30 tr¡m s¡c DC (156 cÕng) -ã snap vào nút g§n nh¥t (< 56 m). Tr¡m Vincom/Depot có 12 cổng 60 kW; Cụm dân cư có 4 cổng 30 kW.

- Quy t¯c vòng quanh hÓ:HÓ San Hô 24,5 ha c¥m tuyÇt –Ñi ‑i xuyên qua các c¡nh m·t nước {120, 206, 551, 552, 871, 923}. Tuyến Vincom -> Cổng Bắc đo thực tế 3,33 km, gấp 1,2094 lần đường chim bay (2,75 km).

- CÕng ông cô l­p:CÕng ông (node 4915951940) thuÙc o¡n °Ýng cåt 28 node cô lập hoàn toàn (khoảng cách Dijkstra = inf). Không spawn xe hoặc gán khách tại cổng này.

| Zone ID Tên vị trí Node ID Tọa độ GPS Ghi chú kỹ thuật (Anchor) (Lat, Lon) cho nhóm 3D |
| --- |
| Zone 0 Vincom Mega 7262861319 20.99400, Điểm đón khách Mall 105.95863 lớn nhất OCP1, trạm sạc 12 cổng |


Zone 1

Vinschool Liên 7262861412 cấp

60 kW

Tập trung nhu cầu đầu ngày (06:45–

20.99448, 105.93663

07:30)

Bãi tập kết đội xe, trạm sạc trung tâm 12 cổng

Zone 2

VinBus Depot 7262861361

20.99195, 105.96066

Cổng Bắc (North 642954579 Gate)

Cửa ngõ ra Quốc lộ 5 và cao tốc Hà Nội - Hải Phòng

Zone 3

21.01039, 105.93473

Cổng Nam (South 10691095504 Gate)

Cửa ngõ kết nối Ecopark và Hưng

Zone 4

20.97096, 105.95165

Yên

Cổng Tây (West 10876114913 Gate)

Cửa ngõ nút giao Cổ Linh hướng về cầu Vĩnh Tuy

Zone 5

20.98801, 105.93882

ĐƯỜNG CỤT CÔ LẬP — Dijkstra = inf (không gán xe)

Cổng Đông (East 4915951940 Gate)

Zone 6

21.00099, 105.96617

Cụm Sapphire 1 8333311848 (st01)

Cụm căn hộ cao tầng mật độ cao phía Bắc

Zone 7

20.99950, 105.94720

Cụm Sapphire 2 12011835346 (st17)

Cụm căn hộ cao tầng mật độ cao

Zone 8

20.99220, 105.93920

phía Tây


*Hình 2: Bản đồ mạng lưới giao thông OCP1, 9 zones, trạm sạc DC và tuyến đường vòng ven hồ*

*San Hô.*

## 6.2. Bàn giao cho nhóm Baseline & Kinh tế (Economics & Physics)

- BiÃu c°Ûc chi ti¿t:Mß cía 30.500  (2 km §u); cñ ly 212 km: 14.700 /km; 1225 km: 13.800 đ/km; trên 25 km: 11.900 đ/km; phụ phí đêm +20.000 đ. Cuốc 15 km ban ngày chuẩn đạt 218.900 đ.

- ‐·c tính s¡c 2 c¥p:S¡c 40 kW d°Ûi 80% SoC (10% lên 70% m¥t ‐úng 33,51 phút), taper xuống 15 kW trên 80% SoC (chậm gấp 2,67 lần). Hiệu suất nạp 90%.

- Hao håt iÁu hòa khi dëng ×:iÁu hòa tiêu hao 1,2 kW liên tåc khi xe dëng chÝ (m¥t 3,22% SoC/h trên pin VF5).

- ChuyÃn giao pin qua –êm (Carryover):50% xe ‑°ãc c¯m s¡c –êm lên méc [0,8, 1,0]. Mức SoC trung bình mở đầu ngày mới dịch chuyển dương (> +0,04) phản ánh chu kỳ vận hành liên tục.


*Hình 3: Quỹ đạo pin trung bình theo giờ (05h–23h) và đặc tuyến sạc nhanh 2 cấp (knee 80%*

*SoC).*

## 7. Danh mục File Artifacts & Lệnh Kiểm Thử

- Dï liÇu b£n Ó:data/ocp1_graph.json  B£n Ó sÑ m¡ng l°Ûi °Ýng OCP1 (1.110 nút, 1.517 đoạn đường, 30 trạm sạc, 9 zones).

- Tham sÑ hÇ thÑng:data/ocp1_params.json - 43 tham sÑ v­t lý, kinh t¿ và v­n hành.

- K¿t qu£ mô phÏng:results/ocp1-baseline.json & results/ocp1-policy.json - Toàn bÙ kết quả 280 ngày chạy mô phỏng.

- Tài liÇu kù thu­t:docs/OCP1.md - Báo cáo kù thu­t chi ti¿t ti¿ng Anh kèm b£ng ma trận nguồn gốc 43 tham số.

- LÇnh kiÃm thí -Ñi soát:Ch¡y 'rtk make verify-ocp1' -Ã kiÃm tra k¿t qu£ OCP1; ch¡y 'rtk make verify-sim' để chạy toàn bộ 21 gate kiểm thử của hệ thống.

Tài liệu này cung cấp đầy đủ luận cứ khoa học, phương pháp luận và số liệu thực nghiệm, hoàn tất bàn giao cho nhóm Baseline và nhóm Mô phỏng 3D.
