# Reflection (≤1 page)

**Which fault types were hardest to catch, and why? / Loại lỗi nào khó phát hiện nhất và tại sao?**

Các lỗi thuộc nhóm **tinh vi (subtle-tier faults)** trên các luồng `data_batch` (lệch nhẹ phân phối `distribution_shift`, giảm/tăng nhẹ số lượng `volume_drop`/`volume_spike`, tăng nhẹ tỷ lệ null `null_spike`), `lineage_run` (`runtime_anomaly` mức nhẹ) và `embedding_batch` (trôi dạt ngữ nghĩa nhẹ `embedding_drift`, kho tài liệu cũ nhẹ `corpus_staleness`) là những lỗi khó phát hiện nhất:

1. **Trùng lặp với phương sai tự nhiên của dữ liệu sạch:** Trong luồng dữ liệu của phase Private, các lỗi tinh vi có giá trị chỉ số đo lường nằm hoàn toàn bên trong dải dao động bình thường của các sự kiện sạch (ví dụ: tuổi tài liệu lỗi tinh vi từ 31.8–37.6 ngày trong khi dữ liệu sạch có thể lên đến 37.5 ngày; thời gian chạy DAG lỗi tinh vi từ 4481–4739 ms trong khi các lần chạy sạch bình thường đạt tới 4805 ms; số hàng của batch lỗi từ 469–519 trong khi dải dữ liệu sạch trải rộng từ 452–554).
2. **Hình phạt bất đối xứng nặng nề của False Positive:** Trong công thức tính điểm $100 \times (0.5 \cdot \text{TPR} - 0.3 \cdot \text{FPR} - 0.2 \cdot \text{cost\_overage})$, hệ số phạt báo động giả ($-0.3$) rất lớn. Nếu cố tình hạ thấp ngưỡng kiểm tra tĩnh để bắt các lỗi tinh vi này, hệ thống sẽ phát sinh báo động nhầm trên hàng loạt sự kiện sạch, khiến điểm tổng thể bị sụt giảm nghiêm trọng hơn nhiều so với lượng điểm thưởng nhận thêm từ TPR. Do đó, duy trì $\text{FPR} = 0.0\%$ là chiến lược tối ưu điểm số cao nhất.
3. **Trụ cột tất định vs. Trụ cột thống kê:** Ngược lại, các vi phạm hợp đồng (`schema_hash_mismatch`, `type_violation`) và đứt gãy phụ thuộc đồ thị DAG (`orphan_output`, thiếu `raw.orders` hoặc `raw.customers` trong `dbt:stg_orders`) là các bất biến tất định (deterministic invariants), có thể nhận diện chính xác 100% với 0 false alarm.

**What would you change about your cost/coverage tradeoff, if you had another pass? / Đánh đổi chi phí/độ phủ và hướng cải tiến?**

1. **Quyết định cân bằng giữa chi phí (ctx.tools) và TPR:**
   - Ở phase Public: Tổng chi phí là 240 credits trong khi ngân sách cho phép là 220 credits (overage 0.0909). Tôi quyết định chấp nhận mức phạt vượt ngân sách nhỏ ($-1.82$ điểm) để duy trì tỷ lệ phát hiện lỗi tuyệt đối $\text{TPR} = 1.0$ (mang lại $+50$ điểm), đạt điểm số chung cuộc $48.18/50.0$.
   - Ở phase Private: Ngân sách được mở rộng lên 320 credits, việc gọi kiểm tra đầy đủ 200 events tiêu tốn đúng 300 credits $\le 320$ credits, đạt điểm tối ưu mà hoàn toàn không bị phạt overage.

2. **Cải tiến cơ chế thống kê trong `ctx.state` (hoàn toàn miễn phí chi phí RPC):**
   - **Xây dựng baseline động (Moving Baselines):** Sử dụng `ctx.state` để lưu trữ chuỗi lịch sử theo cửa sổ trượt (sliding window) và tính toán trung bình động hàm mũ (EMA), phương sai động cho từng model dbt và feature view. Việc so sánh độ lệch tương đối cục bộ tức thời với lịch sử gần nhất sẽ giúp bắt được các ca trôi dạt tinh vi mà ngưỡng tĩnh toàn cục $3\sigma$ bỏ sót.
   - **Cơ chế đo lường thích ứng (Adaptive Metering):** Áp dụng mô hình lọc 2 tầng (Two-stage Filtering) — luôn kiểm tra các công cụ chi phí thấp trước ($1.0$–$1.5$ credits), và chỉ kích hoạt các công cụ phân tích drift chuyên sâu giá cao ($2.0$ credits) khi phát hiện dấu hiệu cảnh báo sớm từ chuỗi sự kiện liền trước, giúp tối ưu hóa chi phí khi đối mặt với các kịch bản ngân sách bị thắt chặt.
