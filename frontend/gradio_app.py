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
from config_loader import RESULTS_DIR

API_BASE_URL = "http://localhost:8002"


def upload_file_to_api(file_path):
    """上傳檔案到 FastAPI 後端"""
    try:
        with open(file_path, "rb") as f:
            files = {"file": (Path(file_path).name, f)}
            response = requests.post(f"{API_BASE_URL}/api/upload", files=files, timeout=30)
            return response.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


def start_ocr_task_api(file_path, prompt):
    """啟動 OCR 任務"""
    try:
        payload = {"file_path": file_path, "prompt": prompt}
        response = requests.post(f"{API_BASE_URL}/api/start", json=payload, timeout=30)
        return response.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


def wait_for_task_completion(task_id, max_wait_seconds=600):
    """輪詢等待任務完成"""
    max_retries = max_wait_seconds
    retry_count = 0
    
    while retry_count < max_retries:
        time.sleep(1)
        retry_count += 1
        
        try:
            response = requests.get(f"{API_BASE_URL}/api/result/{task_id}", timeout=10)
            result = response.json()
            
            if result.get("status") == "success" and result.get("state") == "finished":
                return {"status": "finished", "result": result}
            elif result.get("status") == "error":
                return {"status": "error", "message": result.get("message", "未知錯誤")}
        except Exception as e:
            if retry_count >= 3:  # 前 3 次重試不回報錯誤
                print(f"⚠️ 輪詢錯誤 (第 {retry_count} 次): {e}")
    
    return {"status": "error", "message": "任務執行逾時"}


def get_result_files_api(task_id):
    """取得結果檔案列表"""
    try:
        response = requests.get(f"{API_BASE_URL}/api/result/{task_id}", timeout=10)
        return response.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_folder_structure_api(folder_path):
    """取得資料夾結構"""
    try:
        response = requests.get(f"{API_BASE_URL}/api/folder", params={"path": folder_path}, timeout=10)
        return response.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


def preview_file_api(file_path):
    """預覽檔案內容"""
    try:
        response = requests.get(f"{API_BASE_URL}/api/file/content", params={"path": file_path}, timeout=10)
        if response.headers.get("content-type", "").startswith("image"):
            return response.content
        else:
            return response.json().get("content", "")
    except Exception as e:
        return f"錯誤: {str(e)}"


def process_ocr(file, prompt):
    """處理 OCR 任務的主函式"""
    if file is None:
        return "❌ 請先上傳檔案", None
    
    upload_result = upload_file_to_api(file.name)
    
    if upload_result.get("status") != "success":
        return f"❌ 上傳失敗: {upload_result.get('message')}", None
    
    file_path = upload_result["file_path"]
    
    start_result = start_ocr_task_api(file_path, prompt)
    
    if start_result.get("status") != "running":
        return f"❌ 任務啟動失敗: {start_result.get('message')}", None
    
    task_id = start_result["task_id"]
    
    # 輪詢等待任務完成
    completion_result = wait_for_task_completion(task_id)
    
    if completion_result.get("status") == "error":
        return f"❌ 任務執行失敗: {completion_result.get('message', '未知錯誤')}", None
    
    # 取得結果檔案
    result = get_result_files_api(task_id)
    
    if result.get("status") != "success":
        return f"❌ 取得結果失敗: {result.get('message')}", None
    
    result_dir = result.get("result_dir", "")
    
    return f"✅ 任務完成！\n任務 ID: {task_id}\n結果目錄: {result_dir}", result_dir


def load_folder_structure(folder_path):
    """載入資料夾結構,返回可點擊的檔案列表"""
    if not folder_path or not Path(folder_path).exists():
        return gr.update(choices=[], value=None)
    
    result = get_folder_structure_api(folder_path)
    
    if result.get("status") != "success":
        return gr.update(choices=[], value=None)
    
    def collect_items(items, parent_path=""):
        """收集所有檔案和資料夾的路徑"""
        item_list = []
        for item in items:
            if item["type"] == "folder":
                # 資料夾顯示為 📁 開頭
                display_name = f"📁 {item['name']}"
                item_list.append((display_name, item['path']))
                # 遞迴加入子項目
                if 'children' in item:
                    item_list.extend(collect_items(item['children'], item['path']))
            else:
                # 檔案顯示為 📄 開頭
                display_name = f"📄 {item['name']}"
                item_list.append((display_name, item['path']))
        return item_list
    
    items = collect_items(result.get("children", []))
    
    return gr.update(choices=items, value=None)


