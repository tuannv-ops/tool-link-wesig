import os
import sys

# Thư mục gốc chứa toàn bộ mã nguồn của dự án
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
os.chdir(ROOT_DIR)

import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    auto_open = 'RENDER' not in os.environ and 'PORT' not in os.environ
    app.run_server(port=port, auto_open=auto_open)
