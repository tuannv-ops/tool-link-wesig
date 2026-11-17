import sys
import os
import argparse
import time
import pandas as pd
from wesign_api import WeSignClient

def find_cccd_column(df):
    """Tự động tìm cột chứa CCCD trong dataframe"""
    keywords = ['cccd', 'cmnd', 'căn cước', 'can cuoc', 'dinh danh', 'định danh', 'so_cccd', 'socccd', 'id']
    for col in df.columns:
        col_lower = str(col).lower().strip()
        for kw in keywords:
            if kw in col_lower:
                return col
    # Kiểm tra dữ liệu mẫu (chuỗi số 9-12 chữ số)
    for col in df.columns:
        sample_vals = df[col].dropna().astype(str).head(10)
        digits_count = sum(1 for v in sample_vals if v.strip().isdigit() and len(v.strip()) in [9, 12])
        if digits_count >= max(1, len(sample_vals) // 2):
            return col
    return df.columns[0]

def process_single(client, cccd):
    print(f"\n[+] Đang tra cứu số CCCD: {cccd} trên toàn hệ thống WeSign...")
    res = client.get_link_by_cccd(cccd)
    if res.get('status') == 'success':
        print("\n" + "="*70)
        print("  KẾT QUẢ TRA CỨU HỢP ĐỒNG THÀNH CÔNG")
        print("="*70)
        print(f"  * Số CCCD       : {res.get('cccd')}")
        print(f"  * Người lao động: {res.get('worker_name')}")
        print(f"  * Chức vụ       : {res.get('job_position')}")
        print(f"  * Đợt / Lô ký   : {res.get('batch_name')}")
        print(f"  * Trạng thái ký : {res.get('doc_status')}")
        print(f"  * Tên hợp đồng  : {res.get('doc_name')}")
        print(f"  * Link ký       : {res.get('sign_link')}")
        print("="*70)
    elif res.get('status') == 'not_found':
        print(f"\n[-] Không tìm thấy hợp đồng cho CCCD: {cccd}")
    else:
        print(f"\n[!] Lỗi: {res.get('message')}")
    return res

def process_excel(client, input_path, output_path=None, col_name=None, delay=0.25):
    if not os.path.exists(input_path):
        print(f"[!] Không tìm thấy file: {input_path}")
        return

    print(f"[+] Đang đọc file: {input_path}...")
    if input_path.endswith('.csv'):
        df = pd.read_csv(input_path, dtype=str)
    else:
        df = pd.read_excel(input_path, dtype=str)

    if not col_name:
        col_name = find_cccd_column(df)
        print(f"[+] Tự động chọn cột CCCD: '{col_name}'")
    else:
        if col_name not in df.columns:
            print(f"[!] Cột '{col_name}' không tồn tại trong file. Các cột hiện có: {list(df.columns)}")
            return

    df[col_name] = df[col_name].fillna('').astype(str).str.strip()
    total = len(df)
    print(f"[+] Tổng số dòng cần xử lý: {total}")

    worker_names = []
    job_positions = []
    batch_names = []
    doc_names = []
    sign_links = []
    signing_states = []
    signed_times = []
    completed_times = []
    viewed_times = []
    statuses = []
    notes = []

    success_count = 0
    not_found_count = 0
    error_count = 0

    print("-" * 70)
    for idx, row in df.iterrows():
        cccd = row[col_name]
        if not cccd:
            worker_names.append("")
            job_positions.append("")
            batch_names.append("")
            doc_names.append("")
            sign_links.append("")
            signing_states.append("")
            signed_times.append("")
            completed_times.append("")
            viewed_times.append("")
            statuses.append("Bỏ qua")
            notes.append("CCCD trống")
            continue

        res = client.get_link_by_cccd(cccd)
        status = res.get('status')
        if status == 'success':
            success_count += 1
            w_name = res.get('worker_name', '')
            link = res.get('sign_link', '')
            state = res.get('signing_state', 'Chưa rõ')
            worker_names.append(w_name)
            job_positions.append(res.get('job_position', ''))
            batch_names.append(res.get('batch_name', ''))
            doc_names.append(res.get('doc_name', ''))
            sign_links.append(link)
            signing_states.append(state)
            signed_times.append(res.get('worker_signed_time', '-'))
            completed_times.append(res.get('completed_time', '-'))
            viewed_times.append(res.get('worker_viewed_time', '-'))
            statuses.append("Thành công")
            notes.append(res.get('doc_status', ''))
            print(f"[{idx+1}/{total}] OK: {cccd} - {w_name} | {state} ({res.get('batch_name', '')})")
        elif status == 'not_found':
            not_found_count += 1
            worker_names.append("")
            job_positions.append("")
            batch_names.append("")
            doc_names.append("")
            sign_links.append("")
            signing_states.append("Không tìm thấy")
            signed_times.append("-")
            completed_times.append("-")
            viewed_times.append("-")
            statuses.append("Không tìm thấy")
            notes.append(res.get('message', ''))
            print(f"[{idx+1}/{total}] Không tìm thấy: {cccd}")
        else:
            error_count += 1
            worker_names.append("")
            job_positions.append("")
            batch_names.append("")
            doc_names.append("")
            sign_links.append("")
            signing_states.append("Lỗi")
            signed_times.append("-")
            completed_times.append("-")
            viewed_times.append("-")
            statuses.append("Lỗi")
            notes.append(res.get('message', ''))
            print(f"[{idx+1}/{total}] LỖI: {cccd} - {res.get('message')}")

        if idx < total - 1 and delay > 0:
            time.sleep(delay)

    df['Họ và tên NLĐ'] = worker_names
    df['Chức vụ'] = job_positions
    df['Đợt ký / Lô HĐ'] = batch_names
    df['Tiến độ ký (Lịch sử)'] = signing_states
    df['Thời gian NLĐ ký'] = signed_times
    df['Thời gian hoàn tất'] = completed_times
    df['Thời gian NLĐ xem'] = viewed_times
    df['Tên hợp đồng'] = doc_names
    df['Link ký hợp đồng'] = sign_links
    df['Trạng thái tra cứu'] = statuses
    df['Ghi chú'] = notes

    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_KetQuaTraCuu.xlsx"

    print(f"\n[+] Đang lưu kết quả vào: {output_path}...")
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='KetQuaTraCuu')

    print("=" * 70)
    print("HOÀN THÀNH!")
    print(f"  * Tổng số: {total}")
    print(f"  * Thành công: {success_count}")
    print(f"  * Không tìm thấy: {not_found_count}")
    print(f"  * Lỗi: {error_count}")
    print(f"  * File kết quả: {output_path}")
    print("=" * 70)

