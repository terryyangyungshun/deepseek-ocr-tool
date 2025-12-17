"""
gradio_app.py
-------------
DeepSeek OCR Gradio 前端介面
"""

import sys
from pathlib import Path
import markdown 
# 將 backend 目錄加入 Python 搜尋路徑
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import gradio as gr
import requests
import time
from config_loader import RESULTS_DIR

API_BASE_URL = "http://localhost:8003"  # FastAPI 後端的 URL

# 新增一個全域集合，儲存目前已展開的資料夾路徑
EXPANDED_FOLDERS = set()


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
    """載入資料夾結構，回傳 Radio 可用的 choices（支援展開/摺疊）"""
    if not folder_path or not Path(folder_path).exists():
        return gr.update(choices=[], value=None)

    result = get_folder_structure_api(folder_path)
    if result.get("status") != "success":
        return gr.update(choices=[], value=None)

    def collect_items(items, indent=0):
        item_list = []
        for item in items:
            # 使用全形空格作為縮排，能在元件中保留寬度感
            indent_prefix = '\u3000' * indent
            if item["type"] == "folder":
                # 根據是否已展開選擇圖示與是否顯示子項
                if item['path'] in EXPANDED_FOLDERS:
                    display_name = f"{indent_prefix}📁 ▼ {item['name']}"
                    item_list.append((display_name, item['path']))
                    if 'children' in item and item['children']:
                        item_list.extend(collect_items(item['children'], indent + 1))
                else:
                    display_name = f"{indent_prefix}📁 ▶ {item['name']}"
                    item_list.append((display_name, item['path']))
            else:
                display_name = f"{indent_prefix}📄 {item['name']}"
                item_list.append((display_name, item['path']))
        return item_list

    items = collect_items(result.get("children", []))
    return gr.update(choices=items, value=None)


