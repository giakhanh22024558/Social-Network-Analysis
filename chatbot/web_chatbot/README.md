# 🤖 Iterative Graph RAG Web Chatbot

Web chatbot với giao diện hiện đại cho hệ thống Iterative Graph RAG.

## 📁 Cấu trúc thư mục

```
web_chatbot/
├── backend/
│   ├── app.py              # FastAPI backend
│   └── requirements.txt    # Python dependencies
├── frontend/
│   ├── index.html          # Trang HTML chính
│   ├── styles.css          # CSS styles
│   └── app.js              # JavaScript logic
├── start.sh                # Script khởi động
└── README.md               # Hướng dẫn
```

## 🚀 Cách chạy

### Cách 1: Sử dụng script (Khuyến nghị)

```bash
cd web_chatbot
chmod +x start.sh
./start.sh
```

pkill -f "uvicorn" 2>/dev/null; pkill -f "python.*http.server.*3000" 2>/dev/null; sleep 1 && cd /home/ubuntu/Documents/Social-Network-Analysis/chatbot/web_chatbot && ./start.sh

### Cách 2: Chạy thủ công

**Terminal 1 - Backend:**
```bash
cd backend
pip install -r requirements.txt
python app.py
```

**Terminal 2 - Frontend:**
```bash
cd frontend
python -m http.server 3000
```

## 🌐 Truy cập

- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs

## ✨ Tính năng

### Giao diện
- 🎨 Giao diện dark mode hiện đại
- 📱 Responsive design
- 💬 Chat interface trực quan
- 📜 Panel logs bên trái hiển thị quá trình xử lý

### Backend
- ⚡ FastAPI với WebSocket support
- 🔄 Real-time streaming logs
- 🧠 Iterative Graph RAG pipeline
- 🔗 Kết nối Neo4j knowledge graph

### Logs Panel
Hiển thị các bước xử lý:
- 📝 Trích xuất thực thể
- 🔄 Chuẩn hóa thực thể (RapidFuzz)
- 🔗 Truy vấn đồ thị Neo4j
- ⚖️ Đánh giá độ đầy đủ thông tin
- 🤔 Suy luận tìm thêm thực thể (nếu cần)
- ✨ Tạo câu trả lời

## 📡 API Endpoints

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| GET | `/` | Health check |
| GET | `/health` | Trạng thái hệ thống |
| POST | `/chat` | Chat (không streaming) |
| WS | `/ws/chat` | WebSocket chat với streaming logs |

## ⚙️ Cấu hình

Chỉnh sửa trong `backend/app.py`:

```python
NEO4J_URI = "neo4j://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "123456789"
MODEL_ID = "Qwen/Qwen3-0.6B"
MAX_ITERATIONS = 5
```

## 🔧 Yêu cầu hệ thống

- Python 3.10+
- Neo4j Database đang chạy
- GPU (khuyến nghị) cho model LLM
- ~4GB RAM cho model Qwen3-0.6B

## 📝 Ví dụ câu hỏi

- "Ai là đạo diễn phim Titanic?"
- "Brad Pitt có quan hệ gì với Angelina Jolie?"
- "Leonardo DiCaprio đã đóng những phim nào?"
- "Ai là con của Jon Voight?"
