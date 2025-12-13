"""
file_manager.py
---------------
本模組負責：
1. 統一管理使用者上傳檔案的保存；
2. 自動為每次推理建立獨立的結果資料夾；
3. 提供路徑生成、檔案類型判斷等工具函式；
4. 保證檔案名稱安全、防止命名衝突。
"""

import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Tuple

from config_loader import UPLOAD_DIR, RESULTS_DIR


# ========== Step 1. 檔案類型判斷 ==========
def detect_file_type(file_path: str) -> str:
    """
    根據副檔名自動判斷檔案類型
    回傳值: 'pdf' 或 'image'
    """
    ext = Path(file_path).suffix.lower()
    if ext in [".pdf"]:
        return "pdf"
    elif ext in [".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"]:
        return "image"
    else:
        raise ValueError(f"❌ 不支援的檔案類型: {ext}")


# ========== Step 2. 保存上傳檔案 ==========
def save_uploaded_file(file, filename: str = None) -> Tuple[str, str]:
    """
    保存上傳檔案到 workspace/uploads/
    - 自動生成唯一檔案名稱（避免重複）
    - 回傳保存路徑與檔案類型
    """
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    # 生成唯一檔案名稱
    ext = Path(file.filename).suffix
    if not filename:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        filename = f"user_upload_{timestamp}_{unique_id}{ext}"
    
    file_path = Path(UPLOAD_DIR) / filename
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    file_type = detect_file_type(str(file_path))
    
    print(f"📤 檔案已保存: {file_path} ({file_type})")
    
    return str(file_path), file_type


# ========== Step 3. 建立結果目錄 ==========
def create_result_dir(prefix: str = "task") -> str:
    """
    為每次推理任務建立獨立結果資料夾
    範例: workspace/results/task_20251022_153045_ab12cd34/
    """
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    dir_name = f"{prefix}_{timestamp}_{unique_id}"
    result_dir = Path(RESULTS_DIR) / dir_name
    os.makedirs(result_dir, exist_ok=True)
    
    print(f"📁 已建立結果目錄: {result_dir}")
    return str(result_dir)


# ========== Step 4. 清理舊檔案（可選） ==========
def cleanup_uploads(max_keep: int = 10):
    """
    清理 uploads 資料夾中舊檔案，僅保留最近 N 個
    """
    files = sorted(Path(UPLOAD_DIR).glob("*"), key=os.path.getmtime, reverse=True)
    for old_file in files[max_keep:]:
        try:
            os.remove(old_file)
        except Exception as e:
            print(f"⚠️ 刪除舊檔案失敗: {old_file}, {e}")


# ========== Step 5. 檔案列表工具 ==========
def list_result_files(result_dir: str) -> list:
    """
    列出指定結果目錄中的所有檔案（遞迴）
    回傳: 檔案相對路徑列表
    """
    result_dir = Path(result_dir)
    if not result_dir.exists():
        return []
    
    files = []
    for path in result_dir.rglob("*"):
        if path.is_file():
            rel_path = path.relative_to(result_dir)
            files.append(str(rel_path))
    return files


# ========== Step 6. 除錯輸出（可選） ==========
if __name__ == "__main__":
    # 模擬除錯執行
    dummy_file_path = Path(UPLOAD_DIR) / "test.png"
    print("[DEBUG] 建立結果目錄:", create_result_dir())
    print("[DEBUG] 當前結果目錄檔案列表:", list_result_files(RESULTS_DIR))
