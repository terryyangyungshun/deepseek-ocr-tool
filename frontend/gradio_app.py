"""
gradio_app.py
-------------
DeepSeek OCR Gradio 前端介面
"""

import sys
from pathlib import Path

# 將 backend 目錄加入 Python 搜尋路徑
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import gradio as gr
import requests
import time
import asyncio
import websockets
import json
from config_loader import RESULTS_DIR

API_BASE_URL = "http://localhost:8002"
WS_BASE_URL = "ws://localhost:8002"


def upload_file_to_api(file_path):
    """上傳檔案到 FastAPI 後端"""
    try:
        with open(file_path, "rb") as f:
            files = {"file": (Path(file_path).name, f)}
            response = requests.post(f"{API_BASE_URL}/api/upload", files=files)
            return response.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


def start_ocr_task_api(file_path, prompt):
    """啟動 OCR 任務"""
    try:
        payload = {"file_path": file_path, "prompt": prompt}
        response = requests.post(f"{API_BASE_URL}/api/start", json=payload)
        return response.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def monitor_progress_via_websocket(task_id, progress_callback):
    """透過 WebSocket 監聽任務進度"""
    try:
        uri = f"{WS_BASE_URL}/ws/progress/{task_id}"
        async with websockets.connect(uri) as websocket:
            while True:
                message = await websocket.recv()
                data = json.loads(message)
                
                # 如果收到進度更新
                if "progress" in data:
                    progress_callback(data["progress"])
                
                # 如果收到完成訊息
                if data.get("status") == "finished" or data.get("status") == "error":
                    return data
    except Exception as e:
        print(f"WebSocket 錯誤: {e}")
        return None


def get_task_progress_api(task_id):
    """查詢任務進度（備用方案）"""
    try:
        response = requests.get(f"{API_BASE_URL}/api/progress/{task_id}")
        return response.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_result_files_api(task_id):
    """取得結果檔案列表"""
    try:
        response = requests.get(f"{API_BASE_URL}/api/result/{task_id}")
        return response.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_folder_structure_api(folder_path):
    """取得資料夾結構"""
    try:
        response = requests.get(f"{API_BASE_URL}/api/folder", params={"path": folder_path})
        return response.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


def preview_file_api(file_path):
    """預覽檔案內容"""
    try:
        response = requests.get(f"{API_BASE_URL}/api/file/content", params={"path": file_path})
        if response.headers.get("content-type", "").startswith("image"):
            return response.content
        else:
            return response.json().get("content", "")
    except Exception as e:
        return f"錯誤: {str(e)}"


def process_ocr(file, prompt, progress=gr.Progress()):
    """處理 OCR 任務的主函式"""
    if file is None:
        return "❌ 請先上傳檔案", "", None, ""
    
    progress(0, desc="📤 上傳檔案中...")
    upload_result = upload_file_to_api(file.name)
    
    if upload_result.get("status") != "success":
        return f"❌ 上傳失敗: {upload_result.get('message')}", "", None, ""
    
    file_path = upload_result["file_path"]
    
    progress(0.1, desc="🚀 啟動 OCR 任務...")
    start_result = start_ocr_task_api(file_path, prompt)
    
    if start_result.get("status") != "running":
        return f"❌ 任務啟動失敗: {start_result.get('message')}", "", None, ""
    
    task_id = start_result["task_id"]
    
    # 定義進度回調函式
    def update_progress(percent):
        progress(percent / 100, desc=f"⚙️ 處理中... {percent}%")
    
    # 嘗試使用 WebSocket 監聽進度
    try:
        result = asyncio.run(monitor_progress_via_websocket(task_id, update_progress))
        
        # 如果 WebSocket 成功且收到完成訊息
        if result and result.get("status") == "finished":
            pass  # 繼續處理結果
        elif result and result.get("status") == "error":
            return f"❌ 任務執行失敗", "", None, ""
        else:
            # WebSocket 失敗，回退到輪詢方式
            raise Exception("WebSocket 連線失敗，使用輪詢方式")
    
    except Exception as e:
        print(f"使用輪詢方式: {e}")
        # 輪詢任務進度（備用方案）
        while True:
            time.sleep(1)
            progress_result = get_task_progress_api(task_id)
            
            if progress_result.get("status") != "success":
                return f"❌ 查詢進度失敗: {progress_result.get('message')}", "", None, ""
            
            state = progress_result.get("state", "unknown")
            current_progress = int(progress_result.get("progress", 0))
            
            progress(current_progress / 100, desc=f"⚙️ 處理中... {current_progress}%")
            
            if state == "finished":
                break
            elif state == "error":
                return f"❌ 任務執行失敗", "", None, ""
    
    # 取得結果檔案
    result = get_result_files_api(task_id)
    
    if result.get("status") != "success":
        return f"❌ 取得結果失敗: {result.get('message')}", "", None, ""
    
    result_dir = result.get("result_dir", "")
    files = result.get("files", [])
    
    file_list = "\n".join([f"📄 {f}" for f in files]) if files else "無結果檔案"
    
    return f"✅ 任務完成！\n任務 ID: {task_id}", file_list, result_dir, ""


