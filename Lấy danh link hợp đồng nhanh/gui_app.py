import os
import sys
import json
import time
import threading
import webbrowser
from datetime import datetime

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

from wesign_api import WeSignClient, parse_curl_command
from get_links import find_cccd_column

class WeSignGUIApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Tool Lấy Link Hợp Đồng Lao Động Nhanh")
        self.root.geometry("1160x720")
        self.root.minsize(980, 600)

        # Căn giữa cửa sổ trên màn hình
        self.center_window(1160, 720)

        # Nạp logo thương hiệu
        self.logo_photo = None
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logo.png')
        if os.path.exists(logo_path) and HAS_PIL:
            try:
                pil_img = Image.open(logo_path)
                w, h = pil_img.size
                new_h = 36
                new_w = max(1, int(w * (new_h / h)))
                pil_resized = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                self.logo_photo = ImageTk.PhotoImage(pil_resized)
                self.root.iconphoto(False, self.logo_photo)
            except Exception as e:
                print(f"[!] Lỗi nạp logo: {e}")

        self.client = WeSignClient()
        self.is_running = False
        self.stop_requested = False
        self.results = []

        self.setup_styles()
        self.build_ui()

        # Tự động kiểm tra kết nối
        self.root.after(500, self.async_test_connection)

    def center_window(self, width, height):
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, int((screen_w - width) / 2))
        y = max(0, int((screen_h - height) / 2) - 30)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use('vista' if 'vista' in style.theme_names() else 'clam')
        except Exception:
            pass

        self.font_title = ("Segoe UI", 12, "bold")
        self.font_bold = ("Segoe UI", 10, "bold")
        self.font_normal = ("Segoe UI", 10)
        self.font_small = ("Segoe UI", 9)
        self.font_mono = ("Consolas", 10)

        style.configure("Treeview", font=self.font_small, rowheight=26)
        style.configure("Treeview.Heading", font=self.font_bold)

    def build_ui(self):
        # 1. TOP HEADER BAR
        top_frame = tk.Frame(self.root, bg="#1E40AF", height=60)
        top_frame.pack(fill=tk.X, side=tk.TOP)

        header_container = tk.Frame(top_frame, bg="#1E40AF")
        header_container.pack(fill=tk.BOTH, expand=True, padx=16, pady=10)

        title_box = tk.Frame(header_container, bg="#1E40AF")
        title_box.pack(side=tk.LEFT)

        if self.logo_photo:
            lbl_logo = tk.Label(title_box, image=self.logo_photo, bg="#1E40AF", relief=tk.FLAT)
            lbl_logo.pack(side=tk.LEFT, padx=(0, 12))

        text_title_box = tk.Frame(title_box, bg="#1E40AF")
        text_title_box.pack(side=tk.LEFT)

        lbl_title = tk.Label(text_title_box, text="TOOL LẤY LINK HỢP ĐỒNG LAO ĐỘNG NHANH", font=("Segoe UI", 13, "bold"), fg="white", bg="#1E40AF")
        lbl_title.pack(anchor="w")
        lbl_sub = tk.Label(text_title_box, text="Tra cứu toàn bộ tài liệu & lấy link ký hợp đồng hàng loạt theo CCCD", font=("Segoe UI", 9), fg="#93C5FD", bg="#1E40AF")
        lbl_sub.pack(anchor="w")

        right_box = tk.Frame(header_container, bg="#1E40AF")
        right_box.pack(side=tk.RIGHT)

        self.lbl_conn_status = tk.Label(right_box, text="● Đang kiểm tra kết nối...", font=self.font_small, fg="#FDE047", bg="#1E40AF")
        self.lbl_conn_status.pack(side=tk.LEFT, padx=(0, 15))

        btn_test = tk.Button(right_box, text="🔄 Kiểm Tra", font=self.font_small, bg="#2563EB", fg="white",
                             activebackground="#1D4ED8", activeforeground="white", relief=tk.FLAT,
                             padx=10, pady=4, cursor="hand2", command=self.async_test_connection)
        btn_test.pack(side=tk.LEFT, padx=(0, 8))

        btn_settings = tk.Button(right_box, text="⚙️ Đổi Token & Cookie", font=("Segoe UI", 9, "bold"), bg="#F59E0B", fg="white",
                                 activebackground="#D97706", activeforeground="white", relief=tk.FLAT,
                                 padx=12, pady=4, cursor="hand2", command=self.open_settings_dialog)
        btn_settings.pack(side=tk.LEFT)

        # 2. MAIN BODY (PANED WINDOW 2 CỘT)
        main_paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=4, bg="#E2E8F0")
        main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # === CỘT TRÁI: NHẬP INPUT HÀNG LOẠT ===
        left_frame = tk.Frame(main_paned, bg="#F8FAFC", padx=10, pady=10)
        main_paned.add(left_frame, minsize=320, width=360)

        lbl_input_title = tk.Label(left_frame, text="DANH SÁCH CCCD CẦN TRA CỨU", font=self.font_bold, fg="#1E293B", bg="#F8FAFC")
        lbl_input_title.pack(anchor="w", pady=(0, 4))

        lbl_input_hint = tk.Label(left_frame, text="Nhập/dán mỗi số CCCD trên 1 dòng. Hệ thống sẽ tự tìm trên TOÀN BỘ các đợt/tài liệu WeSign:",
                                  font=self.font_small, fg="#64748B", bg="#F8FAFC", wraplength=340, justify="left")
        lbl_input_hint.pack(anchor="w", pady=(0, 8))

        # Thanh công cụ cho ô nhập
        tools_frame = tk.Frame(left_frame, bg="#F8FAFC")
        tools_frame.pack(fill=tk.X, pady=(0, 6))

        btn_import_file = tk.Button(tools_frame, text="📂 Nhập Excel/TXT", font=self.font_small, bg="#E2E8F0", fg="#1E293B",
                                    relief=tk.GROOVE, padx=8, pady=3, cursor="hand2", command=self.import_from_file)
        btn_import_file.pack(side=tk.LEFT, padx=(0, 6))

        btn_sample = tk.Button(tools_frame, text="Dán 5 mẫu", font=self.font_small, bg="#E2E8F0", fg="#1E293B",
                               relief=tk.GROOVE, padx=8, pady=3, cursor="hand2", command=self.insert_sample_cccd)
        btn_sample.pack(side=tk.LEFT, padx=(0, 6))

        btn_clear = tk.Button(tools_frame, text="Xóa", font=self.font_small, bg="#E2E8F0", fg="#DC2626",
                              relief=tk.GROOVE, padx=8, pady=3, cursor="hand2", command=self.clear_input_text)
        btn_clear.pack(side=tk.RIGHT)

        # Ô Text nhập danh sách CCCD
        text_container = tk.Frame(left_frame)
        text_container.pack(fill=tk.BOTH, expand=True)

        self.txt_cccd = tk.Text(text_container, font=self.font_mono, wrap=tk.NONE, relief=tk.SOLID, bd=1)
        txt_scroll_y = tk.Scrollbar(text_container, orient=tk.VERTICAL, command=self.txt_cccd.yview)
        self.txt_cccd.configure(yscrollcommand=txt_scroll_y.set)

        txt_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_cccd.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.txt_cccd.bind('<KeyRelease>', self.update_input_count)

        self.lbl_count = tk.Label(left_frame, text="Số lượng: 0 CCCD", font=self.font_small, fg="#2563EB", bg="#F8FAFC")
        self.lbl_count.pack(anchor="w", pady=(4, 8))

        # Tùy chọn độ trễ
        delay_frame = tk.Frame(left_frame, bg="#F8FAFC")
        delay_frame.pack(fill=tk.X, pady=(0, 10))

        tk.Label(delay_frame, text="Độ trễ mỗi request:", font=self.font_small, bg="#F8FAFC", fg="#475569").pack(side=tk.LEFT)
        self.delay_var = tk.StringVar(value="0.25")
        delay_combo = ttk.Combobox(delay_frame, textvariable=self.delay_var, values=["0.1", "0.25", "0.5", "1.0"], width=6, state="readonly")
        delay_combo.pack(side=tk.LEFT, padx=(6, 2))
        tk.Label(delay_frame, text="giây", font=self.font_small, bg="#F8FAFC", fg="#475569").pack(side=tk.LEFT)

        # Nút Bắt đầu và Dừng
        btn_box = tk.Frame(left_frame, bg="#F8FAFC")
        btn_box.pack(fill=tk.X, pady=(0, 4))

        self.btn_start = tk.Button(btn_box, text="🚀 BẮT ĐẦU LẤY LINK", font=("Segoe UI", 11, "bold"),
                                   bg="#16A34A", fg="white", activebackground="#15803D", activeforeground="white",
                                   relief=tk.FLAT, pady=8, cursor="hand2", command=self.start_processing)
        self.btn_start.pack(fill=tk.X)

        self.btn_stop = tk.Button(btn_box, text="⏹ DỪNG LẠI", font=("Segoe UI", 10, "bold"),
                                  bg="#DC2626", fg="white", activebackground="#B91C1C", activeforeground="white",
                                  relief=tk.FLAT, pady=6, cursor="hand2", command=self.stop_processing)

        # === CỘT PHẢI: BẢNG KẾT QUẢ & TIẾN TRÌNH ===
        right_frame = tk.Frame(main_paned, bg="#FFFFFF", padx=10, pady=10)
        main_paned.add(right_frame, minsize=550, width=780)

        prog_box = tk.Frame(right_frame, bg="#FFFFFF")
        prog_box.pack(fill=tk.X, pady=(0, 6))

        self.lbl_progress_status = tk.Label(prog_box, text="Sẵn sàng thực hiện", font=self.font_bold, fg="#1E293B", bg="#FFFFFF")
        self.lbl_progress_status.pack(side=tk.LEFT)

        self.lbl_stats = tk.Label(prog_box, text="Tổng: 0 | Thành công: 0 | Không tìm thấy: 0 | Lỗi: 0", font=self.font_small, fg="#64748B", bg="#FFFFFF")
        self.lbl_stats.pack(side=tk.RIGHT)

        self.prog_bar = ttk.Progressbar(right_frame, orient=tk.HORIZONTAL, mode='determinate')
        self.prog_bar.pack(fill=tk.X, pady=(0, 6))

        # Thanh lọc trạng thái
        filter_bar = tk.Frame(right_frame, bg="#FFFFFF")
        filter_bar.pack(fill=tk.X, pady=(0, 6))

        tk.Label(filter_bar, text="🔍 Lọc trạng thái:", font=self.font_small, bg="#FFFFFF", fg="#475569").pack(side=tk.LEFT, padx=(0, 6))
        self.filter_var = tk.StringVar(value="Tất cả kết quả")
        self.filter_combo = ttk.Combobox(
            filter_bar, textvariable=self.filter_var,
            values=["Tất cả kết quả", "🎉 Đã hoàn thành", "✍️ NLĐ đã ký", "👀 Đã xem", "⏳ Chưa xem", "❌ Không tìm thấy"],
            state="readonly", width=18
        )
        self.filter_combo.pack(side=tk.LEFT)
        self.filter_combo.bind("<<ComboboxSelected>>", self.on_filter_changed)

        btn_view_hist = tk.Button(filter_bar, text="🕒 Xem Lịch Sử Ký Chi Tiết", font=self.font_small, bg="#EEF2FF", fg="#4338CA",
                                  relief=tk.GROOVE, padx=10, pady=2, cursor="hand2", command=self.show_history_dialog)
        btn_view_hist.pack(side=tk.RIGHT)

        # Bảng kết quả (Treeview)
        tree_container = tk.Frame(right_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)

        columns = ("stt", "cccd", "name", "phone", "signing_state", "signed_time", "batch", "doc_name", "link")
        self.tree = ttk.Treeview(tree_container, columns=columns, show='headings', selectmode='browse')

        self.tree.heading("stt", text="STT")
        self.tree.heading("cccd", text="Số CCCD")
        self.tree.heading("name", text="Họ và Tên NLĐ")
        self.tree.heading("phone", text="Số ĐT / Zalo")
        self.tree.heading("signing_state", text="Tiến Độ Ký")
        self.tree.heading("signed_time", text="Thời Gian Ký")
        self.tree.heading("batch", text="Đợt / Lô Ký")
        self.tree.heading("doc_name", text="Tên Hợp Đồng Chi Tiết")
        self.tree.heading("link", text="Link Ký Hợp Đồng")

        self.tree.column("stt", width=40, minwidth=35, anchor="center")
        self.tree.column("cccd", width=110, minwidth=100, anchor="center")
        self.tree.column("name", width=130, minwidth=110, anchor="w")
        self.tree.column("phone", width=105, minwidth=95, anchor="center")
        self.tree.column("signing_state", width=110, minwidth=95, anchor="center")
        self.tree.column("signed_time", width=120, minwidth=100, anchor="center")
        self.tree.column("batch", width=130, minwidth=110, anchor="w")
        self.tree.column("doc_name", width=180, minwidth=130, anchor="w")
        self.tree.column("link", width=220, minwidth=160, anchor="w")

        tree_scroll_y = tk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.tree.yview)
        tree_scroll_x = tk.Scrollbar(tree_container, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)

        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        tree_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.setup_context_menu()

        # THANH CÔNG CỤ DƯỚI BẢNG KẾT QUẢ
        action_bar = tk.Frame(right_frame, bg="#FFFFFF")
        action_bar.pack(fill=tk.X, pady=(10, 0))

        btn_resend_all = tk.Button(action_bar, text="📨 Gửi Lại Cho NLĐ Chưa Ký", font=self.font_small,
                                   bg="#7C3AED", fg="white", activebackground="#6D28D9", activeforeground="white",
                                   relief=tk.FLAT, padx=12, pady=7, cursor="hand2", command=self.resend_pending_contracts)
        btn_resend_all.pack(side=tk.LEFT, padx=(0, 8))

        btn_zalo_all = tk.Button(action_bar, text="💬 Chép Tin Zalo Hàng Loạt", font=self.font_small,
                                 bg="#0284C7", fg="white", activebackground="#0369A1", activeforeground="white",
                                 relief=tk.FLAT, padx=12, pady=7, cursor="hand2", command=self.copy_bulk_zalo_messages)
        btn_zalo_all.pack(side=tk.LEFT, padx=(0, 8))

        btn_export = tk.Button(action_bar, text="📊 XUẤT FILE EXCEL (.xlsx)", font=("Segoe UI", 10, "bold"),
                               bg="#059669", fg="white", activebackground="#047857", activeforeground="white",
                               relief=tk.FLAT, padx=14, pady=7, cursor="hand2", command=self.export_excel)
        btn_export.pack(side=tk.LEFT, padx=(0, 8))

        btn_copy_all = tk.Button(action_bar, text="📋 Sao Chép Tất Cả Link", font=self.font_small,
                                 bg="#334155", fg="white", activebackground="#1E293B", activeforeground="white",
                                 relief=tk.FLAT, padx=12, pady=7, cursor="hand2", command=self.copy_all_links)
        btn_copy_all.pack(side=tk.LEFT, padx=(0, 6))

        btn_copy_only = tk.Button(action_bar, text="🔗 Chỉ Chép Link", font=self.font_small,
                                  bg="#F1F5F9", fg="#334155", activebackground="#E2E8F0", activeforeground="#0F172A",
                                  relief=tk.GROOVE, padx=10, pady=6, cursor="hand2", command=self.copy_only_links)
        btn_copy_only.pack(side=tk.LEFT, padx=(0, 8))

        btn_clear_results = tk.Button(action_bar, text="🗑 Xóa Bảng", font=self.font_small,
                                      bg="#F1F5F9", fg="#475569", relief=tk.GROOVE, padx=10, pady=6,
                                      cursor="hand2", command=self.clear_results)
        btn_clear_results.pack(side=tk.RIGHT)

    def setup_context_menu(self):
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="📨 Gửi Lại Hợp Đồng Cho NLĐ", command=self.resend_selected_contract)
        self.menu.add_separator()
        self.menu.add_command(label="💬 Mở Chat Zalo Với NLĐ", command=self.open_selected_zalo)
        self.menu.add_command(label="📋 Sao Chép Tin Nhắn Zalo", command=self.copy_selected_zalo_msg)
        self.menu.add_separator()
        self.menu.add_command(label="📋 Sao chép Link Ký", command=self.copy_selected_link)
        self.menu.add_command(label="🌐 Mở Link Trong Trình Duyệt", command=self.open_selected_link)
        self.menu.add_command(label="🕒 Xem Chi Tiết Lịch Sử Ký...", command=self.show_history_dialog)
        self.menu.add_separator()
        self.menu.add_command(label="📋 Sao chép Số CCCD", command=self.copy_selected_cccd)

        def show_menu(event):
            item = self.tree.identify_row(event.y)
            if item:
                self.tree.selection_set(item)
                self.menu.post(event.x_root, event.y_root)

        self.tree.bind("<Button-3>", show_menu)
        self.tree.bind("<Double-1>", lambda e: self.show_history_dialog())

    def update_input_count(self, event=None):
        text = self.txt_cccd.get("1.0", tk.END).strip()
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        self.lbl_count.config(text=f"Số lượng: {len(lines)} CCCD")

    def insert_sample_cccd(self):
        # 5 mẫu từ các đợt khác nhau (bao gồm đợt 99811838, đợt 601d8d36, đợt ff7b7049...)
        samples = [
            "036196013408",  # Đợt 99811838 (Phạm Thị Gấm)
            "038207014810",  # Đợt 601d8d36 (Trịnh Tuấn Anh)
            "014207009207",  # Đợt ff7b7049 (Lò Khánh Duy)
            "038207001582",  # Đợt ff7b7049 (Trần Văn Long)
            "017207002124"   # Đợt ff7b7049 (Phạm Việt Hùng)
        ]
        self.txt_cccd.delete("1.0", tk.END)
        self.txt_cccd.insert(tk.END, "\n".join(samples))
        self.update_input_count()

    def clear_input_text(self):
        self.txt_cccd.delete("1.0", tk.END)
        self.update_input_count()

    def clear_results(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.results = []
        self.lbl_stats.config(text="Tổng: 0 | Thành công: 0 | Không tìm thấy: 0 | Lỗi: 0")
        self.lbl_progress_status.config(text="Sẵn sàng thực hiện")
        self.prog_bar['value'] = 0

    def import_from_file(self):
        file_path = filedialog.askopenfilename(
            title="Chọn file chứa danh sách CCCD",
            filetypes=[("Excel & Text files", "*.xlsx *.xls *.csv *.txt"), ("All files", "*.*")]
        )
        if not file_path:
            return

        try:
            ext = os.path.splitext(file_path)[1].lower()
            if ext != '.txt' and not pd:
                messagebox.showwarning("Thiếu thư viện", "Chưa cài đặt thư viện 'pandas' và 'openpyxl' để đọc Excel.\nVui lòng chạy lệnh: pip install -r requirements.txt")
                return
            cccd_list = []
            if ext == '.txt':
                with open(file_path, 'r', encoding='utf-8') as f:
                    cccd_list = [l.strip() for l in f if l.strip()]
            else:
                if ext == '.csv':
                    df = pd.read_csv(file_path, dtype=str)
                else:
                    df = pd.read_excel(file_path, dtype=str)

                col = find_cccd_column(df)
                cccd_list = [str(x).strip() for x in df[col].dropna() if str(x).strip()]

            if cccd_list:
                self.txt_cccd.delete("1.0", tk.END)
                self.txt_cccd.insert(tk.END, "\n".join(cccd_list))
                self.update_input_count()
                messagebox.showinfo("Thành công", f"Đã nạp {len(cccd_list)} số CCCD từ file:\n{os.path.basename(file_path)}")
            else:
                messagebox.showwarning("Thông báo", "Không tìm thấy dữ liệu CCCD trong file đã chọn.")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không đọc được file: {str(e)}")

    def async_test_connection(self):
        self.lbl_conn_status.config(text="● Đang kiểm tra kết nối...", fg="#FDE047")
        threading.Thread(target=self._run_test_connection, daemon=True).start()

    def _run_test_connection(self):
        res = self.client.test_connection()
        if res.get('success'):
            total = res.get('total', 0)
            self.root.after(0, lambda: self.lbl_conn_status.config(
                text=f"● Đã kết nối: Có {total} tài liệu/đợt chờ xử lý", fg="#86EFAC"
            ))
        else:
            self.root.after(0, lambda: self.lbl_conn_status.config(
                text="● Chưa kết nối (Cần đổi Token/Cookie)", fg="#FCA5A5"
            ))

    def start_processing(self):
        text = self.txt_cccd.get("1.0", tk.END).strip()
        cccd_list = [l.strip() for l in text.split('\n') if l.strip()]
        if not cccd_list:
            messagebox.showwarning("Cảnh báo", "Vui lòng nhập hoặc dán ít nhất 1 số CCCD vào khung bên trái.")
            return

        try:
            delay = float(self.delay_var.get())
        except Exception:
            delay = 0.25

        self.is_running = True
        self.stop_requested = False
        self.clear_results()

        self.btn_start.pack_forget()
        self.btn_stop.pack(fill=tk.X)

        self.prog_bar['maximum'] = len(cccd_list)
        self.prog_bar['value'] = 0

        threading.Thread(target=self._process_worker, args=(cccd_list, delay), daemon=True).start()

    def stop_processing(self):
        if self.is_running:
            self.stop_requested = True
            self.lbl_progress_status.config(text="Đang dừng...")

    def _process_worker(self, cccd_list, delay):
        total = len(cccd_list)
        success_cnt = 0
        notfound_cnt = 0
        error_cnt = 0

        # Đồng bộ trước danh sách hợp đồng từ tất cả các đợt để tìm thấy 100% và tăng tốc độ
        self.root.after(0, lambda: self.lbl_progress_status.config(
            text="Đang đồng bộ toàn bộ các đợt tài liệu WeSign..."
        ))
        try:
            self.client.sync_all_contracts(force=True)
        except Exception:
            pass

        for idx, cccd in enumerate(cccd_list):
            if self.stop_requested:
                break

            self.root.after(0, lambda i=idx+1, c=cccd: self.lbl_progress_status.config(
                text=f"Đang tìm kiếm [{i}/{total}]: CCCD {c} trên các đợt tài liệu..."
            ))

            res = self.client.get_link_by_cccd(cccd)
            self.results.append(res)

            status = res.get('status')
            if status == 'success':
                success_cnt += 1
            elif status == 'not_found':
                notfound_cnt += 1
            else:
                error_cnt += 1

            self.root.after(0, lambda r=res, i=idx+1, s=success_cnt, n=notfound_cnt, e=error_cnt: self._on_item_finished(r, i, total, s, n, e))

            if idx < total - 1 and delay > 0 and not self.stop_requested:
                time.sleep(delay)

        self.root.after(0, self._on_process_complete)

    def _on_item_finished(self, res, current, total, s, n, e):
        self.prog_bar['value'] = current
        self.lbl_stats.config(text=f"Tổng: {total} | Thành công: {s} | Không tìm thấy: {n} | Lỗi: {e}")

        stt = current
        cccd = res.get('cccd', '')
        phone = res.get('phone', '') or '-'
        status = res.get('status')

        if status == 'success':
            name = res.get('worker_name', '')
            signing_state = res.get('signing_state', 'Chưa xem')
            signed_time = res.get('completed_time') or res.get('worker_signed_time') or res.get('worker_viewed_time') or '-'
            batch_name = res.get('batch_name', '')
            doc_name = res.get('doc_name', '')
            link_text = res.get('sign_link', '')

            if signing_state == 'Đã hoàn thành':
                tag = 'completed'
            elif signing_state == 'NLĐ đã ký':
                tag = 'signed'
            elif signing_state == 'Đã xem (Chưa ký)':
                tag = 'viewed'
            else:
                tag = 'notviewed'
        elif status == 'not_found':
            name = "-"
            signing_state = "Không thấy"
            signed_time = "-"
            batch_name = "-"
            doc_name = "-"
            link_text = "(Không tìm thấy)"
            tag = 'notfound'
        else:
            name = "-"
            signing_state = "Lỗi"
            signed_time = "-"
            batch_name = "-"
            doc_name = "-"
            link_text = res.get('message', 'Lỗi')
            tag = 'notfound'

        item_id = self.tree.insert("", tk.END, values=(stt, cccd, name, phone, signing_state, signed_time, batch_name, doc_name, link_text), tags=(tag,))

        self.tree.tag_configure('completed', foreground='#047857', font=("Segoe UI", 9, "bold"))
        self.tree.tag_configure('signed', foreground='#1D4ED8', font=("Segoe UI", 9, "bold"))
        self.tree.tag_configure('viewed', foreground='#B45309')
        self.tree.tag_configure('notviewed', foreground='#475569')
        self.tree.tag_configure('notfound', foreground='#DC2626')

        self.tree.see(item_id)

    def on_filter_changed(self, event=None):
        selected_filter = self.filter_var.get()
        for item in self.tree.get_children():
            self.tree.delete(item)

        for idx, res in enumerate(self.results):
            status = res.get('status')
            signing_state = res.get('signing_state', 'Chưa xem')

            show = False
            if selected_filter == "Tất cả kết quả":
                show = True
            elif selected_filter == "🎉 Đã hoàn thành" and signing_state == "Đã hoàn thành":
                show = True
            elif selected_filter == "✍️ NLĐ đã ký" and signing_state == "NLĐ đã ký":
                show = True
            elif selected_filter == "👀 Đã xem" and signing_state == "Đã xem (Chưa ký)":
                show = True
            elif selected_filter == "⏳ Chưa xem" and signing_state == "Chưa xem" and status == "success":
                show = True
            elif selected_filter == "❌ Không tìm thấy" and status == "not_found":
                show = True

            if not show:
                continue

            stt = idx + 1
            cccd = res.get('cccd', '')
            phone = res.get('phone', '') or '-'
            if status == 'success':
                name = res.get('worker_name', '')
                signed_time = res.get('completed_time') or res.get('worker_signed_time') or res.get('worker_viewed_time') or '-'
                batch_name = res.get('batch_name', '')
                doc_name = res.get('doc_name', '')
                link_text = res.get('sign_link', '')
                tag = 'completed' if signing_state == 'Đã hoàn thành' else ('signed' if signing_state == 'NLĐ đã ký' else ('viewed' if signing_state == 'Đã xem (Chưa ký)' else 'notviewed'))
            else:
                name = "-"
                signing_state = "Không thấy" if status == 'not_found' else "Lỗi"
                signed_time = "-"
                batch_name = "-"
                doc_name = "-"
                link_text = "(Không tìm thấy)" if status == 'not_found' else res.get('message', 'Lỗi')
                tag = 'notfound'

            self.tree.insert("", tk.END, values=(stt, cccd, name, phone, signing_state, signed_time, batch_name, doc_name, link_text), tags=(tag,))

    def show_history_dialog(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Thông báo", "Vui lòng chọn một dòng trên bảng kết quả để xem lịch sử ký.")
            return

        vals = self.tree.item(selected[0])['values']
        if len(vals) < 2:
            return

        cccd = str(vals[1])
        # Tìm item tương ứng trong results
        target_res = next((r for r in self.results if str(r.get('cccd', '')) == cccd), None)
        if not target_res or target_res.get('status') != 'success':
            messagebox.showwarning("Thông báo", "Không có dữ liệu hợp đồng cho số CCCD này.")
            return

        doc_id = target_res.get('doc_id')
        worker_name = target_res.get('worker_name', '')
        batch_name = target_res.get('batch_name', '')
        doc_name = target_res.get('doc_name', '')

        # Tạo popup cửa sổ xem lịch sử
        hist_win = tk.Toplevel(self.root)
        hist_win.title(f"Lịch Sử Ký Hợp Đồng - {worker_name} ({cccd})")
        hist_win.geometry("700x520")
        hist_win.minsize(580, 400)
        hist_win.configure(bg="#F8FAFC")

        # Header
        top_frame = tk.Frame(hist_win, bg="#1E40AF", padx=16, pady=12)
        top_frame.pack(fill=tk.X)

        tk.Label(top_frame, text=f"LỊCH SỬ KÝ: {worker_name.upper()}", font=("Segoe UI", 12, "bold"), fg="white", bg="#1E40AF").pack(anchor="w")
        tk.Label(top_frame, text=f"CCCD: {cccd} | Đợt ký: {batch_name}", font=self.font_small, fg="#93C5FD", bg="#1E40AF").pack(anchor="w", pady=(2, 0))

        # Khung trạng thái
        status_bar = tk.Frame(hist_win, bg="#EFF6FF", padx=14, pady=8, bd=1, relief=tk.SOLID)
        status_bar.pack(fill=tk.X, padx=14, pady=(10, 6))

        signing_state = target_res.get('signing_state', 'Chưa rõ')
        tk.Label(status_bar, text=f"Tiến độ hiện tại: {signing_state}", font=("Segoe UI", 10, "bold"), fg="#1E40AF", bg="#EFF6FF").pack(side=tk.LEFT)

        if target_res.get('worker_signed_time'):
            tk.Label(status_bar, text=f"| NLĐ ký: {target_res.get('worker_signed_time')}", font=self.font_small, fg="#047857", bg="#EFF6FF").pack(side=tk.LEFT, padx=8)
        if target_res.get('completed_time'):
            tk.Label(status_bar, text=f"| Hoàn tất: {target_res.get('completed_time')}", font=self.font_small, fg="#047857", bg="#EFF6FF").pack(side=tk.LEFT, padx=8)

        # Bảng Timeline các sự kiện
        table_frame = tk.Frame(hist_win, bg="#F8FAFC", padx=14, pady=4)
        table_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("time", "action", "user", "email")
        t_tree = ttk.Treeview(table_frame, columns=cols, show='headings')
        t_tree.heading("time", text="Thời Gian")
        t_tree.heading("action", text="Hành Động / Sự Kiện")
        t_tree.heading("user", text="Người Thực Hiện")
        t_tree.heading("email", text="Email")

        t_tree.column("time", width=140, anchor="center")
        t_tree.column("action", width=150, anchor="w")
        t_tree.column("user", width=160, anchor="w")
        t_tree.column("email", width=180, anchor="w")

        sc_y = tk.Scrollbar(table_frame, orient=tk.VERTICAL, command=t_tree.yview)
        t_tree.configure(yscrollcommand=sc_y.set)
        sc_y.pack(side=tk.RIGHT, fill=tk.Y)
        t_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Lấy events đã lưu sẵn trong target_res, nếu chưa có thì gọi API
        events = target_res.get('history_events')
        if not events and doc_id:
            h_info = self.client.get_document_history(doc_id, worker_name)
            events = h_info.get('events', [])

        if events:
            for ev in events:
                t_tree.insert("", tk.END, values=(
                    ev.get('time', ''),
                    ev.get('action_text', ''),
                    ev.get('user_name', ''),
                    ev.get('user_email', '')
                ))
        else:
            t_tree.insert("", tk.END, values=("-", "Chưa ghi nhận sự kiện nào", "-", "-"))

        btn_close = tk.Button(hist_win, text="Đóng", font=self.font_small, bg="#E2E8F0", fg="#1E293B",
                              relief=tk.FLAT, padx=16, pady=5, cursor="hand2", command=hist_win.destroy)
        btn_close.pack(pady=8)

    def _on_process_complete(self):
        self.is_running = False
        self.btn_stop.pack_forget()
        self.btn_start.pack(fill=tk.X)

        if self.stop_requested:
            self.lbl_progress_status.config(text="Đã tạm dừng quá trình lấy link.")
            messagebox.showinfo("Thông báo", "Đã tạm dừng quá trình tra cứu.")
        else:
            self.lbl_progress_status.config(text="Hoàn thành tất cả!")
            messagebox.showinfo("Hoàn thành", f"Đã tra cứu xong {len(self.results)} số CCCD!\nBạn có thể bấm 'Xuất File Excel' để lưu kết quả.")

    def copy_selected_link(self):
        selected = self.tree.selection()
        if not selected:
            return
        vals = self.tree.item(selected[0])['values']
        if len(vals) >= 9:
            link = str(vals[8])
            if link.startswith('http'):
                self.root.clipboard_clear()
                self.root.clipboard_append(link)
                self.root.update()
                messagebox.showinfo("Đã sao chép", f"Đã chép link ký của {vals[2]} vào bộ nhớ tạm!")

    def open_selected_link(self):
        selected = self.tree.selection()
        if not selected:
            return
        vals = self.tree.item(selected[0])['values']
        if len(vals) >= 9:
            link = str(vals[8])
            if link.startswith('http'):
                webbrowser.open(link)

    def open_selected_zalo(self):
        selected = self.tree.selection()
        if not selected:
            return
        vals = self.tree.item(selected[0])['values']
        phone = str(vals[3]).strip()
        if not phone or phone == '-':
            messagebox.showwarning("Thông báo", f"Không tìm thấy số điện thoại của {vals[2]} để mở Zalo.")
            return
        zalo_url = f"https://zalo.me/{phone}"
        webbrowser.open(zalo_url)

    def copy_selected_zalo_msg(self):
        selected = self.tree.selection()
        if not selected:
            return
        vals = self.tree.item(selected[0])['values']
        cccd = str(vals[1])
        r = next((x for x in self.results if str(x.get('cccd')) == cccd), None)
        if not r or not r.get('sign_link'):
            messagebox.showwarning("Thông báo", "Không có link ký hợp lệ để tạo tin nhắn.")
            return
        name = r.get('worker_name', vals[2])
        phone = r.get('phone', '')
        link = r.get('sign_link', '')
        msg = f"Kính gửi Anh/Chị {name},\nCông ty gửi lại Anh/Chị đường link ký Hợp đồng lao động điện tử:\n👉 {link}\nAnh/Chị vui lòng bấm vào link trên để kiểm tra thông tin và ký xác nhận sớm giúp công ty nhé. Trân trọng!"
        self.root.clipboard_clear()
        self.root.clipboard_append(msg)
        self.root.update()
        messagebox.showinfo("Đã sao chép", f"Đã sao chép tin nhắn Zalo kèm link ký của {name}!")

    def copy_bulk_zalo_messages(self):
        pending = [r for r in self.results if r.get('status') == 'success' and r.get('signing_state') != 'Đã hoàn thành' and r.get('sign_link')]
        if not pending:
            messagebox.showwarning("Thông báo", "Không có NLĐ nào đang chờ ký để tạo tin nhắn Zalo.")
            return
        msgs = []
        for r in pending:
            name = r.get('worker_name', '')
            phone = r.get('phone', '')
            link = r.get('sign_link', '')
            phone_info = f" (SĐT: {phone} - Zalo: https://zalo.me/{phone})" if phone else ""
            msgs.append(f"--- [Gửi cho: {name}{phone_info}] ---\nKính gửi Anh/Chị {name},\nCông ty gửi đường link ký Hợp đồng lao động điện tử:\n👉 {link}\nAnh/Chị vui lòng bấm vào link trên để ký xác nhận nhé.\n")
        text_all = "\n".join(msgs)
        self.root.clipboard_clear()
        self.root.clipboard_append(text_all)
        self.root.update()
        messagebox.showinfo("Đã sao chép", f"Đã sao chép danh sách tin nhắn Zalo cho {len(pending)} người lao động chưa hoàn tất ký!")

    def copy_selected_cccd(self):
        selected = self.tree.selection()
        if not selected:
            return
        vals = self.tree.item(selected[0])['values']
        if len(vals) >= 2:
            cccd = str(vals[1])
            self.root.clipboard_clear()
            self.root.clipboard_append(cccd)
            self.root.update()
            messagebox.showinfo("Đã sao chép", f"Đã chép CCCD {cccd} vào bộ nhớ tạm!")

    def copy_all_links(self):
        valid = [r for r in self.results if r.get('status') == 'success' and r.get('sign_link')]
        if not valid:
            messagebox.showwarning("Thông báo", "Chưa có link ký hợp lệ nào để sao chép.")
            return

        lines = [f"{r.get('cccd')}\t{r.get('worker_name')}\t{r.get('phone', '')}\t{r.get('zalo_link', '')}\t{r.get('signing_state', '-')}\t{r.get('batch_name')}\t{r.get('sign_link')}" for r in valid]
        text_all = "\n".join(lines)
        self.root.clipboard_clear()
        self.root.clipboard_append(text_all)
        self.root.update()
        messagebox.showinfo("Đã sao chép", f"Đã sao chép toàn bộ {len(valid)} dòng vào bộ nhớ tạm (dạng bảng: CCCD | Họ tên | SĐT | Link Zalo | Tiến độ ký | Đợt ký | Link Ký)!")

    def copy_only_links(self):
        valid = [r for r in self.results if r.get('status') == 'success' and r.get('sign_link')]
        if not valid:
            messagebox.showwarning("Thông báo", "Chưa có link ký hợp lệ nào để sao chép.")
            return

        lines = [str(r.get('sign_link')) for r in valid]
        text_all = "\n".join(lines)
        self.root.clipboard_clear()
        self.root.clipboard_append(text_all)
        self.root.update()
        messagebox.showinfo("Đã sao chép", f"Đã sao chép {len(valid)} link ký URL vào bộ nhớ tạm!")

    def resend_selected_contract(self):
        selected = self.tree.selection()
        if not selected:
            return
        vals = self.tree.item(selected[0])['values']
        cccd = str(vals[1])
        target_res = next((r for r in self.results if str(r.get('cccd', '')) == cccd), None)
        if not target_res or not target_res.get('doc_id'):
            messagebox.showwarning("Thông báo", "Không tìm thấy mã hợp đồng để gửi lại.")
            return

        worker_name = target_res.get('worker_name', cccd)
        if not messagebox.askyesno("Xác nhận", f"Bạn có chắc muốn gửi lại thông báo ký hợp đồng cho '{worker_name}' qua AMIS WeSign?"):
            return

        doc_id = target_res.get('doc_id')
        res = self.client.resend_documents(doc_id)
        if res.get('success'):
            messagebox.showinfo("Thành công", f"Đã gửi lại hợp đồng thành công cho {worker_name}!")
        else:
            messagebox.showerror("Thất bại", res.get('message', 'Không thể gửi lại hợp đồng.'))

    def resend_pending_contracts(self):
        pending = [r for r in self.results if r.get('status') == 'success' and r.get('doc_id') and r.get('signing_state') != 'Đã hoàn thành']
        if not pending:
            messagebox.showinfo("Thông báo", "Không có người lao động nào chưa hoàn thành ký để gửi lại.")
            return

        if not messagebox.askyesno("Xác nhận", f"Hệ thống tìm thấy {len(pending)} NLĐ chưa hoàn thành ký.\nBạn có chắc muốn gửi lại thông báo ký cho toàn bộ {len(pending)} người này qua AMIS WeSign?"):
            return

        doc_ids = [r['doc_id'] for r in pending]
        res = self.client.resend_documents(doc_ids)
        if res.get('success'):
            messagebox.showinfo("Thành công", f"Đã gửi lại hợp đồng thành công cho toàn bộ {len(doc_ids)} người lao động!")
        else:
            messagebox.showerror("Thất bại", res.get('message', 'Lỗi khi gửi lại hợp đồng hàng loạt.'))

    def export_excel(self):
        if not self.results:
            messagebox.showwarning("Thông báo", "Chưa có dữ liệu để xuất Excel.")
            return

        if not pd or not HAS_OPENPYXL:
            messagebox.showwarning("Thiếu thư viện", "Chưa cài đặt thư viện 'openpyxl' và 'pandas' để xuất Excel.\nVui lòng chạy lệnh: pip install -r requirements.txt")
            return

        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"Danh_Sach_Link_Ky_{now_str}.xlsx"

        out_path = filedialog.asksaveasfilename(
            title="Lưu file Excel kết quả",
            defaultextension=".xlsx",
            initialfile=default_name,
            filetypes=[("Excel files", "*.xlsx")]
        )
        if not out_path:
            return

        try:
            export_rows = []
            for idx, r in enumerate(self.results):
                stt = idx + 1
                cccd = r.get('cccd', '')
                status = r.get('status')
                if status == 'success':
                    status_lbl = "Thành công"
                    worker_name = r.get('worker_name', '')
                    position = r.get('job_position', '')
                    batch_name = r.get('batch_name', '')
                    doc_name = r.get('doc_name', '')
                    doc_status = r.get('doc_status', '')
                    sign_link = r.get('sign_link', '')
                    signing_state = r.get('signing_state', 'Chưa rõ')
                    worker_signed_time = r.get('worker_signed_time', '-')
                    completed_time = r.get('completed_time', '-')
                    worker_viewed_time = r.get('worker_viewed_time', '-')
                    note = "Sẵn sàng ký"
                elif status == 'not_found':
                    status_lbl = "Không tìm thấy"
                    worker_name = ""
                    position = ""
                    batch_name = ""
                    doc_name = ""
                    doc_status = ""
                    sign_link = ""
                    signing_state = "Không tìm thấy"
                    worker_signed_time = "-"
                    completed_time = "-"
                    worker_viewed_time = "-"
                    note = r.get('message', 'Không tìm thấy hợp đồng')
                else:
                    status_lbl = "Lỗi"
                    worker_name = ""
                    position = ""
                    batch_name = ""
                    doc_name = ""
                    doc_status = ""
                    sign_link = ""
                    signing_state = "Lỗi"
                    worker_signed_time = "-"
                    completed_time = "-"
                    worker_viewed_time = "-"
                    note = r.get('message', 'Lỗi API')

                export_rows.append({
                    "STT": stt,
                    "Số CCCD": cccd,
                    "Họ và Tên NLĐ": worker_name,
                    "Số ĐT NLĐ": r.get('phone', ''),
                    "Link Chat Zalo": r.get('zalo_link', f"https://zalo.me/{r.get('phone')}" if r.get('phone') else ''),
                    "Chức Vụ": position,
                    "Đợt Ký / Lô Hợp Đồng": batch_name,
                    "Tiến Độ Ký (Lịch Sử)": signing_state,
                    "Thời Gian NLĐ Ký": worker_signed_time,
                    "Thời Gian Hoàn Tất": completed_time,
                    "Thời Gian NLĐ Xem": worker_viewed_time,
                    "Tên Hợp Đồng Chi Tiết": doc_name,
                    "Trạng Thái Văn Bản": doc_status,
                    "Trạng Thái Tra Cứu": status_lbl,
                    "Link Ký Hợp Đồng": sign_link,
                    "Ghi Chú": note
                })

            df = pd.DataFrame(export_rows)

            with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='DanhSachLinkKy')
                ws = writer.sheets['DanhSachLinkKy']

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
                    cell.alignment = Alignment(horizontal="center", vertical="center")

                # Định dạng dữ liệu
                for row_idx in range(2, len(df) + 2):
                    ws.row_dimensions[row_idx].height = 22
                    for col_idx in range(1, len(df.columns) + 1):
                        cell = ws.cell(row=row_idx, column=col_idx)
                        cell.border = thin_border
                        cell.font = Font(name="Calibri", size=10)

                        # Căn giữa STT, CCCD, Trạng thái
                        if col_idx in [1, 2, 7, 8]:
                            cell.alignment = Alignment(horizontal="center", vertical="center")
                        else:
                            cell.alignment = Alignment(vertical="center")

                        # Cột Link Ký Hợp Đồng (cột 9) có hyperlink click mở ngay
                        if col_idx == 9 and cell.value and str(cell.value).startswith('http'):
                            cell.font = Font(name="Calibri", size=10, color="2563EB", underline="single")
                            cell.hyperlink = cell.value

                for col in ws.columns:
                    max_len = max(len(str(cell.value or '')) for cell in col)
                    col_letter = get_column_letter(col[0].column)
                    ws.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 65)

            messagebox.showinfo("Thành công", f"Đã xuất file Excel thành công!\n{out_path}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể xuất file Excel: {str(e)}")

    # ================= HỘP THOẠI CÀI ĐẶT TOKEN & COOKIE =================
    def open_settings_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Cài Đặt Token & Cookie AMIS WeSign")
        dlg.geometry("780x600")
        dlg.transient(self.root)
        dlg.grab_set()

        dlg.update_idletasks()
        dw = 780
        dh = 600
        dx = max(0, int((self.root.winfo_screenwidth() - dw) / 2))
        dy = max(0, int((self.root.winfo_screenheight() - dh) / 2) - 20)
        dlg.geometry(f"{dw}x{dh}+{dx}+{dy}")

        cfg = self.client.load_config()

        # KHUNG 1: DÁN NHANH CURL (Hỗ trợ cả paging/data và batch-data)
        box_curl = tk.LabelFrame(dlg, text=" ⚡ Cập Nhật Nhanh Bằng Câu Lệnh cURL (Khuyên Dùng) ",
                                 font=self.font_bold, fg="#B45309", padx=10, pady=8)
        box_curl.pack(fill=tk.X, padx=12, pady=(10, 8))

        lbl_curl_hint = tk.Label(box_curl, text="Bật F12 trên WeSign -> Thẻ Network -> Chuột phải vào request bất kỳ (paging/data hoặc batch-data) -> Copy as cURL -> Dán vào đây:",
                                 font=self.font_small, fg="#64748B", justify="left")
        lbl_curl_hint.pack(anchor="w", pady=(0, 4))

        txt_curl = tk.Text(box_curl, height=4, font=self.font_mono, relief=tk.SOLID, bd=1)
        txt_curl.pack(fill=tk.X, pady=(0, 6))

        def parse_and_fill():
            curl_text = txt_curl.get("1.0", tk.END).strip()
            if not curl_text:
                messagebox.showwarning("Cảnh báo", "Vui lòng dán câu lệnh cURL vào ô.")
                return
            res = parse_curl_command(curl_text)
            if not res or not (res.get('token') or res.get('cookie')):
                messagebox.showerror("Lỗi", "Không tìm thấy Token hoặc Cookie hợp lệ trong cURL.")
                return

            if res.get('token'):
                ent_token.delete("1.0", tk.END)
                ent_token.insert(tk.END, res['token'])
            if res.get('cookie'):
                ent_cookie.delete("1.0", tk.END)
                ent_cookie.insert(tk.END, res['cookie'])
            if res.get('tenant_id'):
                ent_tenant.delete(0, tk.END)
                ent_tenant.insert(0, res['tenant_id'])
            if res.get('document_batch_id'):
                ent_batch.delete(0, tk.END)
                ent_batch.insert(0, res['document_batch_id'])

            messagebox.showinfo("Thành công", "Đã tự động trích xuất Token và Cookie thành công!\nBấm 'LƯU CẤU HÌNH' để áp dụng.")

        btn_parse = tk.Button(box_curl, text="⚡ Phân Tích & Tự Động Điền", font=self.font_small,
                              bg="#F59E0B", fg="white", activebackground="#D97706", activeforeground="white",
                              relief=tk.FLAT, padx=10, pady=4, cursor="hand2", command=parse_and_fill)
        btn_parse.pack(anchor="w")

        # KHUNG 2: CHI TIẾT CÁC TRƯỜNG CẤU HÌNH
        box_fields = tk.LabelFrame(dlg, text=" 📝 Chỉnh Sửa Chi Tiết ", font=self.font_bold, fg="#1E293B", padx=10, pady=8)
        box_fields.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))

        tk.Label(box_fields, text="Authorization Bearer Token:", font=self.font_small, fg="#334155").pack(anchor="w")
        ent_token = tk.Text(box_fields, height=3, font=self.font_mono, relief=tk.SOLID, bd=1)
        ent_token.pack(fill=tk.X, pady=(2, 6))
        ent_token.insert(tk.END, cfg.get('token', ''))

        tk.Label(box_fields, text="Cookie chuỗi (Bao gồm cf_clearance, x-sessionid, ...):", font=self.font_small, fg="#334155").pack(anchor="w")
        ent_cookie = tk.Text(box_fields, height=3, font=self.font_mono, relief=tk.SOLID, bd=1)
        ent_cookie.pack(fill=tk.X, pady=(2, 6))
        ent_cookie.insert(tk.END, cfg.get('cookie', ''))

        grid_frame = tk.Frame(box_fields)
        grid_frame.pack(fill=tk.X, pady=(2, 6))

        tk.Label(grid_frame, text="Tenant ID:", font=self.font_small, fg="#334155").grid(row=0, column=0, sticky="w", padx=(0, 10))
        ent_tenant = tk.Entry(grid_frame, font=self.font_mono, relief=tk.SOLID, bd=1)
        ent_tenant.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        ent_tenant.insert(0, cfg.get('tenant_id', ''))

        tk.Label(grid_frame, text="Batch ID Mặc định (Tùy chọn):", font=self.font_small, fg="#334155").grid(row=0, column=1, sticky="w")
        ent_batch = tk.Entry(grid_frame, font=self.font_mono, relief=tk.SOLID, bd=1)
        ent_batch.grid(row=1, column=1, sticky="ew")
        ent_batch.insert(0, cfg.get('document_batch_id', ''))

        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)

        btn_box = tk.Frame(dlg, padx=12, pady=10)
        btn_box.pack(fill=tk.X, side=tk.BOTTOM)

        def save_and_close():
            new_cfg = {
                "token": ent_token.get("1.0", tk.END).strip(),
                "cookie": ent_cookie.get("1.0", tk.END).strip(),
                "tenant_id": ent_tenant.get().strip(),
                "document_batch_id": ent_batch.get().strip()
            }
            self.client.save_config(new_cfg)
            messagebox.showinfo("Đã lưu", "Đã lưu cấu hình mới thành công!")
            dlg.destroy()
            self.async_test_connection()

        def test_in_dialog():
            temp_cfg = {
                "token": ent_token.get("1.0", tk.END).strip(),
                "cookie": ent_cookie.get("1.0", tk.END).strip(),
                "tenant_id": ent_tenant.get().strip(),
                "document_batch_id": ent_batch.get().strip()
            }
            self.client.save_config(temp_cfg)
            res = self.client.test_connection()
            if res.get('success'):
                messagebox.showinfo("Thành công", f"{res.get('message')}")
            else:
                messagebox.showerror("Thất bại", f"{res.get('message')}")

        btn_save = tk.Button(btn_box, text="💾 LƯU CẤU HÌNH", font=self.font_bold, bg="#1E40AF", fg="white",
                             activebackground="#1D4ED8", activeforeground="white", relief=tk.FLAT,
                             padx=16, pady=6, cursor="hand2", command=save_and_close)
        btn_save.pack(side=tk.RIGHT, padx=(8, 0))

        btn_test_dialog = tk.Button(btn_box, text="🔄 Kiểm Tra Kết Nối", font=self.font_small,
                                    bg="#E2E8F0", fg="#1E293B", relief=tk.GROOVE, padx=12, pady=6,
                                    cursor="hand2", command=test_in_dialog)
        btn_test_dialog.pack(side=tk.RIGHT)

        btn_cancel = tk.Button(btn_box, text="Đóng", font=self.font_small, bg="#F1F5F9", fg="#475569",
                               relief=tk.GROOVE, padx=10, pady=6, cursor="hand2", command=dlg.destroy)
        btn_cancel.pack(side=tk.LEFT)

def main():
    root = tk.Tk()
    app = WeSignGUIApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()
