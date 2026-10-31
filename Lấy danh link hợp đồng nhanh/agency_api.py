import os
import sys
import re
import json
import requests

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

DEFAULT_AGENCY_CONFIG = {
    "enabled": True,
    "cookie": "",
    "device_id": "1e483b648ab3801d54d28320c7c0e85b",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
}

def parse_agency_curl(curl_text):
    """
    Phân tích câu lệnh cURL từ logistics.myagencyservice.vn
    Tự động trích xuất cookie và device-id.
    """
    result = {}
    if not curl_text:
        return result

    # 1. Cookie: Tìm -b, --cookie hoặc -H 'Cookie: ...'
    cookie_match = re.search(r'(?:-b|--cookie)\s+[\'"]([^\'"]+)[\'"]', curl_text)
    if not cookie_match:
        cookie_match = re.search(r'-H\s+[\'"][Cc]ookie:\s*([^\'"]+)[\'"]', curl_text)
    if not cookie_match:
        cookie_match = re.search(r'(?:-b|--cookie|-H\s+Cookie:)\s*[\'"]?([^"\'\r\n\\]+)[\'"]?', curl_text)
    if not cookie_match:
        # Tìm bất kỳ chuỗi nào có định dạng chuỗi Cookie nhiều cặp key=value
        raw_cookie_match = re.search(r'([_A-Za-z0-9]+=[^;\r\n]+;(?:\s*[_A-Za-z0-9]+=[^;\r\n]+;?)+)', curl_text)
        if raw_cookie_match:
            cookie_match = raw_cookie_match

    if cookie_match:
        result['cookie'] = cookie_match.group(1).strip()

    # 2. Device ID
    device_match = re.search(r'-H\s+[\'"]device-id:\s*([^\'"]+)[\'"]', curl_text, re.IGNORECASE)
    if not device_match:
        device_match = re.search(r'device-id:\s*([a-zA-Z0-9_\-]+)', curl_text, re.IGNORECASE)
    if device_match:
        result['device_id'] = device_match.group(1).strip()

    # 3. User Agent
    ua_match = re.search(r'-H\s+[\'"]user-agent:\s*([^\'"]+)[\'"]', curl_text, re.IGNORECASE)
    if ua_match:
        result['user_agent'] = ua_match.group(1).strip()

    result['enabled'] = True
    return result