def handle_file_selection(selected_path, current_root_folder):
    """處理檔案/資料夾選擇：
    - 若為資料夾：切換展開/摺疊狀態，並回傳更新後的 choices（第三個輸出）
    - 若為檔案：回傳檔案路徑與預覽內容，並不變更選單
    返回值順序: preview_path_input_value, unified_preview_html, folder_tree_update
    """
    if not selected_path:
        return None, "<div style='padding:20px;text-align:center;color:#999;'>請選擇檔案進行預覽</div>", gr.update()

    path_obj = Path(selected_path)

    # 如果是資料夾,切換展開/摺疊
    if path_obj.is_dir():
        if selected_path in EXPANDED_FOLDERS:
            EXPANDED_FOLDERS.remove(selected_path)
        else:
            EXPANDED_FOLDERS.add(selected_path)

        # 重新產生選單（使用目前的 root folder 路徑）
        folder_update = load_folder_structure(current_root_folder)
        # 不顯示預覽路徑，但顯示提示文字
        return None, "<div style='padding:20px;text-align:center;color:#999;'>資料夾已切換展開/摺疊</div>", folder_update

    # 如果是檔案,填入路徑並預覽
    if path_obj.is_file():
        preview_html = preview_file(selected_path)
        # 保持選單原狀
        return selected_path, preview_html, gr.update()

    return None, "<div style='padding:20px;color:red;'>❌ 無效的路徑</div>", gr.update()


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

    # .mmd、.md、.markdown 檔案：以 markdown 呈現
    if file_path_obj.suffix.lower() in [".mmd", ".md", ".markdown"]:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            # 嘗試判斷是否為 markdown 表格或 markdown 內容
            html = markdown.markdown(content, extensions=['tables'])
            # 加上簡單樣式讓表格更好看
            style = """
            <style>
            table { border-collapse: collapse; margin: 10px 0; }
            th, td { border: 1px solid #bbb; padding: 6px 12px; }
            </style>
            """
            return style + html
        except Exception as e:
            return f"<div style='padding:20px;color:red;'>❌ 檔案讀取失敗: {str(e)}</div>"
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

    # 注入 CSS，使文件瀏覽的 Radio 選項垂直排列、每項佔一列，並修正文字與選取色彩對比
    gr.HTML("""
    <style>
    /* 容器限制：固定高度並出現滾動，避免展開時整個 block 增高 */
    #folder_tree {
        max-height: 220px !important;
        height: 220px !important;
        overflow-y: auto !important;
        padding: 6px;
        border-radius: 6px;
        margin-top: 8px;
        box-sizing: border-box;
    }

    /* 使上方 row 的左右欄等高，移除固定高度 */
    #top_row {
        display: flex !important;
        gap: 20px;
        align-items: flex-start; /* 改為頂端對齊 */
    }
    #top_row > div {
        display: flex !important;
        flex-direction: column !important;
        flex: 1 1 0 !important;
    }

    /* 深色主題：標籤為深色背景、淺色文字 */
    #folder_tree label {
        display: block !important;
        width: 100%;
        padding: 8px 10px;
        margin: 6px 0 !important;
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 6px;
        cursor: pointer;
        background: #1f2937 !important;
        color: #f5f7fa !important;
        user-select: text;
        overflow: hidden;               /* 防止換行導致高度增長 */
        white-space: nowrap;            /* 單行並省略超出內容 */
        text-overflow: ellipsis;
    }

    /* 確保內部所有文字元素都為淺色 */
    #folder_tree label, #folder_tree label * {
        color: #f5f7fa !important;
    }

    #folder_tree input[type="radio"] {
        margin-right: 8px;
        accent-color: #60a5fa;
        flex: 0 0 auto;
    }

    /* 被勾選時加強對比（稍亮的深色） */
    #folder_tree input[type="radio"]:checked + label,
    #folder_tree label:has(input[type="radio"]:checked) {
        background: #374151 !important;
        color: #ffffff !important;
        border-color: #60a5fa !important;
    }

    /* 選取文字時的樣式 */
    #folder_tree label::selection {
        background: #2563eb;
        color: #ffffff;
    }

    /* hover 效果 */
    #folder_tree label:hover {
        box-shadow: 0 1px 6px rgba(0,0,0,0.5);
        transform: translateY(-1px);
    }

    /* 捲軸美化 (Webkit) */
    #folder_tree::-webkit-scrollbar { width: 10px; }
    #folder_tree::-webkit-scrollbar-track { background: transparent; }
    #folder_tree::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.06); border-radius: 6px; }

    /* 小螢幕時保持適應：允許較小字體但仍維持固定高度 */
    @media (max-width: 600px) {
        #folder_tree label { font-size: 14px; padding: 10px; }
        #folder_tree { max-height: 180px !important; height: 180px !important; }
    }
    </style>
    """)

    with gr.Row(elem_id="top_row"):
        with gr.Column(scale=1, elem_id="left_col"):
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
            
            # 將提示詞選擇與執行狀態移到左側，提示詞在左、執行狀態在右
            gr.Markdown("### 📊 任務狀態")
            with gr.Row():
               
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
                status_output = gr.Textbox(label="執行狀態", lines=3)

            submit_btn = gr.Button("🚀 開始解析", variant="primary", elem_id="start_btn")
            
        with gr.Column(scale=1, elem_id="right_col"):
            gr.Markdown("### 📂 檔案瀏覽")
            # 右側：單一 row，左右兩欄平均分配高度
            with gr.Row(equal_height=True):  # 加入 equal_height 參數
                with gr.Column(scale=1):  # 左側：路徑輸入與重新整理
                    folder_path_input = gr.Textbox(
                        label="瀏覽資料夾路徑",
                        value=str(RESULTS_DIR),
                        placeholder="輸入資料夾路徑..."
                    )
                    refresh_btn = gr.Button("🔄 重新整理")
                with gr.Column(scale=1):  # 右側：文件瀏覽
                    folder_tree_output = gr.Radio(
                        label="文件瀏覽",
                        choices=[],
                        interactive=True,
                        type="value",
                        elem_id="folder_tree"
                    )

            # 統一的檔案預覽區（直接放在文件瀏覽下方，移除手動輸入路徑功能）
            unified_preview = gr.HTML(
                label="檔案預覽",
                value="<div style='padding:20px;text-align:center;color:#999;'>請從文件瀏覽選擇檔案進行預覽</div>"
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
    
    # 當選擇檔案或資料夾時,自動預覽（移除 preview_path_input，僅更新 unified_preview 與 folder_tree）
    folder_tree_output.change(
        fn=lambda selected_path, current_root_folder: handle_file_selection(selected_path, current_root_folder)[1:],
        inputs=[folder_tree_output, folder_path_input],
        outputs=[unified_preview, folder_tree_output]
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