def handle_file_selection(selected_path):
    """處理檔案選擇,如果是檔案則預覽,如果是資料夾則展開"""
    if not selected_path:
        return None, "<div style='padding:20px;text-align:center;color:#999;'>請選擇檔案進行預覽</div>"
    
    path_obj = Path(selected_path)
    
    # 如果是資料夾,回傳訊息
    if path_obj.is_dir():
        return None, "<div style='padding:20px;text-align:center;color:#999;'>這是資料夾,請選擇檔案進行預覽</div>"
    
    # 如果是檔案,填入路徑並預覽
    if path_obj.is_file():
        preview_html = preview_file(selected_path)
        return selected_path, preview_html
    
    return None, "<div style='padding:20px;color:red;'>❌ 無效的路徑</div>"


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
        try:
            with open(file.name, "rb") as img_f:
                img_bytes = img_f.read()
                img_b64 = base64.b64encode(img_bytes).decode()
            ext = Path(file.name).suffix.lower().replace('.', '')
            return f'<div style="text-align:center;"><img src="data:image/{ext};base64,{img_b64}" style="max-width:100%;max-height:400px;border:1px solid #ddd;border-radius:4px;" /></div>'
        except Exception as e:
            return f"<div style='padding:20px;color:red;'>❌ 圖片載入失敗: {str(e)}</div>"
    
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
        return "<div style='padding:20px;color:red;'>❌ 檔案路徑無效</div>"
    
    file_path_obj = Path(file_path)
    
    # 如果是圖片，轉為 base64 內嵌
    if file_path_obj.suffix.lower() in [".png", ".jpg", ".jpeg"]:
        import base64
        try:
            with open(file_path, "rb") as img_f:
                img_bytes = img_f.read()
                img_b64 = base64.b64encode(img_bytes).decode()
            ext = file_path_obj.suffix.lower().replace('.', '')
            return f'<div style="text-align:center;"><img src="data:image/{ext};base64,{img_b64}" style="max-width:100%;max-height:600px;border:1px solid #ddd;border-radius:4px;" /></div>'
        except Exception as e:
            return f"<div style='padding:20px;color:red;'>❌ 圖片載入失敗: {str(e)}</div>"
    
    # 如果是 PDF，顯示 iframe
    elif file_path_obj.suffix.lower() == ".pdf":
        # 找出相對於 RESULTS_DIR 的路徑
        try:
            rel_path = file_path_obj.relative_to(RESULTS_DIR)
            url = f"{API_BASE_URL}/results/{rel_path.as_posix()}"
        except ValueError:
            # 如果不在 results 資料夾，可能在 uploads
            pdf_name = file_path_obj.name
            url = f"{API_BASE_URL}/uploads/{pdf_name}"
        
        return f'<iframe src="{url}" width="100%" height="600px" style="border:1px solid #888;border-radius:4px;">您的瀏覽器不支援 PDF 預覽</iframe>'
    
    # 其他文字檔案
    else:
        content = preview_file_api(file_path)
        if isinstance(content, str) and content.startswith("錯誤"):
            return f"<div style='padding:20px;color:red;'>{content}</div>"
        # 使用 pre 標籤保持格式，設定深色文字
        escaped_content = str(content).replace('<', '&lt;').replace('>', '&gt;')
        return f'<pre style="padding:15px;background:#f5f5f5;border:1px solid #ddd;border-radius:4px;max-height:600px;overflow:auto;font-family:monospace;white-space:pre-wrap;color:#333;">{escaped_content}</pre>'


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
            gr.Markdown("### 📂 檔案瀏覽器")
            folder_path_input = gr.Textbox(
                label="瀏覽資料夾路徑",
                value=str(RESULTS_DIR),
                placeholder="輸入資料夾路徑..."
            )
            refresh_btn = gr.Button("🔄 重新整理")
            folder_tree_output = gr.Dropdown(
                label="檔案結構 (選擇檔案進行預覽)",
                choices=[],
                interactive=True,
                allow_custom_value=False
            )
    
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
        # 統一的預覽框（支援圖片、文字、PDF）
        unified_preview = gr.HTML(
            label="檔案預覽",
            value="<div style='padding:20px;text-align:center;color:#999;'>請輸入檔案路徑並點擊預覽按鈕</div>"
        )
    
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
        outputs=[status_output, folder_path_input]
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
    
    # 當選擇檔案時,自動填入路徑並預覽
    folder_tree_output.change(
        fn=handle_file_selection,
        inputs=[folder_tree_output],
        outputs=[preview_path_input, unified_preview]
    )
    
    preview_btn.click(
        fn=preview_file,
        inputs=[preview_path_input],
        outputs=[unified_preview]
    )
    
    folder_path_input.change(
        fn=load_folder_structure,
        inputs=[folder_path_input],
        outputs=[folder_tree_output]
    )


if __name__ == "__main__":
    demo.launch(
        server_name="localhost",
        server_port=7861,
        share=False
    )