def load_folder_structure(folder_path):
    """載入資料夾結構"""
    if not folder_path or not Path(folder_path).exists():
        return "❌ 資料夾路徑無效"
    
    result = get_folder_structure_api(folder_path)
    
    if result.get("status") != "success":
        return f"❌ 載入失敗: {result.get('message')}"
    
    def format_tree(items, indent=0):
        lines = []
        for item in items:
            prefix = "📁" if item["type"] == "folder" else "📄"
            lines.append("  " * indent + f"{prefix} {item['name']}")
            if item["type"] == "folder" and "children" in item:
                lines.extend(format_tree(item["children"], indent + 1))
        return lines
    
    tree = format_tree(result.get("children", []))
    return "\n".join(tree) if tree else "空資料夾"


def preview_uploaded_file(file):
    """預覽上傳的檔案"""
    if file is None:
        return ""

    # 先將檔案上傳到 FastAPI，取得 file_path
    upload_result = upload_file_to_api(file.name)
    if upload_result.get("status") != "success":
        return f"<div style='padding:20px;color:red;'>❌ 上傳失敗: {upload_result.get('message')}</div>"

    file_path = upload_result["file_path"]
    file_type = upload_result.get("file_type", "")

    # 如果是圖片，直接顯示（用 base64 內嵌）
    if file_type in ["png", "jpg", "jpeg"] or str(file_path).lower().endswith((".png", ".jpg", ".jpeg")):
        import base64
        with open(file.name, "rb") as img_f:
            img_bytes = img_f.read()
            img_b64 = base64.b64encode(img_bytes).decode()
        ext = Path(file.name).suffix.lower().replace('.', '')
        return f'<div style="text-align:center;"><img src="data:image/{ext};base64,{img_b64}" style="max-width:100%;max-height:400px;border:1px solid #ddd;border-radius:4px;" /></div>'
    # 如果是 PDF，顯示可滾動預覽（iframe）
    elif file_type == "pdf" or str(file_path).lower().endswith(".pdf"):
        # 產生 /uploads/xxx.pdf 路徑（上傳的檔案在 uploads 資料夾）
        pdf_name = Path(file_path).name
        url = f"{API_BASE_URL}/uploads/{pdf_name}"
        return f'<iframe src="{url}" width="100%" height="500px" style="border:1px solid #888;border-radius:4px;">您的瀏覽器不支援 PDF 預覽</iframe>'
    else:
        return f"<div style='padding:20px;text-align:center;color:#666;'>📎 檔案: {Path(file_path).name}</div>"


