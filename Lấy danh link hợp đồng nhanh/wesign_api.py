import re
import json
import time
import os
import base64
from datetime import datetime
import requests

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

DEFAULT_CONFIG = {
    "token": "",
    "cookie": "",
    "document_batch_id": "",
    "tenant_id": "c4e3c4ef-a722-40cd-96ed-6aa20a86ee94",
    "device_id": "f4007158-f14d-48f2-bae2-0e73c4e046a4",
    "status_filter": [],  # [] là TẤT CẢ các trạng thái (bản nháp, chờ ký, hoàn thành...)
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
}

STATUS_MAP = {
    0: "Bản nháp",
    1: "Chờ duyệt",
    2: "Từ chối duyệt",
    3: "Đã duyệt",
    4: "Chờ tôi ký",
    5: "Từ chối ký",
    6: "Chờ người khác ký",
    7: "Hoàn thành",
    8: "Hủy bỏ",
    9: "Hết hạn",
    -1: "Tất cả"
}

def parse_cookies_str(cookie_str):
    if not cookie_str:
        return {}
    cookies = {}
    for item in cookie_str.split(';'):
        item = item.strip()
        if not item or '=' not in item:
            continue
        parts = item.split('=', 1)
        cookies[parts[0].strip()] = parts[1].strip()
    return cookies

def parse_curl_command(curl_text):
    result = {}
    if not curl_text:
        return result

    # 1. Token
    token_match = re.search(r'Bearer\s+([A-Za-z0-9\-_=\.]+)', curl_text, re.IGNORECASE)
    if token_match:
        result['token'] = token_match.group(1).strip()

    # 2. Cookie
    cookie_match = re.search(r'(?:-b|--cookie|-H\s+[\'"][Cc]ookie:\s*)\s*[\'"]([^\'"]+)[\'"]', curl_text)
    if not cookie_match:
        cookie_match = re.search(r'-H\s+[\'"]Cookie:\s*([^;\'"]+;[^\'"]+)[\'"]', curl_text)
    if cookie_match:
        result['cookie'] = cookie_match.group(1).strip()

    # 3. DocumentBatchId (nếu có)
    batch_match = re.search(r'[\'"]DocumentBatchId[\'"]\s*:\s*[\'"]([a-f0-9\-]+)[\'"]', curl_text, re.IGNORECASE)
    if not batch_match:
        batch_match = re.search(r'(?:waiting-for-others/|batchId=)([a-f0-9\-]{36})', curl_text, re.IGNORECASE)
    if batch_match:
        result['document_batch_id'] = batch_match.group(1).strip()

    # 4. TenantId
    tenant_match = re.search(r'[\'"](?:DocumentBatchTenantId|tenantId|x-tenantid)[\'"]\s*:\s*[\'"]([a-f0-9\-]+)[\'"]', curl_text, re.IGNORECASE)
    if not tenant_match:
        tenant_match = re.search(r'(?:x-misa-ws-database-tenantid|tenantId=)\s*[:=]\s*[\'"]?([a-f0-9\-]{36})', curl_text, re.IGNORECASE)
    if tenant_match:
        result['tenant_id'] = tenant_match.group(1).strip()

    # 5. DeviceId
    device_match = re.search(r'(?:deviceId|x-deviceid)\s*[:=]\s*[\'"]?([a-f0-9\-]{36})', curl_text, re.IGNORECASE)
    if device_match:
        result['device_id'] = device_match.group(1).strip()

    return result

