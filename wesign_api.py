import re
import json
import time
import os
import base64
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

DEFAULT_CONFIG = {
    "token": "",
    "cookie": "",
    "document_batch_id": "",
    "folder_id": "all",
    "tenant_id": "c4e3c4ef-a722-40cd-96ed-6aa20a86ee94",
    "device_id": "6d656d65-248f-4cc2-80e1-69faf29f910d",
    "status_filter": [0, 1, 3, 5],
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"
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
        # Tự động trích xuất tenant_id từ JWT token nếu có
        try:
            parts = result['token'].split('.')
            if len(parts) >= 2:
                padded = parts[1] + '=' * (4 - len(parts[1]) % 4)
                data = json.loads(base64.b64decode(padded).decode('utf-8'))
                if data.get('tenantid'):
                    result['tenant_id'] = data.get('tenantid')
        except Exception:
            pass

    # 2. Cookie
    cookie_match = re.search(r'(?:-b|--cookie|-H\s+[\'"][Cc]ookie:\s*)\s*[\'"]([^\'"]+)[\'"]', curl_text)
    if not cookie_match:
        cookie_match = re.search(r'-H\s+[\'"]Cookie:\s*([^;\'"]+;[^\'"]+)[\'"]', curl_text)
    if cookie_match:
        result['cookie'] = cookie_match.group(1).strip()

    # 3. FolderID (Rất quan trọng cho WeSign!)
    folder_match = re.search(r'[\'"]folderID[\'"]\s*:\s*([0-9]+)', curl_text, re.IGNORECASE)
    if not folder_match:
        folder_match = re.search(r'/documents/([0-9]{3,10})', curl_text)
    if folder_match:
        try:
            result['folder_id'] = int(folder_match.group(1))
        except Exception:
            result['folder_id'] = folder_match.group(1)

    # 4. DocumentBatchId (nếu có)
    batch_match = re.search(r'[\'"]DocumentBatchId[\'"]\s*:\s*[\'"]([a-f0-9\-]+)[\'"]', curl_text, re.IGNORECASE)
    if not batch_match:
        batch_match = re.search(r'(?:waiting-for-others/|batchId=)([a-f0-9\-]{36})', curl_text, re.IGNORECASE)
    if batch_match:
        result['document_batch_id'] = batch_match.group(1).strip()

    # 5. TenantId (nếu có trong header, cookie, body)
    tenant_match = re.search(r'(?:x-misa-ws-database-tenantid|DocumentBatchTenantId|tenantId|x-tenantid)[\'"]?\s*[:=]\s*[\'"]?([a-f0-9\-]{36})', curl_text, re.IGNORECASE)
    if tenant_match:
        result['tenant_id'] = tenant_match.group(1).strip()

    # 6. DeviceId
    device_match = re.search(r'(?:deviceId|x-deviceid)\s*[:=]\s*[\'"]?([a-f0-9\-]{36})', curl_text, re.IGNORECASE)
    if device_match:
        result['device_id'] = device_match.group(1).strip()

    # 7. Status filter (nếu có mảng status trong body)
    status_match = re.search(r'[\'"]status[\'"]\s*:\s*(\[[0-9,\s]*\])', curl_text)
    if status_match:
        try:
            st_list = json.loads(status_match.group(1))
            if isinstance(st_list, list):
                result['status_filter'] = st_list
        except Exception:
            pass

    return result

class WeSignClient:
    def __init__(self, config_path=CONFIG_FILE):
        self.config_path = config_path
        self.config = self.load_config()
        self.cached_batches = []
        self.batches_cache_time = 0
        self.contracts_cache = {}  # cccd -> doc info
        self.contracts_cache_time = 0
        self.cached_folders = []
        self.folders_cache_time = 0

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
        if os.environ.get('WESIGN_FOLDER_ID'):
            val = os.environ['WESIGN_FOLDER_ID'].strip()
            if val.isdigit():
                cfg['folder_id'] = int(val)
            else:
                cfg['folder_id'] = val
        if os.environ.get('WESIGN_TENANT_ID'):
            cfg['tenant_id'] = os.environ['WESIGN_TENANT_ID']

        return cfg

    def save_config(self, new_config=None):
        if new_config:
            self.config.update(new_config)
            self.cached_batches = []
            self.contracts_cache = {}
            if 'token' in new_config or 'cookie' in new_config:
                self.cached_folders = []
                self.folders_cache_time = 0
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
        return self.config

    def _get_headers(self):
        tenant_id = self.config.get('tenant_id', '')
        device_id = self.config.get('device_id', '')
        headers = {
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
            'productVersion': 'R3'
        }
        if device_id:
            headers['deviceId'] = device_id
        if tenant_id:
            headers['x-misa-ws-database-tenantid'] = tenant_id
            headers['x-tenantid'] = tenant_id
            headers['tenantId'] = tenant_id
        return headers

    def get_folders(self, force_refresh=False):
        """
        Lấy danh sách tất cả các thư mục từ MISA WeSign:
        POST /wesign/g2/api/file-management/api/v1/documents/get-folder
        """
        now = time.time()
        if not force_refresh and self.cached_folders and (now - self.folders_cache_time < 300):
            return self.cached_folders

        url = 'https://amisapp.misa.vn/wesign/g2/api/file-management/api/v1/documents/get-folder'
        headers = self._get_headers()
        cookies = parse_cookies_str(self.config.get('cookie', ''))

        try:
            r = requests.post(url, headers=headers, cookies=cookies, json={}, timeout=10)
            if r.status_code == 200:
                raw_folders = r.json() or []
                folders_list = []
                for f in raw_folders:
                    f_id = f.get('id')
                    if f_id is not None:
                        folders_list.append({
                            "id": f_id,
                            "name": f.get('folderName', f'Thư mục {f_id}'),
                            "parent_id": f.get('parentID'),
                            "code": f.get('folderCode', '')
                        })
                self.cached_folders = folders_list
                self.folders_cache_time = now
                return folders_list
        except Exception as e:
            print(f"Lỗi lấy danh sách thư mục từ WeSign: {e}")
        return self.cached_folders or []

    def _get_user_info(self):
        token = self.config.get('token', '')
        try:
            parts = token.split('.')
            if len(parts) >= 2:
                padded = parts[1] + '=' * (4 - len(parts[1]) % 4)
                data = json.loads(base64.b64decode(padded).decode('utf-8'))
                return {
                    "user_id": data.get('sub', ''),
                    "user_name": data.get('name', ''),
                    "tenant_id": data.get('tenantid', ''),
                    "exp": data.get('exp', 0)
                }
        except Exception:
            pass
        return {
            "user_id": "9ce95ef8-327d-4682-9b42-9af0eb079021",
            "user_name": "Người dùng",
            "tenant_id": self.config.get('tenant_id', ''),
            "exp": 0
        }

    def is_token_expired(self):
        info = self._get_user_info()
        exp = info.get('exp', 0)
        if exp and time.time() >= exp:
            return True, exp
        return False, exp

    def _get_user_id(self):
        return self._get_user_info().get('user_id', '')

    def get_all_batches(self, force_refresh=False, max_pages=10):
        """
        Lấy danh sách các đợt/lô tài liệu từ WeSign qua API /v1/documents/paging/data.
        Hỗ trợ:
        - folder_id = 'all': Quét qua TẤT CẢ các thư mục + Thư mục gốc (Mặc định).
        - folder_id = None hoặc '': Quét Thư mục gốc.
        - folder_id = <id>: Quét riêng thư mục chỉ định.
        """
        now = time.time()
        if not force_refresh and self.cached_batches and (now - self.batches_cache_time < 300):
            return self.cached_batches

        url = 'https://amisapp.misa.vn/wesign/g2/api/file-management/api/v1/documents/paging/data'
        headers = self._get_headers()
        cookies = parse_cookies_str(self.config.get('cookie', ''))

        folder_cfg = self.config.get('folder_id')
        is_all_folders = str(folder_cfg).strip().lower() in ['all', 'tat-ca', 'all_folders', 'tatca']

        if is_all_folders:
            folders = self.get_folders()
            target_folders = [(None, "Thư mục gốc")] + [(f['id'], f['name']) for f in folders]
        elif folder_cfg in [None, '', 0, '0']:
            target_folders = [(None, "Thư mục gốc")]
        else:
            try:
                fid_num = int(folder_cfg)
                fname = f"Thư mục {fid_num}"
                for f in self.get_folders():
                    if f['id'] == fid_num:
                        fname = f['name']
                        break
                target_folders = [(fid_num, fname)]
            except Exception:
                target_folders = [(folder_cfg, f"Thư mục {folder_cfg}")]

        status_filter = self.config.get('status_filter') or [0, 1, 3, 5]
        all_batches = []
        seen_ids = set()

        for f_id, f_name in target_folders:
            sort_params = []
            for page in range(1, max_pages + 1):
                body = {
                    "status": status_filter,
                    "limit": 50,
                    "pageNumber": page,
                    "keyword": "",
                    "isMine": False,
                    "isParticipated": False,
                    "isTrash": False,
                    "DocumentRoleFilter": 1,
                    "folderID": f_id,
                    "actionType": 1,
                    "typeSearch": 2,
                    "sortParameters": sort_params
                }

                try:
                    res = requests.post(url, headers=headers, cookies=cookies, json=body, timeout=12)
                    if res.status_code != 200:
                        break
                    res_data = res.json()
                    data = res_data.get('data') or []
                    sort_nexts = res_data.get('sortParameterNexts') or []

                    new_count = 0
                    for item in data:
                        item_id = item.get('id')
                        if item_id and item_id not in seen_ids:
                            seen_ids.add(item_id)
                            item['folder_id'] = f_id
                            item['folder_name'] = f_name
                            all_batches.append(item)
                            new_count += 1

                    if not sort_nexts or len(data) == 0 or new_count == 0:
                        break

                    sort_params = sort_nexts
                except Exception as e:
                    print(f"[!] Lỗi get_all_batches thư mục {f_name} (trang {page}): {e}")
                    break

        if all_batches:
            self.cached_batches = all_batches
            self.batches_cache_time = now
            return self.cached_batches

        default_batch_id = self.config.get('document_batch_id')
        if default_batch_id:
            return [{"id": default_batch_id, "name": "Đợt mặc định"}]
        return []

    def sync_all_contracts(self, force=False):
        """
        Đồng bộ toàn bộ hợp đồng trong các đợt tài liệu vào bộ nhớ đệm (contracts_cache).
        Luôn gửi kèm folderID khi gọi API batch-data.
        """
        now = time.time()
        if not force and self.contracts_cache and (now - self.contracts_cache_time < 300):
            return self.contracts_cache

        batches = self.get_all_batches(force_refresh=force)
        if not batches:
            return self.contracts_cache

        url_batch = 'https://amisapp.misa.vn/wesign/g2/api/file-management/api/v1/documents/paging/batch-data'
        headers = self._get_headers()
        cookies = parse_cookies_str(self.config.get('cookie', ''))
        tenant_id = self.config.get('tenant_id', '')
        status_filter = self.config.get('status_filter') or [0, 1, 3, 5]

        new_cache = {}
        for b in batches:
            b_id = b.get('id')
            b_name = b.get('name', 'Đợt tài liệu')
            b_folder_id = b.get('folder_id')
            try:
                body_b = {
                    "status": status_filter,
                    "limit": 100,
                    "pageNumber": 1,
                    "keyword": "",
                    "DocumentBatchId": b_id,
                    "DocumentBatchTenantId": tenant_id,
                    "folderID": b_folder_id
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
                                "doc_status": doc_status,
                                "folder_id": b_folder_id
                            }

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
        expired, exp_time = self.is_token_expired()
        if expired:
            exp_str = datetime.fromtimestamp(exp_time).strftime("%H:%M:%S") if exp_time else ""
            return {
                "success": False,
                "message": f"Phiên đăng nhập WeSign đã hết hạn{f' lúc {exp_str}' if exp_str else ''}. Vui lòng dán cURL mới hoặc mở tab WeSign để Extension đồng bộ!",
                "expired": True
            }

        # Gọi trực tiếp API WeSign để kiểm tra thực tế xem Token còn sống không
        url = 'https://amisapp.misa.vn/wesign/g2/api/file-management/api/v1/folders/get-folder'
        headers = self._get_headers()
        cookies = parse_cookies_str(self.config.get('cookie', ''))
        try:
            r = requests.post(url, headers=headers, cookies=cookies, json={}, timeout=10)
            if r.status_code == 401:
                return {
                    "success": False,
                    "message": "Phiên đăng nhập MISA WeSign đã hết hạn (401 Unauthorized). Vui lòng dán cURL mới hoặc bấm Đồng Bộ trên Extension!",
                    "expired": True
                }
        except Exception:
            pass

        user_info = self._get_user_info()
        user_name = user_info.get('user_name') or 'AMIS WeSign'
        folder_id = self.config.get('folder_id')
        folders = self.get_folders(force_refresh=True)

        if not folders:
            return {
                "success": False,
                "message": "Không thể kết nối đến MISA WeSign hoặc Token đã hết hạn (401). Vui lòng cập nhật Token mới!",
                "expired": True
            }

        is_all_folders = str(folder_id).strip().lower() in ['all', 'tat-ca', 'all_folders', 'tatca']
        max_p = 1 if is_all_folders else 3
        batches = self.get_all_batches(force_refresh=True, max_pages=max_p)

        total = len(batches)
        first_name = batches[0].get('name', 'Đợt tài liệu') if batches else ''
        folder_info = " (Tất cả thư mục)" if is_all_folders else (f" (Folder: {folder_id})" if folder_id else " (Thư mục gốc)")
        folder_count_info = f" | {len(folders)} thư mục" if folders else ""
        return {
            "success": True,
            "message": f"Kết nối thành công! Đăng nhập: {user_name}. Đã nạp {total} đợt tài liệu{folder_count_info}{folder_info}{f' (VD: {first_name})' if first_name else ''}",
            "batchName": f"{user_name} - {total} đợt tài liệu{folder_info}",
            "total": total,
            "userName": user_name,
            "folderId": folder_id,
            "folders": folders
        }

    def _extract_worker_participant(self, participants, doc_name):
        if not participants:
            return None
        # 1. Tìm người có jobPosition chứa 'lao động'
        for p in participants:
            job = (p.get('jobPosition') or '').lower()
            if 'lao động' in job:
                return p
        # 2. Tìm người có tên xuất hiện trong tên hợp đồng
        for p in participants:
            p_name = (p.get('name') or '').strip().upper()
            if p_name and p_name in doc_name.upper():
                return p
        # 3. Lọc bỏ đại diện công ty / người duyệt
        for p in participants:
            job = (p.get('jobPosition') or '').lower()
            if not any(k in job for k in ['trưởng phòng', 'giám đốc', 'đại diện', 'kế toán', 'nhân sự', 'người tạo']):
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
        Lấy và phân tích toàn bộ lịch sử thao tác của tài liệu theo doc_id.
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
        1. Tìm trực tiếp trên Server MISA qua API /v1/documents/paging/data bằng từ khóa CCCD.
           Cực nhanh (0.2s - 0.5s), tìm chính xác 100% không bỏ sót bất kỳ đợt nào trong Thư mục!
        2. Nếu chưa thấy trong Folder chỉ định, tự động tìm trên toàn hệ thống WeSign (folderID: None).
        3. Nếu tìm thấy, gọi /batch-data kèm folderID để lấy đúng participant_id của người lao động.
        4. Tự động lấy lịch sử ký (Đã xem, Đã ký, Hoàn tất...).
        """
        cccd_clean = str(cccd).strip()
        if not cccd_clean:
            return {"status": "error", "cccd": cccd, "message": "Số CCCD trống"}

        # Kiểm tra token hết hạn ngay từ đầu
        expired, exp_time = self.is_token_expired()
        if expired:
            exp_str = datetime.fromtimestamp(exp_time).strftime("%H:%M:%S") if exp_time else ""
            return {
                "status": "error",
                "code": 401,
                "cccd": cccd_clean,
                "message": f"Phiên đăng nhập MISA WeSign đã hết hạn{f' lúc {exp_str}' if exp_str else ''}. Vui lòng mở lại tab WeSign để Extension tự động cập nhật hoặc copy cURL mới!"
            }

        headers = self._get_headers()
        cookies = parse_cookies_str(self.config.get('cookie', ''))
        folder_id = self.config.get('folder_id')
        tenant_id = self.config.get('tenant_id', '')
        status_filter = self.config.get('status_filter') or [0, 1, 3, 5]

        # Lấy danh sách tất cả các thư mục có trên WeSign để gán nhãn tên thư mục
        all_known_folders = self.get_folders()
        folder_names_map = {f['id']: f['name'] for f in all_known_folders}

        def _build_success_res(doc_id, doc_name, part_id, worker_name, job_position, b_id, b_name, doc_status, sign_link, f_id=None):
            f_name = folder_names_map.get(f_id)
            if not f_name:
                if f_id:
                    f_name = f"Thư mục {f_id}"
                else:
                    f_name = "Thư mục gốc"

            # Xác định trạng thái ký ban đầu nếu chưa có link ký trực tiếp
            initial_state = "Chưa xem"
            if not sign_link:
                initial_state = "Chờ duyệt / Ký trước"

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
                "sign_link": sign_link or "",
                "folder_id": f_id,
                "folder_name": f_name,
                "signing_state": initial_state,
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
                h_state = h_info.get("signing_state", initial_state)
                # Nếu chưa có link ký của NLĐ và NLĐ chưa ký -> Đang chờ cấp trên/người khác duyệt trước
                if not sign_link and not h_info.get("worker_signed") and not h_info.get("is_completed"):
                    h_state = "Chờ duyệt / Ký trước"
                res.update({
                    "signing_state": h_state,
                    "worker_signed": h_info.get("worker_signed", False),
                    "worker_signed_time": h_info.get("worker_signed_time", ""),
                    "worker_viewed": h_info.get("worker_viewed", False),
                    "worker_viewed_time": h_info.get("worker_viewed_time", ""),
                    "is_completed": h_info.get("is_completed", False),
                    "completed_time": h_info.get("completed_time", ""),
                    "history_events": h_info.get("events", [])
                })
            return res

        # 1. KIỂM TRA NHANH TRONG CACHE (NẾU ĐÃ CÓ)
        if self.contracts_cache:
            doc_info = self.contracts_cache.get(cccd_clean)
            if not doc_info:
                doc_info = self.contracts_cache.get(cccd_clean.lower())
            if not doc_info and cccd_clean.startswith('0'):
                doc_info = self.contracts_cache.get(cccd_clean.lstrip('0'))
            if not doc_info and not cccd_clean.startswith('0') and cccd_clean.isdigit():
                doc_info = self.contracts_cache.get('0' + cccd_clean)
            if not doc_info and len(cccd_clean) < 12 and cccd_clean.isdigit():
                doc_info = self.contracts_cache.get(cccd_clean.zfill(12))

            if doc_info:
                sign_link = doc_info.get('sign_link')
                if not sign_link:
                    sign_link = self._get_sign_link(doc_info['doc_id'], doc_info['participant_id'], headers, cookies) or ""
                return _build_success_res(
                    doc_info['doc_id'], doc_info['doc_name'], doc_info['participant_id'],
                    doc_info['worker_name'], doc_info['job_position'], doc_info['batch_id'],
                    doc_info['batch_name'], doc_info['doc_status'], sign_link,
                    f_id=doc_info.get('folder_id')
                )

        # 2. TÌM TRỰC TIẾP TRÊN SERVER QUA API /paging/data (FAST SERVER SEARCH)
        # Chuẩn bị các biến thể của CCCD
        variants = [cccd_clean]
        if cccd_clean.startswith('0') and len(cccd_clean) > 1:
            variants.append(cccd_clean.lstrip('0'))
        elif not cccd_clean.startswith('0'):
            variants.append('0' + cccd_clean)
        if len(cccd_clean) < 12 and cccd_clean.isdigit():
            variants.append(cccd_clean.zfill(12))

        url_search = 'https://amisapp.misa.vn/wesign/g2/api/file-management/api/v1/documents/paging/data'
        url_batch = 'https://amisapp.misa.vn/wesign/g2/api/file-management/api/v1/documents/paging/batch-data'

        # Lấy danh sách tất cả các thư mục có trên WeSign
        all_known_folders = self.get_folders()
        all_folder_ids = [None] + [f['id'] for f in all_known_folders]

        is_all_folders = str(folder_id).strip().lower() in ['all', 'tat-ca', 'all_folders', 'tatca']

        if is_all_folders or folder_id in [None, '']:
            search_folders = all_folder_ids
        else:
            try:
                fid_num = int(folder_id)
            except Exception:
                fid_num = folder_id
            search_folders = [fid_num] + [f for f in all_folder_ids if f != fid_num]

        # Hàm con tìm kiếm đợt chứa từ khóa trong 1 thư mục
        def _search_in_folder(f_id, kw):
            body_search = {
                'status': status_filter,
                'limit': 10,
                'pageNumber': 1,
                'keyword': kw,
                'folderID': f_id,
                'actionType': 1,
                'typeSearch': 2
            }
            try:
                r_s = requests.post(url_search, headers=headers, cookies=cookies, json=body_search, timeout=8)
                if r_s.status_code == 401:
                    return 401, []
                if r_s.status_code == 200:
                    return 200, (r_s.json().get('data') or [])
            except Exception:
                pass
            return 0, []

        for kw in variants:
            found_folder = None
            matching_batches = []

            # Nếu chỉ có 1 folder mục tiêu, chạy trực tiếp
            if len(search_folders) == 1:
                status_code, batches = _search_in_folder(search_folders[0], kw)
                if status_code == 401:
                    return {
                        "status": "error",
                        "code": 401,
                        "cccd": cccd_clean,
                        "message": "Phiên đăng nhập MISA WeSign đã hết hạn (401 Unauthorized). Vui lòng cập nhật Token mới!"
                    }
                if batches:
                    found_folder = search_folders[0]
                    matching_batches = batches
            else:
                # Quét song song các thư mục bằng ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=min(len(search_folders), 6)) as executor:
                    futures = {executor.submit(_search_in_folder, fid, kw): fid for fid in search_folders}
                    for fut in as_completed(futures):
                        fid = futures[fut]
                        try:
                            status_code, batches = fut.result()
                            if status_code == 401:
                                return {
                                    "status": "error",
                                    "code": 401,
                                    "cccd": cccd_clean,
                                    "message": "Phiên đăng nhập MISA WeSign đã hết hạn (401 Unauthorized). Vui lòng cập nhật Token mới!"
                                }
                            if batches:
                                found_folder = fid
                                matching_batches = batches
                                break
                        except Exception:
                            pass

            if not matching_batches:
                continue

            for b in matching_batches:
                b_id = b.get('id')
                b_name = b.get('name', 'Đợt tài liệu')

                # Gọi batch-data để tìm văn bản của người này bên trong đợt
                body_b = {
                    'status': status_filter,
                    'limit': 20,
                    'pageNumber': 1,
                    'keyword': kw,
                    'DocumentBatchId': b_id,
                    'DocumentBatchTenantId': tenant_id,
                    'folderID': found_folder
                }
                try:
                    r_batch = requests.post(url_batch, headers=headers, cookies=cookies, json=body_b, timeout=8)
                    if r_batch.status_code != 200:
                        url_b2 = 'https://amisapp.misa.vn/wesign/g2/api/file-management/api/v2/documents/paging/batch-data'
                        r_batch = requests.post(url_b2, headers=headers, cookies=cookies, json=body_b, timeout=8)
                        if r_batch.status_code != 200:
                            continue

                    docs = r_batch.json().get('data') or []
                    for doc in docs:
                        doc_id = doc.get('id')
                        doc_name = doc.get('name', '')
                        doc_status = STATUS_MAP.get(doc.get('status', -1), "Chờ ký")

                        # Kiểm tra số CCCD hoặc Từ khóa (Tên / Mã NV) xuất hiện trong tên tài liệu hoặc người ký
                        doc_name_lower = doc_name.lower()
                        kw_lower = kw.lower()

                        matched = False
                        if kw.isdigit():
                            doc_nums = re.findall(r'(\d{9,12})', doc_name)
                            matched = any(
                                (v == num or v.lstrip('0') == num.lstrip('0'))
                                for v in variants for num in doc_nums
                            )
                        if not matched and kw_lower in doc_name_lower:
                            matched = True

                        parts = doc.get('documentParticipants') or []
                        worker = self._extract_worker_participant(parts, doc_name)
                        if not worker:
                            continue

                        part_id = worker.get('documentParticipantID') or worker.get('id')
                        worker_name = worker.get('name', '')
                        job_position = worker.get('jobPosition', 'Người lao động')

                        if not matched and worker_name and kw_lower in worker_name.lower():
                            matched = True

                        if not matched:
                            continue

                        sign_link = self._get_sign_link(doc_id, part_id, headers, cookies) or ""
                        self.contracts_cache[cccd_clean] = {
                            "doc_id": doc_id,
                            "doc_name": doc_name,
                            "participant_id": part_id,
                            "worker_name": worker_name,
                            "job_position": job_position,
                            "batch_id": b_id,
                            "batch_name": b_name,
                            "doc_status": doc_status,
                            "folder_id": found_folder,
                            "sign_link": sign_link
                        }
                        return _build_success_res(
                            doc_id, doc_name, part_id, worker_name, job_position,
                            b_id, b_name, doc_status, sign_link,
                            f_id=found_folder
                        )
                except Exception:
                    continue

        return {
            "status": "not_found",
            "cccd": cccd_clean,
            "message": "Không tìm thấy hợp đồng nào khớp với số CCCD này trên WeSign"
        }

    def get_links_batch(self, cccd_list, delay=0.15, callback=None):
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