class AgencyClient:
    def __init__(self, config_path=CONFIG_FILE):
        self.config_path = config_path
        self.cache = {}  # cccd -> phone
        self.load_config()

    def load_config(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    full_cfg = json.load(f)
                    self.config = full_cfg.get('agency_portal', DEFAULT_AGENCY_CONFIG.copy())
            else:
                self.config = DEFAULT_AGENCY_CONFIG.copy()
        except Exception:
            self.config = DEFAULT_AGENCY_CONFIG.copy()

        # Hỗ trợ cấu hình qua Biến môi trường khi deploy Cloud (Render / Railway)
        if os.environ.get('AGENCY_COOKIE'):
            self.config['cookie'] = os.environ['AGENCY_COOKIE']
        if os.environ.get('AGENCY_DEVICE_ID'):
            self.config['device_id'] = os.environ['AGENCY_DEVICE_ID']

        return self.config

    def save_config(self, new_config=None):
        if new_config:
            self.config.update(new_config)
            self.cache.clear()

        full_cfg = {}
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    full_cfg = json.load(f)
        except Exception:
            full_cfg = {}

        full_cfg['agency_portal'] = self.config
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(full_cfg, f, ensure_ascii=False, indent=2)
        return self.config

    def _get_headers(self):
        return {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7,en-GB;q=0.6',
            'app': 'Agency Portal',
            'content-type': 'application/json;charset=UTF-8',
            'device-id': self.config.get('device_id', DEFAULT_AGENCY_CONFIG['device_id']),
            'origin': 'https://logistics.myagencyservice.vn',
            'referer': 'https://logistics.myagencyservice.vn/',
            'user-agent': self.config.get('user_agent', DEFAULT_AGENCY_CONFIG['user_agent'])
        }

    def _get_cookies(self):
        cookie_str = self.config.get('cookie', '')
        if not cookie_str:
            return {}
        cookies = {}
        for item in cookie_str.split(';'):
            if '=' in item:
                k, v = item.strip().split('=', 1)
                cookies[k] = v
        return cookies

    def normalize_phone(self, phone_raw):
        """
        Chuẩn hóa số điện thoại Việt Nam:
        - Xóa khoảng trắng, ký tự đặc biệt
        - Nếu 9 số -> thêm 0 (vd 814029489 -> 0814029489)
        - Nếu +84 hoặc 84 đầu -> đổi thành 0
        """
        if not phone_raw:
            return ""
        s = re.sub(r'[^\d+]', '', str(phone_raw).strip())
        if s.startswith('+84'):
            s = '0' + s[3:]
        elif s.startswith('84') and len(s) == 11:
            s = '0' + s[2:]
        elif len(s) == 9:
            s = '0' + s
        return s

    def get_phone_by_cccd(self, cccd):
        """
        Tra cứu số điện thoại theo số CCCD từ Agency Portal.
        Trả về: {"phone": "0814029489", "ops_id": "Ops270691", "zalo_link": "https://zalo.me/0814029489"}
        """
        if not cccd:
            return {"phone": "", "ops_id": "", "zalo_link": ""}

        cccd_clean = str(cccd).strip()
        if cccd_clean in self.cache:
            return self.cache[cccd_clean]

        if not self.config.get('enabled', True) or not self.config.get('cookie'):
            return {"phone": "", "ops_id": "", "zalo_link": ""}

        headers = self._get_headers()
        cookies = self._get_cookies()

        try:
            # Bước 1: Lấy ops_id theo passport_id (CCCD)
            url_list = 'https://logistics.myagencyservice.vn/api/wfm/agency/staff/ops/list'
            payload = {'passport_id': cccd_clean, 'pageno': 1, 'count': 24}
            res1 = requests.post(url_list, headers=headers, cookies=cookies, json=payload, timeout=5)
            if res1.status_code != 200:
                return {"phone": "", "ops_id": "", "zalo_link": ""}

            data1 = res1.json()
            ops_list = data1.get('data', {}).get('list') or []
            if not ops_list:
                result = {"phone": "", "ops_id": "", "zalo_link": ""}
                self.cache[cccd_clean] = result
                return result

            ops_id = ops_list[0].get('ops_id')
            if not ops_id:
                result = {"phone": "", "ops_id": "", "zalo_link": ""}
                self.cache[cccd_clean] = result
                return result

            # Bước 2: Lấy số điện thoại theo ops_id
            url_phone = f'https://logistics.myagencyservice.vn/api/wfm/agency/staff/ops/sensitive/data?ops_id={ops_id}&data_field=phone'
            res2 = requests.get(url_phone, headers=headers, cookies=cookies, timeout=5)
            if res2.status_code != 200:
                result = {"phone": "", "ops_id": ops_id, "zalo_link": ""}
                self.cache[cccd_clean] = result
                return result

            data2 = res2.json()
            raw_phone = data2.get('data', {}).get('data_detail', '')
            norm_phone = self.normalize_phone(raw_phone)
            zalo_url = f"https://zalo.me/{norm_phone}" if norm_phone else ""

            result = {
                "phone": norm_phone,
                "ops_id": ops_id,
                "zalo_link": zalo_url
            }
            self.cache[cccd_clean] = result
            return result

        except Exception as e:
            print(f"[!] Lỗi tra cứu SĐT Agency Portal: {e}")
            return {"phone": "", "ops_id": "", "zalo_link": ""}

    def test_connection(self):
        """Kiểm tra kết nối và tính hợp lệ của Cookie Agency Portal"""
        if not self.config.get('cookie'):
            return {"success": False, "message": "Chưa có Cookie Agency Portal"}
        headers = self._get_headers()
        cookies = self._get_cookies()
        try:
            url_list = 'https://logistics.myagencyservice.vn/api/wfm/agency/staff/ops/list'
            payload = {'passport_id': '006308000074', 'pageno': 1, 'count': 1}
            res = requests.post(url_list, headers=headers, cookies=cookies, json=payload, timeout=6)
            if res.status_code == 200:
                data = res.json()
                if data.get('code') == 0 or 'data' in data:
                    return {"success": True, "message": "Kết nối Agency Portal thành công! Cookie hợp lệ."}
                else:
                    return {"success": False, "message": f"Cookie có thể đã hết hạn ({data.get('message', 'Không rõ')})"}
            elif res.status_code in [401, 403]:
                return {"success": False, "message": f"Cookie Agency Portal đã hết hạn (HTTP {res.status_code})."}
            else:
                return {"success": False, "message": f"HTTP {res.status_code} từ Agency Portal"}
        except Exception as e:
            return {"success": False, "message": f"Lỗi kết nối tới Agency Portal: {str(e)}"}
