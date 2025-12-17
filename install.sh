#!/bin/bash
###############################################################################
# DeepSeek-OCR 一鍵環境安裝腳本（增強版）
# 功能：
#  - 自動建立 Conda 環境
#  - 安裝 PyTorch + vLLM + Flash-Attn
#  - 自動下載 DeepSeek-OCR 模型
#  - 自動建立 .env 檔案並寫入 MODEL_PATH
###############################################################################

set -e
exec > >(tee setup.log) 2>&1

# 彩色輸出
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
RESET="\033[0m"

echo -e "${GREEN}============================================================${RESET}"
echo -e "🚀 ${YELLOW}環境初始化開始...${RESET}"
echo -e "${GREEN}============================================================${RESET}"

# 檢查 Conda
if ! command -v conda &> /dev/null; then
    echo -e "${RED}❌ 未偵測到 Conda，請先安裝 Miniconda 或 Anaconda。${RESET}"
    exit 1
fi

# 初始化 Conda
source $(conda info --base)/etc/profile.d/conda.sh

# 1️⃣ 建立虛擬環境
echo -e "${YELLOW}>>> Step 1. 建立 Conda 環境 deepseek-ocr${RESET}"
conda create -n deepseek-ocr python=3.12.9 -y
conda activate deepseek-ocr

# 2️⃣ 安裝 PyTorch (CUDA 11.8)
echo -e "${YELLOW}>>> Step 2. 安裝 PyTorch + CUDA 11.8${RESET}"
pip install torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu118

# 3️⃣ 安裝本地 vLLM 套件
echo -e "${YELLOW}>>> Step 3. 安裝本地 vLLM 套件${RESET}"
VLLM_PKG="./packages/vllm-0.8.5+cu118-cp38-abi3-manylinux1_x86_64.whl"
if [ -f "$VLLM_PKG" ]; then
    pip install "$VLLM_PKG"
else
    echo -e "${RED}❌ 未找到 $VLLM_PKG 檔案，請檢查路徑是否正確。${RESET}"
    exit 1
fi

# 4️⃣ 安裝 Python 專案相依套件
echo -e "${YELLOW}>>> Step 4. 安裝 requirements.txt + flash-attn${RESET}"
pip install -r requirements.txt
pip install flash-attn==2.7.3 --no-build-isolation

# 5️⃣ 自動下載 DeepSeek-OCR 模型
echo -e "${YELLOW}>>> Step 5. 自動下載 DeepSeek-OCR 模型${RESET}"
pip install huggingface-hub
mkdir -p ./deepseek-ocr
python - <<'PY'
from huggingface_hub import snapshot_download
import sys
try:
    snapshot_download(repo_id="deepseek-ai/DeepSeek-OCR", local_dir="./deepseek-ocr")
    print("✅ 模型下載完成")
except Exception as e:
    print(f"⚠️ 模型下載失敗，請檢查網路或 huggingface 登入狀態。錯誤：{e}", file=sys.stderr)
    sys.exit(1)
PY

# 6️⃣ 建立 .env 檔案

# 取得目前專案根目錄的絕對路徑
PROJECT_DIR=$(pwd)
MODEL_DIR="${PROJECT_DIR}/deepseek-ocr"

# 建立 .env
echo -e "${YELLOW}>>> Step 8. 檢查或建立 .env 檔案${RESET}"
if [ ! -f ".env" ]; then
    echo "MODEL_PATH=${MODEL_DIR}" > .env
    echo -e "${GREEN}✅ 已建立 .env 檔案並寫入絕對路徑${RESET}"
else
    if ! grep -q "MODEL_PATH=" .env; then
        echo "MODEL_PATH=${MODEL_DIR}" >> .env
        echo -e "${GREEN}✅ 已向現有 .env 新增 MODEL_PATH（絕對路徑）${RESET}"
    else
        echo -e "${YELLOW}ℹ️ 偵測到已有 .env 檔案，已跳過寫入${RESET}"
    fi
fi

# ✅ 安裝完成
echo -e "${GREEN}============================================================${RESET}"
echo -e "🎉 所有相依套件和模型已安裝完成！"
echo -e "📦 模型路徑：./deepseek-ocr"
echo -e "⚙️  環境設定檔：.env"
echo -e "🧾 安裝日誌：setup.log"
echo -e "${GREEN}============================================================${RESET}"
