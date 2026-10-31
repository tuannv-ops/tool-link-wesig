import os
import sys
import json
import time
import base64
import io
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

from wesign_api import WeSignClient, parse_curl_command
from agency_api import parse_agency_curl
from get_links import find_cccd_column

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, 'web')
INDEX_HTML = os.path.join(WEB_DIR, 'index.html')

client = WeSignClient()

class AppHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Giảm log ồn ào ở console, chỉ in lỗi hoặc request chính
        if 'api/' in args[0]:
            print(f"[API] {args[0]} - {args[1]}")

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/' or path == '/index.html':
            if os.path.exists(INDEX_HTML):
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                with open(INDEX_HTML, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Khong tim thay web/index.html")
            return

        if path in ['/logo.png', '/assets/logo.png', '/favicon.ico']:
            logo_path = os.path.join(BASE_DIR, 'logo.png')
            if not os.path.exists(logo_path):
                logo_path = os.path.join(WEB_DIR, 'assets', 'logo.png')
            if os.path.exists(logo_path):
                self.send_response(200)
                self.send_header('Content-Type', 'image/png')
                self.send_header('Cache-Control', 'max-age=86400')
                self.end_headers()
                with open(logo_path, 'rb') as f:
                    self.wfile.write(f.read())
                return
            self.send_response(404)
            self.end_headers()
            return

        if path == '/api/config':
            cfg = client.load_config()
            cfg['agency_portal'] = client.agency_client.load_config()
            self._send_json(cfg)
            return

        self._send_json({"success": False, "message": f"Tài nguyên không tồn tại ({path})"}, status=404)
        return

    def do_POST(self):
        path = self.path.split('?')[0]
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b'{}'

        try:
            req_data = json.loads(body.decode('utf-8')) if body else {}
        except Exception:
            req_data = {}

        if path == '/api/config':
            if 'agency_portal' in req_data:
                client.agency_client.save_config(req_data['agency_portal'])
            updated = client.save_config(req_data)
            updated['agency_portal'] = client.agency_client.config
            self._send_json({"success": True, "config": updated})
            return

        elif path == '/api/test-connection':
            res = client.test_connection()
            self._send_json(res)
            return

        elif path == '/api/parse-curl':
            curl_str = req_data.get('curl', '')
            extracted = parse_curl_command(curl_str)
            if not extracted or not (extracted.get('token') or extracted.get('cookie')):
                self._send_json({"success": False, "message": "Không tìm thấy Token hoặc Cookie hợp lệ trong cURL"})
                return
            client.save_config(extracted)
            test_res = client.test_connection()
            self._send_json({"success": True, "extracted": extracted, "test": test_res})
            return

        elif path == '/api/parse-agency-curl':
            curl_str = req_data.get('curl', '')
            extracted = parse_agency_curl(curl_str)
            if not extracted or not extracted.get('cookie'):
                self._send_json({"success": False, "message": "Không tìm thấy Cookie hợp lệ trong cURL Agency Portal"})
                return
            saved_agency = client.agency_client.save_config(extracted)
            test_res = client.agency_client.test_connection()
            msg = "Đã cập nhật Cookie Agency Portal thành công!"
            if test_res.get('success'):
                msg += " (Đã kết nối thành công)"
            else:
                msg += f" (Cảnh báo: {test_res.get('message', '')})"
            self._send_json({"success": True, "message": msg, "agency_config": saved_agency, "test": test_res})
            return

        elif path == '/api/test-agency-connection':
            test_res = client.agency_client.test_connection()
            self._send_json(test_res)
            return

        elif path == '/api/lookup-single':
            cccd = req_data.get('cccd', '')
            res = client.get_link_by_cccd(cccd)
            self._send_json(res)
            return

        elif path == '/api/document-history':
            doc_id = req_data.get('doc_id', '')
            worker_name = req_data.get('worker_name', '')
            res = client.get_document_history(doc_id, worker_name)
            self._send_json({"success": True, "data": res})
            return

        elif path == '/api/lookup-batch':
            cccd_list = req_data.get('cccds', [])
            delay = float(req_data.get('delay', 0.25))

            # Gửi Header SSE ngay lập tức để trình duyệt kết nối tức thì
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'close')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()

            # Đồng bộ bộ nhớ đệm nếu chưa nạp (force=False để chạy tức thì)
            try:
                sync_msg = {"type": "syncing", "message": "Đang nạp dữ liệu từ các đợt hợp đồng..."}
                self.wfile.write(f"data: {json.dumps(sync_msg, ensure_ascii=False)}\n\n".encode('utf-8'))
                self.wfile.flush()
                client.sync_all_contracts(force=False)
            except Exception:
                pass

            total = len(cccd_list)
            for idx, cccd in enumerate(cccd_list):
                try:
                    res = client.get_link_by_cccd(cccd)
                    event_payload = {
                        "index": idx + 1,
                        "total": total,
                        "data": res
                    }
                    msg = f"data: {json.dumps(event_payload, ensure_ascii=False)}\n\n"
                    self.wfile.write(msg.encode('utf-8'))
                    self.wfile.flush()
                except Exception:
                    break

                if idx < total - 1 and delay > 0:
                    time.sleep(delay)

            try:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except Exception:
                pass
            self.close_connection = True
            return

        elif path == '/api/parse-excel':
            if not pd:
                self._send_json({"success": False, "message": "Chưa cài đặt thư viện 'pandas' và 'openpyxl'. Vui lòng chạy lệnh: pip install -r requirements.txt"})
                return
            base64_data = req_data.get('base64', '')
            filename = req_data.get('filename', 'data.xlsx')

            try:
                file_bytes = base64.b64decode(base64_data)
                buf = io.BytesIO(file_bytes)
                if filename.lower().endswith('.csv'):
                    df = pd.read_csv(buf, dtype=str)
                else:
                    df = pd.read_excel(buf, dtype=str)

                # Làm sạch
                df = df.fillna('')
                columns = list(df.columns)
                selected_col = find_cccd_column(df)

                columns_data = {}
                for col in columns:
                    vals = [str(x).strip() for x in df[col] if str(x).strip()]
                    columns_data[col] = vals

                self._send_json({
                    "success": True,
                    "columns": columns,
                    "selected_column": selected_col,
                    "total_rows": len(df),
                    "columns_data": columns_data,
                    "cccds": columns_data.get(selected_col, [])
                })
            except Exception as e:
                self._send_json({"success": False, "message": f"Không đọc được file: {str(e)}"})
            return

        elif path == '/api/export-excel':
            if not pd or not HAS_OPENPYXL:
                self._send_json({"success": False, "message": "Chưa cài đặt thư viện 'openpyxl'. Vui lòng chạy lệnh: pip install -r requirements.txt"}, status=500)
                return
            results = req_data.get('results', [])
            try:
                export_data = []
                for idx, r in enumerate(results):
                    export_data.append({
                        "STT": idx + 1,
                        "Số CCCD": r.get('cccd', ''),
                        "Họ và Tên NLĐ": r.get('worker_name', ''),
                        "Số Điện Thoại": r.get('phone', ''),
                        "Link Zalo": r.get('zalo_link', ''),
                        "Chức Vụ": r.get('job_position', ''),
                        "Đợt Ký / Lô HĐ": r.get('batch_name', ''),
                        "Tiến Độ Ký (Lịch Sử)": r.get('signing_state', 'Chưa rõ') if r.get('status') == 'success' else '-',
                        "Thời Gian NLĐ Ký": r.get('worker_signed_time', '-') if r.get('status') == 'success' else '-',
                        "Thời Gian Hoàn Tất": r.get('completed_time', '-') if r.get('status') == 'success' else '-',
                        "Thời Gian NLĐ Xem": r.get('worker_viewed_time', '-') if r.get('status') == 'success' else '-',
                        "Tên Hợp Đồng": r.get('doc_name', ''),
                        "Trạng Thái Văn Bản": r.get('doc_status', ''),
                        "Trạng Thái Tra Cứu": "Thành công" if r.get('status') == 'success' else ("Không tìm thấy" if r.get('status') == 'not_found' else "Lỗi"),
                        "Link Ký Hợp Đồng": r.get('sign_link', '')
                    })

                df = pd.DataFrame(export_data)
                buf = io.BytesIO()

                with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='DanhSachLinkKy')
                    ws = writer.sheets['DanhSachLinkKy']

                    # Styling đẹp cho bảng Excel
                    header_fill = PatternFill(start_color="1E40AF", end_color="1E40AF", fill_type="solid")
                    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
                    thin_border = Border(
                        left=Side(style='thin', color='D1D5DB'),
                        right=Side(style='thin', color='D1D5DB'),
                        top=Side(style='thin', color='D1D5DB'),
                        bottom=Side(style='thin', color='D1D5DB')
                    )

                    for col_num, col_name in enumerate(df.columns, 1):
                        cell = ws.cell(row=1, column=col_num)
                        cell.fill = header_fill
                        cell.font = header_font
                        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

                    # Định dạng các dòng dữ liệu
                    for row_idx in range(2, len(df) + 2):
                        ws.row_dimensions[row_idx].height = 22
                        for col_idx in range(1, len(df.columns) + 1):
                            cell = ws.cell(row=row_idx, column=col_idx)
                            cell.border = thin_border
                            cell.font = Font(name="Calibri", size=10)
                            # Căn giữa STT, CCCD, SĐT, Trạng thái
                            if col_idx in [1, 2, 4, 8, 9]:
                                cell.alignment = Alignment(horizontal="center", vertical="center")
                            else:
                                cell.alignment = Alignment(vertical="center")

                            # Nếu là cột Link Ký Hợp Đồng hoặc Link Zalo
                            if cell.value and str(cell.value).startswith('http'):
                                cell.font = Font(name="Calibri", size=10, color="2563EB", underline="single")
                                cell.hyperlink = str(cell.value)

                    # Tự động điều chỉnh độ rộng cột
                    for col in ws.columns:
                        max_len = max(len(str(cell.value or '')) for cell in col)
                        col_letter = get_column_letter(col[0].column)
                        ws.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 65)

                buf.seek(0)
                excel_bytes = buf.getvalue()

                self.send_response(200)
                self.send_header('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                self.send_header('Content-Disposition', 'attachment; filename="DanhSachLinkKy.xlsx"')
                self.send_header('Content-Length', str(len(excel_bytes)))
                self.end_headers()
                self.wfile.write(excel_bytes)
                return
            except Exception as e:
                self._send_json({"success": False, "message": f"Lỗi xuất Excel: {str(e)}"}, status=500)
                return

        elif path == '/api/resend-contract':
            doc_id = req_data.get('doc_id')
            doc_ids = req_data.get('doc_ids', [])
            if doc_id and doc_id not in doc_ids:
                doc_ids.append(doc_id)
            if not doc_ids:
                self._send_json({"success": False, "message": "Vui lòng cung cấp ID hợp đồng (doc_id hoặc doc_ids)"}, status=400)
                return

            result = client.resend_documents(doc_ids)
            status_code = 200 if result.get('success') else 400
            self._send_json(result, status=status_code)
            return

        self._send_json({"success": False, "message": f"Endpoint không tồn tại ({path}). Vui lòng tải lại trang (F5) hoặc khởi động lại app."}, status=404)
        return

def run_server(port=5050, auto_open=True):
    httpd = None
    target_port = port
    # Tự động chuyển cổng nếu 5050 đang bị ứng dụng khác hoặc phiên trước chiếm dụng
    for p in range(port, port + 10):
        try:
            server_address = ('', p)
            httpd = ThreadingHTTPServer(server_address, AppHandler)
            target_port = p
            break
        except OSError:
            continue

    if not httpd:
        print(f"[!] Khong the mo cong tu {port} den {port + 9}. Vui long tat cac cua so Python dang chay ngam.")
        return

    url = f"http://localhost:{target_port}"
    print("=" * 60)
    print(f"[*] UNG DUNG WEISIGN LINK HUNTER DANG CHAY TAI: {url}")
    print(f"[*] Dang tu dong mo trinh duyet tai: {url}...")
    print("=" * 60)

    if auto_open:
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"[!] Khong the tu mo trinh duyet: {e}")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Dang tat may chu...")
        httpd.server_close()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    auto_open = 'RENDER' not in os.environ and 'PORT' not in os.environ
    run_server(port=port, auto_open=auto_open)
