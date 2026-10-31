# HƯỚNG DẪN SỬ DỤNG CÔNG CỤ LẤY LINK KÝ HỢP ĐỒNG AMIS WESIGN

Công cụ tự động hóa quy trình lấy link ký hợp đồng của người lao động từ hệ thống AMIS WeSign thông qua số CCCD/CMND.

---

## 1. CÁCH KHỞI CHẠY ỨNG DỤNG

### Cách 1: Ứng Dụng Phần Mềm Desktop Python (Tiện Lợi Nhất)
- Nhấp đúp chuột vào file **`Chay_App_Desktop.bat`** (hoặc chạy lệnh `python gui_app.py`).
- Cửa sổ phần mềm Desktop sẽ mở lên ngay lập tức:
  - Cột trái: Nhập / dán hàng loạt số CCCD hoặc chọn file Excel để nạp vào.
  - Cột phải: Bảng kết quả hiển thị thời gian thực, nút **Xuất Excel** và nút **Sao chép tất cả link**.
  - Góc trên bên phải: Nút **"⚙️ Đổi Token & Cookie"** để cập nhật nhanh khi hết hạn.

### Cách 2: Giao Diện Web Trình Duyệt
- Nhấp đúp chuột vào file **`Chay_Ung_Dung.bat`** (mở tại `http://localhost:5050`).

### Cách 3: Chạy Dòng Lệnh (CLI)
- Tra cứu 1 số CCCD: `python get_links.py 014207009207`
- Tra cứu file Excel: `python get_links.py -f file.xlsx -o ketqua.xlsx`

---

## 2. CÁC TÍNH NĂNG CHÍNH TRÊN GIAO DIỆN WEB

### 1. Tra cứu 1 người (Đơn lẻ)
- Nhập số CCCD vào ô tìm kiếm -> Nhấn phím `Enter` hoặc bấm **"Lấy Link Ký"**.
- Kết quả hiển thị tức thì gồm:
  - Họ và tên người lao động
  - Chức vụ (Người lao động)
  - Tên hợp đồng / văn bản
  - Trạng thái hợp đồng
  - Đường dẫn ký hợp đồng (Sign Link)
- Hỗ trợ **1 click sao chép link** vào bộ nhớ tạm hoặc **Mở liên kết** trực tiếp trên tab mới.

### 2. Tra cứu hàng loạt (Bulk Lookup)
Có 2 phương thức nhập dữ liệu:
- **Dán danh sách CCCD:** Dán danh sách các số CCCD (mỗi số trên 1 dòng) vào khung nhập liệu.
- **Tải lên file Excel (.xlsx, .xls) hoặc CSV:** 
  - Kéo thả hoặc bấm để chọn file.
  - Hệ thống tự động nhận diện cột chứa CCCD (bạn cũng có thể chọn cột theo ý muốn).
- Bấm nút **"Bắt Đầu Lấy Link"**:
  - Tiến trình xử lý hiển thị trực tiếp theo thời gian thực (Real-time).
  - Từng dòng kết quả xuất hiện ngay trên bảng khi vừa lấy xong (không cần chờ xử lý hết).
  - Có thể bấm **"Dừng Lại"** bất kỳ lúc nào nếu cần.
- **Sau khi hoàn tất:**
  - Bấm **"Xuất File Excel (.xlsx)"** để tải về file Excel báo cáo hoàn chỉnh (đã được định dạng đẹp mắt, link ký được gắn hyperlink click mở ngay).
  - Bấm **"Sao Chép Toàn Bộ Link"** để copy nhanh tất cả link sang bảng tính hoặc tin nhắn.

### 3. Xem lịch sử thao tác & Lọc trạng thái ký (Mới nâng cấp)
- Hệ thống tự động phân tích lịch sử văn bản từ API WeSign để xác định:
  - **🎉 Đã hoàn tất**: Tất cả các bên đã ký xong hợp đồng.
  - **✍️ NLĐ đã ký**: Người lao động đã bấm ký vào đường link (kèm ngày giờ ký chính xác).
  - **👀 Đã xem (Chưa ký)**: Người lao động đã bấm mở xem văn bản nhưng chưa ký.
  - **⏳ Chưa xem**: Người lao động chưa từng mở liên kết ký.
