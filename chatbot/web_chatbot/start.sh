#!/bin/bash

# ===========================================
# Script khởi động Web Chatbot
# ===========================================

echo "🚀 Khởi động Iterative Graph RAG Web Chatbot"
echo "============================================="

# Kiểm tra Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 chưa được cài đặt!"
    exit 1
fi

# Kiểm tra thư mục
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

# Cài đặt dependencies nếu cần
echo "📦 Kiểm tra dependencies..."
cd "$BACKEND_DIR"

if [ ! -f ".deps_installed" ]; then
    echo "📥 Cài đặt dependencies..."
    pip install -r requirements.txt
    touch .deps_installed
fi

# Khởi động Backend với auto-reload
echo ""
echo "🔧 Khởi động Backend API (port 8000) với auto-reload..."
cd "$BACKEND_DIR"
uvicorn app:app --host 0.0.0.0 --port 8000 --reload --reload-dir "$BACKEND_DIR" &
BACKEND_PID=$!

# Đợi backend khởi động
echo "⏳ Đợi backend khởi động..."
sleep 5

# Khởi động Frontend (sử dụng Python HTTP server)
echo ""
echo "🌐 Khởi động Frontend (port 3000)..."
cd "$FRONTEND_DIR"
python3 -m http.server 3000 &
FRONTEND_PID=$!

echo ""
echo "============================================="
echo "✅ Web Chatbot đã sẵn sàng!"
echo ""
echo "📡 Backend API:  http://localhost:8000"
echo "🌐 Frontend:     http://localhost:3000"
echo ""
echo "📝 Nhấn Ctrl+C để dừng server"
echo "============================================="

# Cleanup function
cleanup() {
    echo ""
    echo "🛑 Đang dừng servers..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    echo "👋 Goodbye!"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Keep script running
wait

cd /home/ubuntu/Documents/Social-Network-Analysis/chatbot/web_chatbot && pkill -f "uvicorn.*app:app" 2>/dev/null; echo "Đã dừng server cũ (nếu có)"