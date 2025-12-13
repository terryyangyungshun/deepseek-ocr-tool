"""
config_loader.py
----------------
本模組負責：
1. 從 .env 檔案載入模型路徑與基本設定；
2. 自動建立 workspace 目錄結構（uploads / results / logs）；
3. 檢查設定合法性並輸出目前設定狀態；
4. 提供全域常數供其他模組匯入使用。
"""

import os
from pathlib import Path
from dotenv import load_dotenv


# ========== Step 1. 定義路徑常數 ==========
BASE_DIR = Path(__file__).resolve().parent.parent   # 專案根目錄（DeepSeek-OCR）
WORKSPACE_PATH = BASE_DIR / "workspace"
UPLOAD_DIR = WORKSPACE_PATH / "uploads"
RESULTS_DIR = WORKSPACE_PATH / "results"
LOGS_DIR = WORKSPACE_PATH / "logs"


# ========== Step 2. 自動建立 .env.example 檔案 ==========
ENV_FILE = BASE_DIR / ".env"
EXAMPLE_ENV_FILE = BASE_DIR / ".env.example"

if not EXAMPLE_ENV_FILE.exists():
    with open(EXAMPLE_ENV_FILE, "w", encoding="utf-8") as f:
        f.write(
            "# DeepSeek-OCR 後端設定檔案範例\n"
            "# 請複製為 .env 並修改 MODEL_PATH 路徑。\n\n"
            "MODEL_PATH=/root/autodl-tmp/deepseek-ocr\n"
            "DEVICE_ID=0\n"
            "MAX_CONCURRENCY=10\n"
        )


# ========== Step 3. 載入 .env 檔案 ==========
if not ENV_FILE.exists():
    print("[⚠️ 警告] 未找到 .env 檔案，已建立範例 .env.example。")
    print("請複製 .env.example → .env 並填寫 MODEL_PATH 後重新啟動。")

load_dotenv(ENV_FILE)


# ========== Step 4. 讀取設定項 ==========
MODEL_PATH = os.getenv("MODEL_PATH", None)
DEVICE_ID = os.getenv("DEVICE_ID", "0")
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "10"))


# ========== Step 5. 檢查模型路徑合法性 ==========
if MODEL_PATH is None or MODEL_PATH.strip() == "":
    raise ValueError("❌ 未在 .env 中設定 MODEL_PATH，請填寫模型路徑後重啟服務。")

if not Path(MODEL_PATH).exists():
    print(f"[⚠️ 警告] 指定的模型路徑不存在: {MODEL_PATH}")
    print("請確保已下載 DeepSeek-OCR 模型權重。")


# ========== Step 6. 自動建立工作目錄 ==========
for directory in [WORKSPACE_PATH, UPLOAD_DIR, RESULTS_DIR, LOGS_DIR]:
    os.makedirs(directory, exist_ok=True)


# ========== Step 7. 除錯輸出（列印目前有效設定） ==========
print("=" * 60)
print("🔧 DeepSeek-OCR 後端設定載入完成")
print(f"📁 模型路徑:      {MODEL_PATH}")
print(f"🖥️  GPU 設備:     {DEVICE_ID}")
print(f"⚙️  最大平行處理任務數: {MAX_CONCURRENCY}")
print(f"📂 工作區路徑:    {WORKSPACE_PATH}")
print("=" * 60)


# ========== Step 8. 匯出可供全域呼叫的常數 ==========
__all__ = [
    "MODEL_PATH",
    "DEVICE_ID",
    "MAX_CONCURRENCY",
    "WORKSPACE_PATH",
    "UPLOAD_DIR",
    "RESULTS_DIR",
    "LOGS_DIR"
]