- **Bộ lọc kết quả:** Có thể lọc nhanh danh sách theo các trạng thái trên (ví dụ lọc riêng những người chưa ký để nhắc nhở).
- **Xem chi tiết lịch sử:** Bấm vào biểu tượng đồng hồ **🕒** trên mỗi dòng để xem dòng thời gian chi tiết (Ai gửi, ai xem lúc nào, ai ký lúc nào).
- **File Excel xuất ra:** Tự động kèm đầy đủ các cột: *Tiến độ ký, Thời gian NLĐ ký, Thời gian hoàn tất, Thời gian NLĐ xem*.

### 4. Gửi Lại Hợp Đồng Cho NLĐ (Resend Contract - Mới)
- **Gửi lại đơn lẻ:** Tại kết quả tra cứu của từng người hoặc cột thao tác trên bảng kết quả, bấm nút **"📨 Gửi Lại Hợp Đồng"** để hệ thống gọi thẳng API WeSign gửi lại email/thông báo mời ký cho NLĐ đó.
- **Gửi lại hàng loạt:** Trên thanh công cụ, bấm nút **"📨 Gửi Lại Cho NLĐ Chưa Ký"**, hệ thống sẽ tự động lọc toàn bộ những người chưa ký (`Chưa xem`, `Đã xem (Chưa ký)`) và gửi lại đồng loạt chỉ bằng 1 cú nhấp chuột!

---

## 4. CÁCH CẬP NHẬT TOKEN & COOKIE KHI HẾT HẠN

Phiên đăng nhập trên WeSign hoặc mã bảo vệ Cloudflare (`cf_clearance`) có thời hạn nhất định. Khi nhận thông báo lỗi **401 Unauthorized** hoặc **423 Locked**, bạn chỉ cần cập nhật lại thông tin như sau:

### Cách cập nhật 1 bước cực nhanh (Khuyên Dùng):
1. Đăng nhập vào trang AMIS WeSign trên trình duyệt (Chrome, Edge, Cốc Cốc).
2. Vào màn hình danh sách hợp đồng hoặc đợt hợp đồng bạn đang quản lý.
3. Bấm phím **F12** (hoặc chuột phải -> chọn **Kiểm tra / Inspect**).
4. Chuyển sang thẻ **Network (Mạng)**.
5. Tải lại trang (F5) hoặc thực hiện tìm kiếm / bấm chuyển trang trên WeSign.
6. Trong danh sách request ở thẻ Network, tìm request tên **`batch-data`** (hoặc bất kỳ request nào của WeSign).
7. Nhấp **chuột phải** vào request đó -> chọn **Copy** -> chọn **Copy as cURL (bash)**.
8. Mở ứng dụng này -> Chuyển sang thẻ **"Cấu Hình & Token"** -> Dán toàn bộ vào ô *"Dán lệnh curl..."* -> Bấm **"Phân Tích & Cập Nhật Tự Động"**.
9. Hệ thống sẽ tự động tách Token, Cookie, ID đợt hợp đồng (`DocumentBatchId`), ID doanh nghiệp (`TenantId`) và lưu lại. Bấm **"Kiểm tra kết nối"** để thấy kết nối thành công!

---

## 4. CẤU TRÚC THƯ MỤC DỰ ÁN

- `Chay_Ung_Dung.bat`: File nhấp đúp để khởi động ứng dụng Web.
- `app.py`: Máy chủ Web dịch vụ API và giao diện người dùng.
- `wesign_api.py`: Module cốt lõi tương tác với 2 API của AMIS WeSign.
- `get_links.py`: Công cụ chạy dòng lệnh trực tiếp (CLI) hoặc xử lý file Excel độc lập.
- `config.json`: File lưu trữ cấu hình kết nối, Token, Cookie, Batch ID.
- `web/index.html`: Giao diện ứng dụng người dùng (HTML5, Tailwind CSS, Javascript).
- `Mau_Danh_Sach_CCCD.xlsx`: File Excel mẫu sẵn có chứa dữ liệu mẫu để thử nghiệm.
