// ===== CONFIGURATION =====
const WS_URL = 'ws://localhost:8000/ws/chat';
const API_URL = 'http://localhost:8000';

// ===== STATE =====
let websocket = null;
let isConnected = false;
let isProcessing = false;

// ===== DOM ELEMENTS =====
const messagesContainer = document.getElementById('messagesContainer');
const logsContainer = document.getElementById('logsContainer');
const questionInput = document.getElementById('questionInput');
const sendBtn = document.getElementById('sendBtn');
const connectionStatus = document.getElementById('connectionStatus');

// ===== WEBSOCKET CONNECTION =====
function connectWebSocket() {
    updateConnectionStatus('connecting');
    
    websocket = new WebSocket(WS_URL);
    
    websocket.onopen = () => {
        isConnected = true;
        updateConnectionStatus('connected');
        console.log('WebSocket connected');
    };
    
    websocket.onclose = () => {
        isConnected = false;
        updateConnectionStatus('disconnected');
        console.log('WebSocket disconnected');
        
        // Auto reconnect after 3 seconds
        setTimeout(connectWebSocket, 3000);
    };
    
    websocket.onerror = (error) => {
        console.error('WebSocket error:', error);
        updateConnectionStatus('error');
    };
    
    websocket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
    };
}

function updateConnectionStatus(status) {
    const statusDot = connectionStatus.querySelector('.status-dot');
    const statusText = connectionStatus.querySelector('.status-text');
    
    statusDot.className = 'status-dot';
    
    switch (status) {
        case 'connected':
            statusDot.classList.add('connected');
            statusText.textContent = 'Đã kết nối';
            break;
        case 'disconnected':
            statusDot.classList.add('disconnected');
            statusText.textContent = 'Mất kết nối';
            break;
        case 'connecting':
            statusText.textContent = 'Đang kết nối...';
            break;
        case 'error':
            statusDot.classList.add('disconnected');
            statusText.textContent = 'Lỗi kết nối';
            break;
    }
}

// ===== MESSAGE HANDLING =====
function handleWebSocketMessage(data) {
    switch (data.event) {
        case 'start':
            // Xử lý bắt đầu - xóa logs cũ
            clearLogs();
            addLogEntry({type: 'info', message: '🚀 Bắt đầu xử lý câu hỏi...'});
            break;
            
        case 'log':
            // Thêm log entry real-time
            addLogEntry(data.data);
            break;
            
        case 'complete':
            // Hoàn thành - hiển thị câu trả lời
            removeTypingIndicator();
            
            // Hiển thị tất cả logs nếu chưa có (fallback)
            const currentLogs = logsContainer.querySelectorAll('.log-entry').length;
            if (data.data.logs && data.data.logs.length > currentLogs) {
                clearLogs();
                data.data.logs.forEach(log => addLogEntry(log));
            }
            
            addBotMessage(data.data.answer);
            setProcessing(false);
            break;
            
        case 'error':
            // Lỗi
            removeTypingIndicator();
            addLogEntry({type: 'error', message: '❌ Lỗi: ' + data.data});
            addBotMessage('❌ Đã xảy ra lỗi: ' + data.data);
            setProcessing(false);
            break;
    }
}

// ===== LOGS =====
function addLogEntry(log) {
    // Remove placeholder if exists
    const placeholder = logsContainer.querySelector('.log-placeholder');
    if (placeholder) {
        placeholder.remove();
    }
    
    const logElement = document.createElement('div');
    logElement.className = `log-entry ${log.type}`;
    logElement.textContent = log.message;
    
    logsContainer.appendChild(logElement);
    logsContainer.scrollTop = logsContainer.scrollHeight;
}

function clearLogs() {
    logsContainer.innerHTML = `
        <div class="log-placeholder">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="16" x2="12" y2="12"></line>
                <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
            <p>Logs sẽ hiển thị ở đây khi bạn gửi câu hỏi</p>
        </div>
    `;
}

// ===== MESSAGES =====
function addUserMessage(text) {
    // Remove welcome message if exists
    const welcome = messagesContainer.querySelector('.welcome-message');
    if (welcome) {
        welcome.remove();
    }
    
    const messageHTML = `
        <div class="message user">
            <div class="message-avatar">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                    <circle cx="12" cy="7" r="4"></circle>
                </svg>
            </div>
            <div class="message-content">${escapeHtml(text)}</div>
        </div>
    `;
    
    messagesContainer.insertAdjacentHTML('beforeend', messageHTML);
    scrollToBottom();
}

function addBotMessage(text) {
    // Format text (simple markdown-like)
    const formattedText = formatMessage(text);
    
    const messageHTML = `
        <div class="message bot">
            <div class="message-avatar">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="3"></circle>
                    <path d="M12 1v4m0 14v4m-9-9h4m14 0h4"></path>
                </svg>
            </div>
            <div class="message-content">${formattedText}</div>
        </div>
    `;
    
    messagesContainer.insertAdjacentHTML('beforeend', messageHTML);
    scrollToBottom();
}

function addTypingIndicator() {
    const indicatorHTML = `
        <div class="message bot typing-message">
            <div class="message-avatar">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="3"></circle>
                    <path d="M12 1v4m0 14v4m-9-9h4m14 0h4"></path>
                </svg>
            </div>
            <div class="message-content">
                <div class="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        </div>
    `;
    
    messagesContainer.insertAdjacentHTML('beforeend', indicatorHTML);
    scrollToBottom();
}

function removeTypingIndicator() {
    const typingMsg = messagesContainer.querySelector('.typing-message');
    if (typingMsg) {
        typingMsg.remove();
    }
}

// ===== SEND QUESTION =====
function sendQuestion() {
    const question = questionInput.value.trim();
    
    if (!question || isProcessing) return;
    
    if (!isConnected) {
        alert('Chưa kết nối đến server. Vui lòng đợi...');
        return;
    }
    
    // Add user message
    addUserMessage(question);
    
    // Clear input
    questionInput.value = '';
    autoResize(questionInput);
    
    // Set processing state
    setProcessing(true);
    
    // Add typing indicator
    addTypingIndicator();
    
    // Clear logs and send question
    clearLogs();
    
    websocket.send(JSON.stringify({ question: question }));
}

function setProcessing(processing) {
    isProcessing = processing;
    sendBtn.disabled = processing;
    questionInput.disabled = processing;
}

// ===== UTILITIES =====
function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatMessage(text) {
    // Simple formatting
    let formatted = escapeHtml(text);
    
    // Bold: **text**
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // Line breaks
    formatted = formatted.replace(/\n/g, '<br>');
    
    // Wrap in paragraph
    const paragraphs = formatted.split('<br><br>');
    return paragraphs.map(p => `<p>${p}</p>`).join('');
}

function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendQuestion();
    }
}

function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
}

function askExample(button) {
    const question = button.textContent;
    questionInput.value = question;
    autoResize(questionInput);
    sendQuestion();
}

// ===== INITIALIZATION =====
document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    
    // Focus input
    questionInput.focus();
});