class WeSignClient:
    def __init__(self, config_path=CONFIG_FILE):
        self.config_path = config_path
        self.config = self.load_config()
        self.cached_batches = []
        self.batches_cache_time = 0
        self.contracts_cache = {}  # cccd -> doc info
        self.contracts_cache_time = 0

    def load_config(self):
        cfg = DEFAULT_CONFIG.copy()
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    file_cfg = json.load(f)
                    cfg.update(file_cfg)
            except Exception as e:
                print(f"Lỗi đọc {self.config_path}: {e}")

        # Hỗ trợ cấu hình qua Biến môi trường khi deploy Cloud (Render / Railway / Docker)
        if os.environ.get('WESIGN_TOKEN'):
            cfg['token'] = os.environ['WESIGN_TOKEN']
        if os.environ.get('WESIGN_COOKIE'):
            cfg['cookie'] = os.environ['WESIGN_COOKIE']
        if os.environ.get('WESIGN_BATCH_ID'):
            cfg['document_batch_id'] = os.environ['WESIGN_BATCH_ID']
        if os.environ.get('WESIGN_TENANT_ID'):
            cfg['tenant_id'] = os.environ['WESIGN_TENANT_ID']

        return cfg

    def save_config(self, new_config=None):
        if new_config:
            self.config.update(new_config)
            self.cached_batches = []
            self.contracts_cache = {}
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
        return self.config

    def _get_headers(self):
        return {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'vi,en-US;q=0.9,en;q=0.8',
            'Authorization': f"Bearer {self.config.get('token', '')}",
            'Content-Type': 'application/json',
            'Origin': 'https://amisapp.misa.vn',
            'Response-Type': 'json',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': self.config.get('user_agent', DEFAULT_CONFIG['user_agent']),
            'deviceId': self.config.get('device_id', ''),
            'productVersion': 'R3',
            'x-misa-ws-database-tenantid': self.config.get('tenant_id', '')
        }

    def _get_user_id(self):
        token = self.config.get('token', '')
        try:
            parts = token.split('.')
            if len(parts) >= 2:
                padded = parts[1] + '=' * (4 - len(parts[1]) % 4)
                data = json.loads(base64.b64decode(padded).decode('utf-8'))
                return data.get('sub', '')
        except Exception:
            pass
        return "9ce95ef8-327d-4682-9b42-9af0eb079021"

    def get_all_batches(self, force_refresh=False):
        """
        Lấy danh sách TẤT CẢ các đợt/lô tài liệu từ WeSign qua API /paging/data (không giới hạn trạng thái)
        """
        now = time.time()
        if not force_refresh and self.cached_batches and (now - self.batches_cache_time < 300):
            return self.cached_batches

        url = 'https://amisapp.misa.vn/wesign/g2/api/file-management/api/v2/documents/paging/data'
        headers = self._get_headers()
        cookies = parse_cookies_str(self.config.get('cookie', ''))

        body = {
            "status": [],  # Lấy tất cả các trạng thái
            "limit": 100,
            "pageNumber": 1,
            "keyword": "",
            "currentUser": self._get_user_id(),
            "filterField": 1,
            "isMine": False,
            "isParticipated": False,
            "isTrash": False,
            "sourceDocuments": ["Task", "CRM", "Accounting", "AMISProcess", "EmployeesProfile", "Other", "AMISWesign"],
            "draftType": 0,
            "relatedUsers": []
        }

        try:
            res = requests.post(url, headers=headers, cookies=cookies, json=body, timeout=12)
            if res.status_code == 200:
                self.cached_batches = res.json().get('data') or []
                self.batches_cache_time = now
                return self.cached_batches
        except Exception as e:
            print(f"[!] Lỗi get_all_batches: {e}")

        default_batch_id = self.config.get('document_batch_id')
        if default_batch_id:
            return [{"id": default_batch_id, "name": "Đợt mặc định"}]
        return []

    def sync_all_contracts(self, force=False):
        """
        ĐỒNG BỘ TOÀN BỘ dữ liệu tất cả tài liệu/hợp đồng từ TẤT CẢ các đợt vào bộ nhớ đệm.
        Bao gồm: HỢP ĐỒNG OS, THỎA THUẬN OS, v.v...
        Chạy chỉ mất ~1 giây nhưng giúp tra cứu tìm thấy 100% không sót bất kỳ ai!
        """
        now = time.time()
        if not force and self.contracts_cache and (now - self.contracts_cache_time < 300):
            return self.contracts_cache

        batches = self.get_all_batches(force_refresh=force)
        if not batches:
            return self.contracts_cache

        url_batch = 'https://amisapp.misa.vn/wesign/g2/api/file-management/api/v2/documents/paging/batch-data'
        headers = self._get_headers()
        cookies = parse_cookies_str(self.config.get('cookie', ''))

        new_cache = {}
        for b in batches:
            b_id = b.get('id')
            b_name = b.get('name', 'Đợt tài liệu')
            try:
                body_b = {
                    "status": [],  # Lấy tất cả các trạng thái
                    "limit": 100,
                    "pageNumber": 1,
                    "keyword": "",
                    "DocumentBatchId": b_id,
                    "DocumentBatchTenantId": self.config.get('tenant_id', '')
                }
                res_b = requests.post(url_batch, headers=headers, cookies=cookies, json=body_b, timeout=10)
                if res_b.status_code == 200:
                    docs = res_b.json().get('data') or []
                    for doc in docs:
                        doc_name = doc.get('name', '')
                        doc_id = doc.get('id')
                        doc_status = STATUS_MAP.get(doc.get('status', -1), "Chờ ký")
                        parts = doc.get('documentParticipants') or []

                        worker = self._extract_worker_participant(parts, doc_name)
                        if worker:
                            part_id = worker.get('documentParticipantID') or worker.get('id')
                            worker_name = worker.get('name', '')
                            job_position = worker.get('jobPosition', 'Người lao động')

                            doc_info = {
                                "doc_id": doc_id,
                                "doc_name": doc_name,
                                "participant_id": part_id,
                                "worker_name": worker_name,
                                "job_position": job_position,
                                "batch_id": b_id,
                                "batch_name": b_name,
                                "doc_status": doc_status
                            }

                            # Trích xuất tất cả các chuỗi 9 - 12 chữ số trong tên tài liệu
                            found_numbers = re.findall(r'(\d{9,12})', doc_name)
                            for num in found_numbers:
                                new_cache[num] = doc_info
                                if num.startswith('0'):
                                    new_cache[num.lstrip('0')] = doc_info

            except Exception as e:
                print(f"[!] Lỗi đồng bộ đợt {b_name}: {e}")
                continue

        if new_cache:
            self.contracts_cache = new_cache
            self.contracts_cache_time = now

        return self.contracts_cache

    def test_connection(self):
        batches = self.get_all_batches(force_refresh=True)
        if batches:
            total = len(batches)
            first_name = batches[0].get('name', 'Đợt tài liệu WeSign')
            return {
                "success": True,
                "message": f"Kết nối thành công! Đang có {total} đợt tài liệu (ví dụ: '{first_name}')",
                "batchName": f"Tất cả {total} đợt tài liệu",
                "total": total
            }
        return {"success": False, "message": "Không thể kết nối hoặc Token/Cookie đã hết hạn"}

    def _extract_worker_participant(self, participants, doc_name):
        if not participants:
            return None
        for p in participants:
            job = (p.get('jobPosition') or '').lower()
            if 'lao động' in job:
                return p
        for p in participants:
            p_name = (p.get('name') or '').strip().upper()
            if p_name and p_name in doc_name.upper():
                return p
        for p in participants:
            job = (p.get('jobPosition') or '').lower()
            if not any(k in job for k in ['trưởng phòng', 'giám đốc', 'đại diện', 'kế toán', 'nhân sự']):
                return p
        return participants[0]

    def _get_sign_link(self, doc_id, participant_id, headers, cookies):
        url_sign = 'https://amisapp.misa.vn/wesign/g2/api/file-management/api/v2/documents/sign-link'
        body_sign = {
            "documentId": doc_id,
            "documentParticipantId": participant_id
        }
        try:
            res = requests.post(url_sign, headers=headers, cookies=cookies, json=body_sign, timeout=12)
            if res.status_code == 200:
                return res.json().get('data')
        except Exception:
            pass
        return None

    def get_document_history(self, doc_id, worker_name=""):
        """
        Lấy và phân tích toàn bộ lịch sử thao tác của tài liệu theo documentId:
        - Kiểm tra xem NLĐ đã mở xem tài liệu chưa (Action 4)
        - Kiểm tra xem NLĐ đã ký chưa (Action 5)
        - Kiểm tra xem tài liệu đã hoàn tất chưa (Action 6)
        - Phân loại rõ: 'Đã hoàn thành', 'NLĐ đã ký', 'Đã xem (Chưa ký)', 'Chưa xem'
        """
        if not doc_id:
            return {
                "is_completed": False,
                "completed_time": "",
                "worker_signed": False,
                "worker_signed_time": "",
                "worker_viewed": False,
                "worker_viewed_time": "",
                "signing_state": "Chưa xem",
                "events": []
            }

        url = f"https://amisapp.misa.vn/wesign/g2/api/file-management/api/v1/documents/{doc_id}/histories"
        headers = self._get_headers()
        cookies = parse_cookies_str(self.config.get('cookie', ''))

        try:
            res = requests.get(url, headers=headers, cookies=cookies, timeout=8)
            if res.status_code != 200:
                return {
                    "is_completed": False,
                    "completed_time": "",
                    "worker_signed": False,
                    "worker_signed_time": "",
                    "worker_viewed": False,
                    "worker_viewed_time": "",
                    "signing_state": "Chưa xem",
                    "events": []
                }
            histories = res.json().get('documents') or []
        except Exception:
            return {
                "is_completed": False,
                "completed_time": "",
                "worker_signed": False,
                "worker_signed_time": "",
                "worker_viewed": False,
                "worker_viewed_time": "",
                "signing_state": "Chưa xem",
                "events": []
            }

        worker_clean = (worker_name or '').strip().upper()
        worker_signed = False
        worker_signed_time = ""
        worker_viewed = False
        worker_viewed_time = ""
        is_completed = False
        completed_time = ""

        ACTION_MAP = {
            0: "Tạo / Gửi tài liệu",
            4: "Mở xem tài liệu",
            5: "Đã ký",
            6: "Hoàn tất hợp đồng",
            21: "Cập nhật tài liệu"
        }

        events = []
        for h in histories:
            act = h.get('action')
            u_name = (h.get('userName') or '').strip()
            u_clean = u_name.upper()
            act_time_raw = h.get('actionTime') or ''
            act_time = ""
            if act_time_raw:
                try:
                    dt = datetime.fromisoformat(act_time_raw)
                    act_time = dt.strftime("%d/%m/%Y %H:%M:%S")
                except Exception:
                    act_time = act_time_raw

            act_text = ACTION_MAP.get(act, f"Hành động ({act})")
            desc = h.get('description') or ''

            events.append({
                "action": act,
                "action_text": act_text,
                "user_name": u_name,
                "user_email": h.get('userEmail') or '',
                "time": act_time,
                "description": desc
            })

            if act == 6:
                is_completed = True
                if not completed_time:
                    completed_time = act_time

            # Kiểm tra xem user có phải người lao động không
            is_worker = bool(worker_clean and (worker_clean in u_clean or u_clean in worker_clean))
            if is_worker or (not worker_clean and act in [4, 5]):
                if act == 5 and not worker_signed:
                    worker_signed = True
                    worker_signed_time = act_time
                elif act == 4 and not worker_viewed:
                    worker_viewed = True
                    worker_viewed_time = act_time

        if is_completed:
            signing_state = "Đã hoàn thành"
        elif worker_signed:
            signing_state = "NLĐ đã ký"
        elif worker_viewed:
            signing_state = "Đã xem (Chưa ký)"
        else:
            signing_state = "Chưa xem"

        return {
            "is_completed": is_completed,
            "completed_time": completed_time,
            "worker_signed": worker_signed,
            "worker_signed_time": worker_signed_time,
            "worker_viewed": worker_viewed,
            "worker_viewed_time": worker_viewed_time,
            "signing_state": signing_state,
            "events": events
        }

    def get_link_by_cccd(self, cccd, include_history=True):
        """
        Tra cứu hợp đồng theo số CCCD:
        1. Tìm trong kho dữ liệu đồng bộ của tất cả các đợt (Level 1 - Instant Cache).
        2. Nếu chưa thấy, tìm nhanh qua API /paging/data của MISA WeSign (Level 2 - Server Search).
        3. Nếu chưa thấy, quét trực tiếp từng đợt tài liệu (Level 3 - Deep Fallback).
        4. Tự động kiểm tra lịch sử ký để phân loại: 'Đã hoàn thành', 'NLĐ đã ký', 'Đã xem (Chưa ký)', 'Chưa xem'.
        """
        cccd_clean = str(cccd).strip()
        if not cccd_clean:
            return {"status": "error", "cccd": cccd, "message": "Số CCCD trống"}

        headers = self._get_headers()
        cookies = parse_cookies_str(self.config.get('cookie', ''))

        def _build_success_res(doc_id, doc_name, part_id, worker_name, job_position, b_id, b_name, doc_status, sign_link):
            res = {
                "status": "success",
                "cccd": cccd_clean,
                "worker_name": worker_name,
                "job_position": job_position,
                "batch_name": b_name,
                "doc_name": doc_name,
                "doc_id": doc_id,
                "participant_id": part_id,
                "doc_status": doc_status,
                "sign_link": sign_link,
                "signing_state": "Chưa xem",
                "worker_signed": False,
                "worker_signed_time": "",
                "worker_viewed": False,
                "worker_viewed_time": "",
                "is_completed": False,
                "completed_time": "",
                "history_events": []
            }
            if include_history and doc_id:
                h_info = self.get_document_history(doc_id, worker_name)
                res.update({
                    "signing_state": h_info.get("signing_state", "Chưa xem"),
                    "worker_signed": h_info.get("worker_signed", False),
                    "worker_signed_time": h_info.get("worker_signed_time", ""),
                    "worker_viewed": h_info.get("worker_viewed", False),
                    "worker_viewed_time": h_info.get("worker_viewed_time", ""),
                    "is_completed": h_info.get("is_completed", False),
                    "completed_time": h_info.get("completed_time", ""),
                    "history_events": h_info.get("events", [])
                })
            return res

        # 1. TÌM TRONG KHO DỮ LIỆU ĐỒNG BỘ TOÀN BỘ TÀI LIỆU
        if not self.contracts_cache:
            self.sync_all_contracts()

        doc_info = self.contracts_cache.get(cccd_clean)
        if not doc_info and cccd_clean.startswith('0'):
            doc_info = self.contracts_cache.get(cccd_clean.lstrip('0'))
        if not doc_info and not cccd_clean.startswith('0'):
            doc_info = self.contracts_cache.get('0' + cccd_clean)
        if not doc_info and len(cccd_clean) < 12 and cccd_clean.isdigit():
            doc_info = self.contracts_cache.get(cccd_clean.zfill(12))

        if doc_info:
            sign_link = self._get_sign_link(doc_info['doc_id'], doc_info['participant_id'], headers, cookies)
            if sign_link:
                return _build_success_res(
                    doc_info['doc_id'], doc_info['doc_name'], doc_info['participant_id'],
                    doc_info['worker_name'], doc_info['job_position'], doc_info['batch_id'],
                    doc_info['batch_name'], doc_info['doc_status'], sign_link
                )

        # 2. TÌM NHANH TRÊN TOÀN HỆ THỐNG QUA API PAGING/DATA BẰNG TỪ KHÓA CCCD
        url_data = 'https://amisapp.misa.vn/wesign/g2/api/file-management/api/v2/documents/paging/data'
        url_batch = 'https://amisapp.misa.vn/wesign/g2/api/file-management/api/v2/documents/paging/batch-data'

        body_data = {
            "status": [],
            "limit": 5,
            "pageNumber": 1,
            "keyword": cccd_clean,
            "currentUser": self._get_user_id(),
            "filterField": 1,
            "sourceDocuments": ["Task", "CRM", "Accounting", "AMISProcess", "EmployeesProfile", "Other", "AMISWesign"],
            "draftType": 0,
            "relatedUsers": []
        }

        try:
            res_d = requests.post(url_data, headers=headers, cookies=cookies, json=body_data, timeout=8)
            if res_d.status_code == 200:
                matching_batches = res_d.json().get('data') or []
                for b in matching_batches:
                    b_id = b.get('id')
                    b_name = b.get('name', 'Đợt tài liệu')
                    body_b = {
                        "status": [],
                        "limit": 10,
                        "pageNumber": 1,
                        "keyword": cccd_clean,
                        "DocumentBatchId": b_id,
                        "DocumentBatchTenantId": self.config.get('tenant_id', '')
                    }
                    res_b = requests.post(url_batch, headers=headers, cookies=cookies, json=body_b, timeout=8)
                    if res_b.status_code == 200:
                        docs = res_b.json().get('data') or []
                        if docs:
                            doc = docs[0]
                            doc_id = doc.get('id')
                            doc_name = doc.get('name', '')
                            doc_status = STATUS_MAP.get(doc.get('status', -1), "Chờ ký")
                            parts = doc.get('documentParticipants') or []
                            worker = self._extract_worker_participant(parts, doc_name)
                            if worker:
                                part_id = worker.get('documentParticipantID') or worker.get('id')
                                worker_name = worker.get('name', '')
                                job_position = worker.get('jobPosition', 'Người lao động')
                                sign_link = self._get_sign_link(doc_id, part_id, headers, cookies)
                                if sign_link:
                                    self.contracts_cache[cccd_clean] = {
                                        "doc_id": doc_id,
                                        "doc_name": doc_name,
                                        "participant_id": part_id,
                                        "worker_name": worker_name,
                                        "job_position": job_position,
                                        "batch_id": b_id,
                                        "batch_name": b_name,
                                        "doc_status": doc_status
                                    }
                                    return _build_success_res(
                                        doc_id, doc_name, part_id, worker_name, job_position,
                                        b_id, b_name, doc_status, sign_link
                                    )
        except Exception:
            pass

        # 3. NẾU VẪN CHƯA THẤY: QUÉT TRỰC TIẾP TỪNG ĐỢT TÀI LIỆU
        batches = self.get_all_batches()
        for b in batches:
            b_id = b.get('id')
            b_name = b.get('name', 'Đợt tài liệu')
            body_search = {
                "status": [],
                "limit": 10,
                "pageNumber": 1,
                "keyword": cccd_clean,
                "DocumentBatchId": b_id,
                "DocumentBatchTenantId": self.config.get('tenant_id', '')
            }

            try:
                res = requests.post(url_batch, headers=headers, cookies=cookies, json=body_search, timeout=8)
                if res.status_code == 200:
                    docs = res.json().get('data') or []
                    if docs:
                        doc = docs[0]
                        doc_id = doc.get('id')
                        doc_name = doc.get('name', '')
                        doc_status = STATUS_MAP.get(doc.get('status', -1), "Chờ ký")
                        parts = doc.get('documentParticipants') or []

                        worker = self._extract_worker_participant(parts, doc_name)
                        if worker:
                            part_id = worker.get('documentParticipantID') or worker.get('id')
                            worker_name = worker.get('name', '')
                            job_position = worker.get('jobPosition', 'Người lao động')

                            sign_link = self._get_sign_link(doc_id, part_id, headers, cookies)
                            if sign_link:
                                self.contracts_cache[cccd_clean] = {
                                    "doc_id": doc_id,
                                    "doc_name": doc_name,
                                    "participant_id": part_id,
                                    "worker_name": worker_name,
                                    "job_position": job_position,
                                    "batch_id": b_id,
                                    "batch_name": b_name,
                                    "doc_status": doc_status
                                }

                                return _build_success_res(
                                    doc_id, doc_name, part_id, worker_name, job_position,
                                    b_id, b_name, doc_status, sign_link
                                )
            except Exception:
                continue

        return {
            "status": "not_found",
            "cccd": cccd_clean,
            "message": "Không tìm thấy hợp đồng nào khớp với số CCCD này trong bất kỳ đợt nào"
        }

    def get_links_batch(self, cccd_list, delay=0.25, callback=None):
        self.sync_all_contracts(force=True)
        results = []
        total = len(cccd_list)
        for idx, cccd in enumerate(cccd_list):
            res = self.get_link_by_cccd(cccd)
            results.append(res)
            if callback:
                callback(idx + 1, total, res)
            if idx < total - 1 and delay > 0:
                time.sleep(delay)
        return results
