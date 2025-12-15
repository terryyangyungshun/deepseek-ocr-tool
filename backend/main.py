"""
main.py
-------
DeepSeek OCR FastAPI 後端入口
"""

import uuid
import asyncio
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse 
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi import Query
from typing import Optional
import json

from file_manager import save_uploaded_file
from inference_runner import run_ocr_task, read_task_state
from config_loader import UPLOAD_DIR, RESULTS_DIR


app = FastAPI(title="DeepSeek OCR 後端", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

active_connections = {}


async def send_progress(websocket: WebSocket, task_id: str, percent: int):
    """WebSocket 即時進度"""
    try:
        await websocket.send_json({"task_id": task_id, "progress": percent})
    except Exception as e:
        print(f"❌ WebSocket 發送失敗: {e}")
        # 移除無效連線
        if task_id in active_connections:
            del active_connections[task_id]


@app.get("/api/folder")
async def get_folder_structure(path: str = Query(..., description="結果資料夾路徑")):
    """遞迴回傳資料夾結構（包含二級資料夾）"""
    base_path = Path(path)
    if not base_path.exists() or not base_path.is_dir():
        return {"status": "error", "message": f"路徑無效: {path}"}

    def build_tree(directory: Path):
        items = []
        try:
            for entry in sorted(directory.iterdir(), key=lambda e: (e.is_file(), e.name.lower())):
                if entry.is_dir():
                    items.append({
                        "name": entry.name,
                        "type": "folder",
                        "path": str(entry),
                        "children": build_tree(entry)
                    })
                else:
                    items.append({
                        "name": entry.name,
                        "type": "file",
                        "path": str(entry)
                    })
        except PermissionError:
            pass  # 跳過無權限的資料夾
        return items

    return {
        "status": "success",
        "path": str(base_path),
        "children": build_tree(base_path)
    }


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """上傳檔案"""
    try:
        file_path, file_type = save_uploaded_file(file)
        return {"status": "success", "file_path": file_path, "file_type": file_type}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/start")
async def start_ocr_task(payload: dict, background_tasks: BackgroundTasks):
    """啟動 OCR 任務"""
    file_path = payload.get("file_path")
    prompt = payload.get("prompt", "<image>\nFree OCR.")
    if not file_path or not Path(file_path).exists():
        return {"status": "error", "message": "檔案不存在"}

    task_id = str(uuid.uuid4())[:8]

    async def background_task():
        def on_progress(p):
            if task_id in active_connections:
                ws = active_connections[task_id]
                try:
                    # 使用 asyncio 在事件循環中發送
                    loop = asyncio.get_event_loop()
                    loop.create_task(send_progress(ws, task_id, p))
                except Exception as e:
                    print(f"❌ 進度發送錯誤: {e}")

        # 在背景執行 OCR 任務
        result = await asyncio.to_thread(
            run_ocr_task, 
            input_path=file_path, 
            task_id=task_id, 
            on_progress=on_progress, 
            prompt=prompt
        )

        # 發送完成訊息
        if task_id in active_connections:
            ws = active_connections[task_id]
            try:
                await ws.send_json(result)
            except Exception as e:
                print(f"❌ 完成訊息發送失敗: {e}")

    background_tasks.add_task(background_task)
    return {"status": "running", "task_id": task_id}


@app.websocket("/ws/progress/{task_id}")
async def websocket_progress(websocket: WebSocket, task_id: str):
    """WebSocket 進度推播"""
    await websocket.accept()
    active_connections[task_id] = websocket
    print(f"🌐 WebSocket 已連線: {task_id}")
    try:
        while True:
            # 保持連線活躍
            data = await websocket.receive_text()
            # 如果收到 ping，回應 pong
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        print(f"❌ WebSocket 正常斷線: {task_id}")
    except Exception as e:
        print(f"❌ WebSocket 異常: {task_id} - {e}")
    finally:
        if task_id in active_connections:
            del active_connections[task_id]


@app.get("/api/result/{task_id}")
async def get_result_files(task_id: str):
    """取得結果檔案"""
    state = read_task_state(task_id)
    if not state:
        return {"status": "error", "message": "任務不存在或狀態檔案遺失"}

    status = state.get("status", "unknown")
    if status == "running":
        return {"status": "running", "task_id": task_id, "progress": state.get("progress", 0)}
    if status == "error":
        return {"status": "error", "message": state.get("message", "未知錯誤")}
    if status != "finished":
        return {"status": "error", "message": f"未知狀態: {status}"}

    result_dir = Path(state["result_dir"])
    if not result_dir.exists():
        return {"status": "error", "message": "結果目錄不存在"}

    files = state.get("files", [])
    if not files:
        for path in result_dir.rglob("*"):
            if path.is_file():
                files.append(str(path.relative_to(result_dir)))

    return {
        "status": "success",
        "task_id": task_id,
        "state": "finished",
        "result_dir": str(result_dir),
        "files": files,
    }
    

@app.get("/api/progress/{task_id}")
async def get_task_progress(task_id: str):
    """查詢任務即時進度"""
    state = read_task_state(task_id)
    if not state:
        return {"status": "error", "message": "任務不存在或狀態檔案遺失"}

    progress = state.get("progress", 0)
    status = state.get("status", "unknown")

    return {
        "status": "success",
        "task_id": task_id,
        "state": status,
        "progress": progress
    }


@app.get("/api/file/content")
async def preview_file(path: str):
    """檔案預覽"""
    file_path = Path(path)
    if not file_path.exists():
        return {"status": "error", "message": "檔案不存在"}

    if file_path.suffix.lower() in [".png", ".jpg", ".jpeg", ".gif", ".bmp"]:
        return FileResponse(file_path)
    else:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            return JSONResponse({"content": content})
        except Exception as e:
            return JSONResponse({"status": "error", "message": f"讀取失敗: {str(e)}"})


# 靜態檔案服務 - 注意順序很重要
app.mount("/results", StaticFiles(directory=str(RESULTS_DIR)), name="results")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8002)