def main():
    parser = argparse.ArgumentParser(description="Tra cứu link ký hợp đồng AMIS WeSign toàn hệ thống theo số CCCD")
    parser.add_argument('cccd', nargs='?', help="Số CCCD cần tra cứu nhanh")
    parser.add_argument('--file', '-f', help="Đường dẫn file txt/csv/excel chứa danh sách CCCD")
    parser.add_argument('--col', '-c', help="Tên cột chứa CCCD trong file Excel")
    parser.add_argument('--output', '-o', help="Đường dẫn file Excel xuất kết quả")
    parser.add_argument('--delay', '-d', type=float, default=0.25, help="Độ trễ giữa các request (giây)")
    parser.add_argument('--test', action='store_true', help="Kiểm tra kết nối và token WeSign")

    args = parser.parse_args()
    client = WeSignClient()

    if args.test:
        print("[+] Đang kiểm tra kết nối tới AMIS WeSign...")
        res = client.test_connection()
        if res.get('success'):
            print(f"[OK] {res.get('message')}")
        else:
            print(f"[LỖI] {res.get('message')}")
        return

    if args.cccd:
        process_single(client, args.cccd)
        return

    if args.file:
        ext = os.path.splitext(args.file)[1].lower()
        if ext in ['.xlsx', '.xls', '.csv']:
            process_excel(client, args.file, args.output, args.col, args.delay)
        else:
            with open(args.file, 'r', encoding='utf-8') as f:
                lines = [l.strip() for l in f if l.strip()]
            print(f"[+] Tìm thấy {len(lines)} CCCD trong file text.")
            results = client.get_links_batch(lines, delay=args.delay)
            df = pd.DataFrame(results)
            out_file = args.output or "KetQuaTraCuu.xlsx"
            df.to_excel(out_file, index=False)
            print(f"[+] Đã lưu kết quả ra: {out_file}")
        return

    parser.print_help()

if __name__ == '__main__':
    main()