def preview_file(file_path):
    """預覽選定的檔案"""
    if not file_path or not Path(file_path).exists():
        return None, "❌ 檔案路徑無效"
    
    file_path_obj = Path(file_path)
    
    if file_path_obj.suffix.lower() in [".png", ".jpg", ".jpeg"]:
        return str(file_path), ""
    else:
        content = preview_file_api(file_path)
        return None, content


# 建立 Gradio 介面
with gr.Blocks(title="DeepSeek OCR 識別檢測") as demo:
    gr.Markdown("# 🔍 DeepSeek OCR 識別檢測")
    gr.Markdown("上傳 PDF 或圖片檔案，進行 OCR 文字識別")
    
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 📤 上傳文件")
            file_input = gr.File(
                label="上傳文件 (PDF / PNG / JPG)",
                file_types=[".pdf", ".png", ".jpg", ".jpeg"]
            )
            
            # 統一的上傳檔案預覽框（圖片、PDF、其他檔案都在這裡顯示）
            uploaded_preview = gr.HTML(
                label="檔案預覽",
                value=""  # 預設不顯示
            )
            
            prompt_input = gr.Dropdown(
                label="提示詞選擇",
                choices=[
                    "<image>\n<|grounding|>Convert the document to markdown.",
                    "<image>\nOCR this image.",
                    "<image>\nFree OCR.",
                    "<image>\nParse the figure.",
                    "<image>\nDescribe this image in detail."
                ],
                value="<image>\n<|grounding|>Convert the document to markdown.",
                interactive=True
            )
            submit_btn = gr.Button("🚀 開始解析", variant="primary")
            
            gr.Markdown("### 📊 任務狀態")
            status_output = gr.Textbox(label="執行狀態", lines=3)
        
        with gr.Column(scale=1):
            gr.Markdown("### 📂 文件瀏覽器")
            folder_path_input = gr.Textbox(
                label="結果資料夾路徑",
                value=str(RESULTS_DIR),
                placeholder="輸入資料夾路徑..."
            )
            refresh_btn = gr.Button("🔄 重新整理")
            folder_tree_output = gr.Textbox(
                label="資料夾結構",
                lines=15,
                interactive=False
            )
            files_output = gr.Textbox(label="任務結果檔案", lines=5)
    
    with gr.Row():
        gr.Markdown("### 👁️ 檔案預覽")
    
    with gr.Row():
        preview_path_input = gr.Textbox(
            label="檔案路徑",
            placeholder="輸入完整檔案路徑進行預覽...",
            scale=4
        )
        preview_btn = gr.Button("👁️ 預覽", scale=1)
    
    with gr.Row():
        with gr.Column(scale=1):
            image_preview = gr.Image(label="圖片預覽", type="filepath")
        with gr.Column(scale=1):
            text_preview = gr.Textbox(label="文字預覽", lines=20)
    
    # 事件綁定
    # 上傳檔案時自動預覽
    file_input.change(
        fn=preview_uploaded_file,
        inputs=[file_input],
        outputs=[uploaded_preview]
    )
    
    submit_btn.click(
        fn=process_ocr,
        inputs=[file_input, prompt_input],
        outputs=[status_output, files_output, folder_path_input, folder_tree_output]
    ).then(
        fn=load_folder_structure,
        inputs=[folder_path_input],
        outputs=[folder_tree_output]
    )
    
    refresh_btn.click(
        fn=load_folder_structure,
        inputs=[folder_path_input],
        outputs=[folder_tree_output]
    )
    
    preview_btn.click(
        fn=preview_file,
        inputs=[preview_path_input],
        outputs=[image_preview, text_preview]
    )
    
    # 當結果資料夾更新時自動重新整理
    folder_path_input.change(
        fn=load_folder_structure,
        inputs=[folder_path_input],
        outputs=[folder_tree_output]
    )


if __name__ == "__main__":
    demo.launch(
        server_name="localhost",
        server_port=7860,
        share=False
    )