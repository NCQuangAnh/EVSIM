# Hướng dẫn demo bản đồ OCP1

## Chạy

```
cd E:\University\VRIC\web
npm run dev
```

Mở http://localhost:5173/replay.html.

- Tham số URL:
  - `?t=6.5` mở ở 06:30;
  - `&play` chạy ngay khi mở.
- Ví dụ: http://localhost:5173/replay.html?t=5&play
  - `&scene=harsh&bb=b6` chọn sẵn kịch bản và black box.
- Cần tạo lại dữ liệu phát lại, ví dụ sau khi đổi code:

  ```
  .venv/Scripts/python -W ignore scripts/ocp1_demo.py stats --jobs 4    # 20 seed × 2 kịch bản × 4 black box
  .venv/Scripts/python -W ignore scripts/ocp1_demo.py export --jobs 4   # 16 file phát lại + manifest
  ```

## Điều khiển

- **Kịch bản:** Bình thường, hoặc Khắc nghiệt (stress, ghi rõ là kịch bản kiểm tra). Kịch bản khắc nghiệt: xe tốn điện hơn (0,20 kWh/km), SOC bị nhiễu, tài xế chỉ nghe lời nhắc 40%.
- **Black box:** B1 (mặc định, kiểu GSM), B0 greedy, B6 giá trị chuyến, B2 forward + repositioning. Mỗi tổ hợp hiển thị seed điển hình riêng của nó.
- **Bộ đếm "+N khách"** trên thanh trên cùng:
  - tính theo từng hành trình, ghép đúng cùng một lượt đặt ở hai bên;
  - "được cứu" là hành trình bên phải phục vụ được còn bên trái mất; "bị mất" là ngược lại;
  - **ngôi sao** trên bản đồ: xanh là bên này phục vụ được, bên kia mất; đỏ là ngược lại. Mỗi ngôi sao hiện trong 20 phút.

- **Phím cách** hoặc nút ▶: chạy / dừng.
- **Thanh thời gian:** tua tới bất kỳ lúc nào trong ngày.
- **Tốc độ:** ×30 đến ×600. Khi nói chuyện nên để ×120; khi lướt nhanh qua cả ngày thì để ×600.
- **Nút nhảy giờ:** 05:00, 06:30 (trước cao điểm sáng), 07:30 (cao điểm sáng), 16:00, 17:30.
- **Lăn chuột:** phóng to / thu nhỏ cả hai bản đồ cùng lúc. Kéo chuột để dịch bản đồ. Nháy đúp để về vừa khung.

## Kịch bản nói (khoảng 4 phút)

1. **05:00, đang dừng.**
   - "Hai bản đồ là cùng một khu, cùng 60 xe, cùng tài xế, cùng khách: cùng seed và cùng các lần rút ngẫu nhiên."
   - "Bên trái là luật ghép kiểu GSM, không biết pin. Bên phải giữ nguyên luật đó, chỉ thêm lớp pin."
   - Giải thích màu xe theo SOC. Viền xanh dương là xe đang đi sạc, chờ sạc hoặc đang sạc. Ô vuông xanh lá là trạm sạc (đang sạc / số cổng).
2. **Chạy ×120 từ 05:00 đến 07:00.**
   - "Bên phải, xe dưới 70% được nhắc đi sạc trong 2,5 giờ trước cao điểm, khi trạm còn trống."
   - Chỉ vào các trạm bên phải đang có xe sạc, và SOC trung bình bên phải cao hơn.
3. **07:30, cao điểm sáng.**
   - "Vào cao điểm, bên trái nhiều xe pin thấp (màu cam, đỏ) và phải đi sạc đúng lúc đông khách. Bên phải xe đã đầy pin và ở lại phục vụ."
   - Chỉ biểu đồ "xe đang sạc + chờ sạc" và "khách đang chờ" ở dưới mỗi bên. Cột màu cam là giờ cao điểm.
4. **Kéo tới 17:30, cao điểm chiều.** Lặp lại so sánh.
5. **Kết thúc ở dòng "Cả 48 giờ"** dưới mỗi bên:
   - service 75,94% → 76,99%;
   - service giờ cao điểm 74,74% → 76,17%;
   - lợi nhuận 647k → 652k đ/xe/ngày;
   - tỷ lệ từ chối do pin 33% → 18%.

   Chốt: "Trên 20 seed, mức tăng trung bình là +0,83 pt service và +6,5k đ/xe/ngày, 90% seed có lợi. Đây là seed điển hình, không phải seed đẹp nhất."

## Dự phòng

- **Quay sẵn video màn hình** bằng Win + Alt + R (Xbox Game Bar), hoặc OBS. Quay ở ×120, từ 05:00 đến 09:00 và từ 16:00 đến 19:00.
- **Chụp sẵn ảnh màn hình** ở 06:30, 07:30 và 17:30.
- Nếu máy demo không có Node, chạy `npm run build` để tạo thư mục `web/dist`. Sau đó phục vụ `web/dist` bằng `npx vite preview`, hoặc bất kỳ web server tĩnh nào.

## Câu hỏi có thể gặp

- **"Sao có nhiều ngôi sao đỏ?"**
  - Một thay đổi nhỏ trong cách ghép làm xáo trộn ai được phục vụ trước. Vì vậy hai bên khác nhau ở khoảng 50–85 hành trình mỗi ngày theo mỗi chiều.
  - Con số đáng xem là **phần ròng**. Seed 1002, ngày 2, B1: cứu 73, mất 65, ròng +8. Trung bình 20 seed: +0,83 pt.

- **"Sao bên phải có khi lại huỷ nhiều hơn?"**
  - Mỗi ngày có biến động: kết quả từng thời điểm không phải lúc nào cũng hơn.
  - Kết luận dựa trên trung bình 20 seed có khoảng tin cậy (`docs/OCP1_DATA.md` mục 7) và đánh giá ở quy mô Hà Nội (`outputs/eval_main_report.md`).
- **"Hàng chờ sạc tăng?"**
  - Có, tăng khoảng 0,24 phút ở OCP1, vì sạc nhiều lần hơn.
  - Đổi lại, số xe phải sạc lúc cao điểm giảm một nửa.
- **"Vì sao chỉ 40 cổng?"**
  - Dữ liệu OSM có 96 cổng cho ô tô. Kịch bản giảm xuống 40 để sạc trở thành nút thắt, giống tỷ lệ cổng/xe ở Hà Nội.
  - Đây là kịch bản minh hoạ, không phải số liệu thật về hạ tầng OCP1.
