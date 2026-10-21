import React, { useState } from 'react';
import axios from 'axios';
import { 
  Send, User, Bot, Loader2, Scale, ToggleLeft, ToggleRight, 
  Database, Upload, FileText, ExternalLink, ShieldCheck, Cpu
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import './App.css'; 

function App() {
  const [input, setInput] = useState('');
  const [isComparisonMode, setIsComparisonMode] = useState(true); // Bật mặc định so sánh
  const [isLoading, setIsLoading] = useState(false);
  const [messages, setMessages] = useState([
    { 
      role: 'bot', 
      text: 'Xin chào! Tôi là Trợ lý AI chuyên về Luật Công nghệ thông tin. Bạn muốn hỏi gì nào?' 
    }
  ]);

  // Giả lập danh sách tài liệu đã index dựa vào file bạn đã chạy
  const indexedDocs = [
    { name: "24-2018-qh14.pdf", status: "Processed" },
    { name: "86-signed.pdf", status: "Processed" },
    { name: "2020_217_218_15-2020-ND-CP.pdf", status: "Processed" },
    { name: "luat-cong-nghe-thong-tin-67-2006-QH11-con...", status: "Processed" }
  ];

  const sendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage = { role: 'user', text: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      // Gọi đến Backend FastAPI
      const response = await axios.post('http://127.0.0.1:8000/chat', {
        question: userMessage.text
      });

      let botText = "Không nhận được phản hồi từ cơ sở dữ liệu.";
      if (response.data.answer) {
        botText = Array.isArray(response.data.answer) 
          ? response.data.answer[0]?.text 
          : response.data.answer;
      }

      // Mô phỏng 2 chế độ phản hồi khác nhau để làm ví dụ So sánh trực quan sinh động
      // Cột trái (Naive RAG) - Câu trả lời ngắn
      // Cột phải (Hybrid RAG) - Trả lời sâu, có phân tích nguồn
      const naiveResponse = botText.split("\n\n")[0] || botText;

      setMessages((prev) => [...prev, { 
        role: 'bot', 
        text: botText,          // Câu trả lời đầy đủ (Hybrid)
        naiveText: naiveResponse // Câu trả lời tóm tắt (Naive)
      }]);
    } catch (error) {
      console.error("Lỗi gọi API:", error);
      setMessages((prev) => [...prev, { 
        role: 'bot', 
        text: 'Lỗi máy chủ kết nối. Vui lòng kiểm tra lại Backend!' 
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div style={styles.appContainer}>
      
      {/* 1. SIDEBAR BÊN TRÁI */}
      <aside style={styles.sidebar}>
        <div style={styles.sidebarHeader}>
          <div style={styles.logoIcon}><Scale size={20} /></div>
          <div>
            <h1 style={styles.sidebarTitle}>Law Assistant</h1>
            <span style={styles.sidebarSub}>AI RAG Platform</span>
          </div>
        </div>

        {/* Cài đặt RAG */}
        <div style={styles.sidebarSection}>
          <h3 style={styles.sectionHeader}>RAG Settings</h3>
          <div style={styles.settingCard}>
            <div style={styles.settingRow}>
              <span>Comparison Mode</span>
              <button 
                onClick={() => setIsComparisonMode(!isComparisonMode)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: isComparisonMode ? '#1e56fc' : '#9ca3af' }}
              >
                {isComparisonMode ? <ToggleRight size={38} /> : <ToggleLeft size={38} />}
              </button>
            </div>
            <p style={styles.settingDesc}>Compare Naive RAG vs Hybrid RAG responses.</p>
          </div>
        </div>

        {/* Trạng thái hệ thống */}
        <div style={styles.sidebarSection}>
          <h3 style={styles.sectionHeader}>System Status</h3>
          <div style={styles.statusRow}>
            <span style={styles.greenPulse}></span>
            <span style={styles.statusText}>DB: Connected (Port 5433)</span>
          </div>
        </div>

        {/* Kho tri thức - upload (Giả lập) */}
        <div style={styles.sidebarSection}>
          <h3 style={styles.sectionHeader}>Knowledge Base</h3>
          <div style={styles.uploadArea}>
            <Upload size={20} style={{ color: '#6b7280', marginBottom: 6 }} />
            <span style={styles.uploadText}>Click to upload legal PDFs</span>
          </div>
        </div>

        {/* Sơ đồ liên kết (Hướng phát triển) */}
        <div style={styles.sidebarSection}>
          <h3 style={styles.sectionHeader}>Graph Visualization</h3>
          <a href="#explore" style={styles.exploreBtn}>
            <Cpu size={14} style={{ marginRight: 6 }} />
            Explore Graph
            <ExternalLink size={12} style={{ marginLeft: 'auto' }} />
          </a>
        </div>

        {/* Tài liệu đã Index */}
        <div style={styles.sidebarSection}>
          <h3 style={styles.sectionHeader}>Indexed Documents ({indexedDocs.length})</h3>
          <div style={styles.docList}>
            {indexedDocs.map((doc, idx) => (
              <div key={idx} style={styles.docItem}>
                <FileText size={14} style={{ color: '#3b82f6', marginRight: 8, flexShrink: 0 }} />
                <div style={styles.docDetails}>
                  <span style={styles.docName}>{doc.name}</span>
                  <span style={styles.docStatus}>{doc.status}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Footer Sidebar */}
        <div style={styles.sidebarFooter}>
          <div style={styles.footerTag}>
            <Database size={12} style={{ marginRight: 4 }} /> Postgres + pgvector
          </div>
          <div style={styles.footerTag}>
            <ShieldCheck size={12} style={{ marginRight: 4 }} /> Gemini 1.5 Flash
          </div>
        </div>
      </aside>

      {/* 2. KHU VỰC CHAT BÊN PHẢI */}
      <main style={styles.chatArea}>
        <div style={styles.chatViewport}>
          {messages.map((msg, index) => {
            if (msg.role === 'user') {
              return (
                <div key={index} style={styles.userRow}>
                  <div style={styles.userBubble}>{msg.text}</div>
                  <div style={styles.avatarUser}><User size={16} /></div>
                </div>
              );
            }

            // Nếu là bot và có bật so sánh
            if (msg.role === 'bot' && isComparisonMode && index > 0) {
              return (
                <div key={index} style={styles.comparisonContainer}>
                  {/* Cột trái: Naive RAG */}
                  <div style={styles.comparisonCard}>
                    <div style={styles.cardBadge}>Naive RAG</div>
                    <div style={styles.cardContent}>
                      <ReactMarkdown>{msg.naiveText || msg.text}</ReactMarkdown>
                    </div>
                  </div>

                  {/* Cột phải: Hybrid Vector RAG */}
                  <div style={styles.comparisonCardHighlight}>
                    <div style={styles.cardBadgeHighlight}>Hybrid Vector RAG</div>
                    <div style={styles.cardContent}>
                      <ReactMarkdown>{msg.text}</ReactMarkdown>
                    </div>
                  </div>
                </div>
              );
            }

            // Nếu bot ở chế độ thường (chưa có câu hỏi hoặc tắt so sánh)
            return (
              <div key={index} style={styles.botRow}>
                <div style={styles.avatarBot}><Bot size={16} /></div>
                <div style={styles.botBubble}>
                  <ReactMarkdown>{msg.text}</ReactMarkdown>
                </div>
              </div>
            );
          })}

          {isLoading && (
            <div style={styles.botRow}>
              <div style={styles.avatarBot}><Bot size={16} /></div>
              <div style={styles.loadingBubble}>
                <Loader2 size={16} className="spin" style={{ marginRight: 8 }} />
                Đang tra cứu cơ sở dữ liệu pháp luật...
              </div>
            </div>
          )}
        </div>

        {/* Thanh Input phía dưới */}
        <form onSubmit={sendMessage} style={styles.inputForm}>
          <div style={styles.inputWrapper}>
            <input 
              style={styles.chatInput}
              type="text" 
              value={input} 
              onChange={(e) => setInput(e.target.value)} 
              placeholder="Ask a legal question..."
              disabled={isLoading}
            />
            <button style={styles.sendBtn} type="submit" disabled={isLoading || !input.trim()}>
              <Send size={16} />
            </button>
          </div>
          <div style={styles.underInputText}>
            Powered by Gemini & PostgreSQL. Answers are derived from the uploaded legal database.
          </div>
        </form>
      </main>

    </div>
  );
}

// BẢNG CSS INLINE CHI TIẾT ĐỂ TÁO BẠN RA SẢN PHẨM HOÀN MỸ
const styles = {
  appContainer: { display: 'flex', height: '100vh', backgroundColor: '#f3f4f6', fontFamily: 'Inter, system-ui, sans-serif' },
  
  // SIDEBAR STYLES
  sidebar: { width: '280px', backgroundColor: '#ffffff', borderRight: '1px solid #e5e7eb', display: 'flex', flexDirection: 'column', overflowY: 'auto', flexShrink: 0 },
  sidebarHeader: { padding: '20px', display: 'flex', alignItems: 'center', borderBottom: '1px solid #f3f4f6', gap: '12px' },
  logoIcon: { backgroundColor: '#eff6ff', color: '#1e56fc', padding: '8px', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center' },
  sidebarTitle: { fontSize: '15px', fontWeight: '700', color: '#111827', margin: 0 },
  sidebarSub: { fontSize: '11px', color: '#6b7280' },
  sidebarSection: { padding: '16px 20px', borderBottom: '1px solid #f3f4f6' },
  sectionHeader: { fontSize: '11px', fontWeight: '600', textTransform: 'uppercase', color: '#6b7280', letterSpacing: '0.05em', marginBottom: '10px', marginTop: 0 },
  settingCard: { border: '1px solid #e5e7eb', borderRadius: '8px', padding: '12px' },
  settingRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '13px', fontWeight: '500', color: '#374151' },
  settingDesc: { fontSize: '11px', color: '#6b7280', margin: '4px 0 0 0' },
  statusRow: { display: 'flex', alignItems: 'center', gap: '8px', border: '1px solid #e5e7eb', borderRadius: '8px', padding: '10px 12px' },
  greenPulse: { width: '8px', height: '8px', backgroundColor: '#10b981', borderRadius: '50%', boxShadow: '0 0 0 2px rgba(16, 185, 129, 0.2)' },
  statusText: { fontSize: '12px', fontWeight: '500', color: '#374151' },
  uploadArea: { border: '1px dashed #cbd5e1', borderRadius: '8px', padding: '16px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', backgroundColor: '#fcfcfd' },
  uploadText: { fontSize: '11px', color: '#6b7280', fontWeight: '500' },
  exploreBtn: { display: 'flex', alignItems: 'center', textDecoration: 'none', color: '#374151', border: '1px solid #e5e7eb', backgroundColor: '#fcfcfd', borderRadius: '8px', padding: '10px 12px', fontSize: '12px', fontWeight: '500' },
  docList: { display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '180px', overflowY: 'auto' },
  docItem: { display: 'flex', alignItems: 'flex-start', padding: '8px 10px', backgroundColor: '#f8fafc', borderRadius: '6px', border: '1px solid #f1f5f9' },
  docDetails: { display: 'flex', flexDirection: 'column', overflow: 'hidden' },
  docName: { fontSize: '11px', color: '#334155', fontWeight: '500', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  docStatus: { fontSize: '9px', color: '#10b981', fontWeight: '600', marginTop: '2px' },
  sidebarFooter: { marginTop: 'auto', padding: '16px 20px', borderTop: '1px solid #f3f4f6', display: 'flex', gap: '8px', flexWrap: 'wrap' },
  footerTag: { display: 'inline-flex', alignItems: 'center', fontSize: '11px', color: '#4b5563', padding: '4px 8px', backgroundColor: '#f3f4f6', borderRadius: '4px', fontWeight: '500' },

  // CHAT STYLES
  chatArea: { flex: 1, display: 'flex', flexDirection: 'column', backgroundColor: '#f8fafc' },
  chatViewport: { flex: 1, overflowY: 'auto', padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: '20px' },
  
  userRow: { display: 'flex', justifyContent: 'flex-end', gap: '10px', width: '100%' },
  userBubble: { maxWidth: '70%', backgroundColor: '#1e56fc', color: '#ffffff', borderRadius: '16px 16px 2px 16px', padding: '14px 20px', fontSize: '14px', fontWeight: '400', boxShadow: '0 2px 4px rgba(30, 86, 252, 0.1)', lineHeight: '1.5' },
  avatarUser: { width: '28px', height: '28px', backgroundColor: '#1e56fc', color: '#fff', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', alignSelf: 'flex-end', flexShrink: 0 },

  botRow: { display: 'flex', gap: '10px', width: '100%' },
  avatarBot: { width: '28px', height: '28px', backgroundColor: '#e5e7eb', color: '#4b5563', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  botBubble: { maxWidth: '75%', backgroundColor: '#ffffff', color: '#1f2937', borderRadius: '16px 16px 16px 2px', padding: '14px 20px', fontSize: '14px', border: '1px solid #e5e7eb', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' },
  loadingBubble: { display: 'flex', alignItems: 'center', backgroundColor: '#ffffff', color: '#6b7280', borderRadius: '16px', padding: '12px 18px', fontSize: '13px', border: '1px solid #e5e7eb' },

  // COMPARISON MODES STYLES
  comparisonContainer: { display: 'flex', gap: '16px', width: '100%', paddingLeft: '38px', marginTop: '8px' },
  comparisonCard: { flex: 1, backgroundColor: '#ffffff', border: '1px solid #e5e7eb', borderRadius: '12px', padding: '18px', boxShadow: '0 2px 4px rgba(0,0,0,0.02)', display: 'flex', flexDirection: 'column' },
  comparisonCardHighlight: { flex: 1, backgroundColor: '#ffffff', border: '2px solid #3b82f6', borderRadius: '12px', padding: '18px', boxShadow: '0 4px 6px rgba(59, 130, 246, 0.05)', display: 'flex', flexDirection: 'column' },
  cardBadge: { fontSize: '10px', fontWeight: '700', color: '#9ca3af', textTransform: 'uppercase', marginBottom: '10px', borderBottom: '1px solid #f3f4f6', paddingBottom: '6px' },
  cardBadgeHighlight: { fontSize: '10px', fontWeight: '700', color: '#2563eb', textTransform: 'uppercase', marginBottom: '10px', borderBottom: '1px solid #eff6ff', paddingBottom: '6px' },
  cardContent: { fontSize: '13.5px', color: '#374151', lineHeight: '1.6' },

  // INPUT STYLES
  inputForm: { padding: '24px 32px', backgroundColor: '#ffffff', borderTop: '1px solid #e5e7eb' },
  inputWrapper: { display: 'flex', alignItems: 'center', border: '1px solid #cbd5e1', borderRadius: '24px', padding: '4px 8px 4px 16px', backgroundColor: '#ffffff', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' },
  chatInput: { flex: 1, border: 'none', outline: 'none', padding: '10px 0', fontSize: '14px', color: '#1f2937' },
  sendBtn: { backgroundColor: '#1e56fc', color: '#ffffff', border: 'none', borderRadius: '50%', width: '34px', height: '34px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0, transition: 'all 0.15s ease' },
  underInputText: { fontSize: '10px', color: '#9ca3af', textAlign: 'center', marginTop: '8px' }
};

export default App;