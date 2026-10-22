import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import {
  Send, User, Bot, Loader2, Scale, ToggleLeft, ToggleRight,
  ExternalLink, ShieldCheck, Cpu, GitBranch, CheckCircle2,
  AlertTriangle, Layers, ChevronRight, Info, Sparkles,
  BookOpen, Network, RefreshCw, X
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import './App.css';

const API_BASE_URL = 'http://127.0.0.1:8000';

const SAMPLE_QUESTIONS = [
  {
    title: "1. Công ty vs Cá nhân (Phạt x2)",
    text: "Công ty tôi đăng bài sai sự thật về dịch bệnh lên fanpage thì bị phạt bao nhiêu tiền? Nếu là nhân viên tự ý đăng thì mức phạt có khác không?"
  },
  {
    title: "2. Độ tuổi vị thành niên (15 tuổi)",
    text: "Một học sinh 15 tuổi sử dụng tài khoản mạng xã hội để đăng thông tin sai sự thật thì có bị phạt tiền không?"
  },
  {
    title: "3. Tra cứu Điều 101 Nghị định 15",
    text: "Hành vi chia sẻ thông tin giả mạo, vu khống trên mạng xã hội bị xử phạt thế nào theo Điều 101 Nghị định 15/2020?"
  },
  {
    title: "4. Ngoại lệ Điều 106 (Cá nhân gốc)",
    text: "Người chơi game online lợi dụng trò chơi điện tử để thực hiện hành vi vi phạm pháp luật theo Điều 106 Nghị định 15/2020 bị phạt bao nhiêu?"
  },
  {
    title: "5. Chống ảo giác (Nghị định 9999 giả)",
    text: "Theo Nghị định 9999/2025/NĐ-CP thì hành vi bình luận xúc phạm người khác trên Facebook bị phạt bao nhiêu tiền?"
  },
  {
    title: "6. Hành vi nghiêm cấm (Luật An ninh mạng)",
    text: "Theo Điều 8 Luật An ninh mạng 2018, những hành vi nào bị nghiêm cấm trên không gian mạng?"
  }
];

const INITIAL_BOT_MESSAGE = {
  role: 'bot',
  text: `### Xin chào! Tôi là Trợ lý ảo tư vấn Luật Công nghệ thông tin ⚖️\n\nHệ thống ứng dụng kiến trúc **Neuro-Symbolic AI** kết hợp:\n- 🧠 **Khối Neural**: Tìm kiếm ngữ nghĩa vector bằng Google Gemini & PGVector.\n- 🕸️ **Khối Symbolic**: Đồ thị tri thức **Neo4j** & Bộ quy tắc suy luận tất định (Rule Engine) chống ảo giác số liệu.\n\n*Hãy chọn một kịch bản kiểm thử bên trái hoặc đặt câu hỏi pháp lý của bạn!*`,
  symbolicData: null,
};

// ---------------------------------------------------------------------------
// Component vẽ Sơ đồ Mạng lưới Đồ thị Tri thức trực quan bằng SVG
// ---------------------------------------------------------------------------
function KnowledgeGraphCanvas({ nodes = [], edges = [] }) {
  const [selectedNode, setSelectedNode] = useState(null);

  if (!nodes.length) {
    return (
      <div className="card-box" style={{ textAlign: 'center', color: '#64748b', padding: '20px 12px' }}>
        <span>Không có Node đồ thị nào được kích hoạt cho truy vấn này.</span>
      </div>
    );
  }

  const LAYER_ORDER = ['LegalDoc', 'Article', 'Action', 'Penalty', 'Sanction'];
  const LAYER_Y = {
    LegalDoc: 42,
    Article: 122,
    Action: 215,
    Penalty: 310,
    Sanction: 390,
  };

  const TYPE_STYLES = {
    LegalDoc: { bg: '#eff6ff', border: '#2563eb', text: '#1e40af', tag: 'VĂN BẢN' },
    Article:  { bg: '#ecfdf5', border: '#059669', text: '#065f46', tag: 'ĐIỀU LUẬT' },
    Action:   { bg: '#fffbeb', border: '#d97706', text: '#92400e', tag: 'HÀNH VI' },
    Penalty:  { bg: '#fef2f2', border: '#dc2626', text: '#991b1b', tag: 'MỨC PHẠT' },
    Sanction: { bg: '#faf5ff', border: '#9333ea', text: '#6b21a8', tag: 'KHẮC PHỤC' },
  };

  // Phân nhóm các node theo tầng kiến trúc pháp lý
  const grouped = {};
  nodes.forEach((n) => {
    const t = LAYER_ORDER.includes(n.type) ? n.type : 'Action';
    if (!grouped[t]) grouped[t] = [];
    grouped[t].push(n);
  });

  const maxNodesInRow = Math.max(1, ...Object.values(grouped).map((arr) => arr.length));
  const width = Math.max(340, maxNodesInRow * 118);
  const hasSanction = Boolean(grouped.Sanction?.length);
  const height = hasSanction ? 435 : 355;

  const positioned = {};
  Object.entries(grouped).forEach(([type, list]) => {
    const baseY = LAYER_Y[type] || 215;
    const step = width / (list.length + 1);
    list.forEach((node, idx) => {
      // So le nhẹ tọa độ Y nếu cùng 1 hàng có nhiều node để dễ đọc chữ
      const offsetY = list.length > 2 ? (idx % 2 === 0 ? -8 : 8) : 0;
      positioned[node.id] = {
        ...node,
        x: step * (idx + 1),
        y: baseY + offsetY,
      };
    });
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '8px' }}>
      <div
        style={{
          background: '#ffffff',
          border: '1px solid #e2e8f0',
          borderRadius: '10px',
          padding: '8px',
          overflowX: 'auto',
        }}
      >
        <div style={{ fontSize: '10.5px', color: '#64748b', marginBottom: '4px', display: 'flex', justifyContent: 'space-between' }}>
          <span>💡 <i>Bấm vào từng Node trên sơ đồ để xem chi tiết</i></span>
          <span>{nodes.length} đỉnh • {edges.length} cạnh</span>
        </div>

        <svg
          viewBox={`0 0 ${width} ${height}`}
          width="100%"
          height={hasSanction ? 320 : 270}
          style={{ minWidth: `${Math.min(width, 460)}px`, display: 'block' }}
        >
          <defs>
            <marker
              id="graph-arrow"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="5"
              markerHeight="5"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
            </marker>
          </defs>

          {/* Vẽ các cạnh nối (Edges) */}
          {edges.map((e, idx) => {
            const src = positioned[e.source];
            const tgt = positioned[e.target];
            if (!src || !tgt) return null;
            const midX = (src.x + tgt.x) / 2;
            const midY = (src.y + tgt.y) / 2;
            return (
              <g key={`edge-${idx}`}>
                <line
                  x1={src.x}
                  y1={src.y}
                  x2={tgt.x}
                  y2={tgt.y}
                  stroke="#94a3b8"
                  strokeWidth="1.5"
                  strokeDasharray={e.label === 'HAS_SANCTION' ? '3,3' : 'none'}
                  markerEnd="url(#graph-arrow)"
                />
                <rect
                  x={midX - 28}
                  y={midY - 8}
                  width="56"
                  height="11"
                  rx="3"
                  fill="#f8fafc"
                  opacity="0.88"
                />
                <text
                  x={midX}
                  y={midY}
                  fontSize="7"
                  fill="#475569"
                  textAnchor="middle"
                  fontWeight="700"
                >
                  {e.label}
                </text>
              </g>
            );
          })}

          {/* Vẽ các đỉnh (Nodes) */}
          {Object.values(positioned).map((node, idx) => {
            const style = TYPE_STYLES[node.type] || TYPE_STYLES.Action;
            const isSelected = selectedNode?.id === node.id;
            const shortLabel = node.label.length > 20 ? node.label.slice(0, 19) + '…' : node.label;
            return (
              <g
                key={`node-${idx}`}
                transform={`translate(${node.x - 52}, ${node.y - 17})`}
                onClick={() => setSelectedNode(node)}
                style={{ cursor: 'pointer' }}
              >
                <rect
                  width="104"
                  height="34"
                  rx="7"
                  fill={style.bg}
                  stroke={isSelected ? '#0f172a' : style.border}
                  strokeWidth={isSelected ? '2.2' : '1.5'}
                />
                <text
                  x="52"
                  y="12"
                  fontSize="7.2"
                  fontWeight="700"
                  fill={style.border}
                  textAnchor="middle"
                >
                  {style.tag}
                </text>
                <text
                  x="52"
                  y="24"
                  fontSize="8.2"
                  fontWeight="600"
                  fill={style.text}
                  textAnchor="middle"
                >
                  {shortLabel}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Khung chi tiết khi người dùng bấm chọn 1 Node trên sơ đồ */}
      {selectedNode && (
        <div
          className="card-box"
          style={{
            background: '#f8fafc',
            borderLeft: '4px solid #2563eb',
            padding: '10px 12px',
            fontSize: '11.5px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontWeight: 700, color: '#1e40af', textTransform: 'uppercase', fontSize: '10px' }}>
              Chi tiết Node [{selectedNode.type}]
            </span>
            <button
              onClick={() => setSelectedNode(null)}
              style={{ border: 'none', background: 'none', cursor: 'pointer', color: '#64748b' }}
            >
              <X size={13} />
            </button>
          </div>
          <div style={{ fontWeight: 600, color: '#0f172a', marginTop: '2px' }}>
            {selectedNode.data?.full_name || selectedNode.data?.title || selectedNode.label}
          </div>
          {selectedNode.data?.items && (
            <div style={{ color: '#475569', marginTop: '4px', fontSize: '11px' }}>
              • {selectedNode.data.items.join('; ')}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function App() {
  const [input, setInput] = useState('');
  const [isComparisonMode, setIsComparisonMode] = useState(false);
  const [showSymbolicPanel, setShowSymbolicPanel] = useState(true);
  const [activeTab, setActiveTab] = useState('rules'); // 'rules' | 'graph' | 'sources'
  const [isLoading, setIsLoading] = useState(false);
  const [currentSymbolicData, setCurrentSymbolicData] = useState(null);
  const [backendStatus, setBackendStatus] = useState({ neo4j: false, pgvector: false });
  const [messages, setMessages] = useState([INITIAL_BOT_MESSAGE]);

  const chatEndRef = useRef(null);

  const checkBackendHealth = () => {
    axios
      .get(`${API_BASE_URL}/health`)
      .then((res) => {
        setBackendStatus({
          neo4j: Boolean(res.data.neo4j_connected),
          pgvector: Boolean(res.data.pgvector_ready),
        });
      })
      .catch(() => {
        setBackendStatus({ neo4j: false, pgvector: false });
      });
  };

  useEffect(() => {
    checkBackendHealth();
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const sendMessage = async (questionText) => {
    const textToSend = (questionText ?? input).trim();
    if (!textToSend || isLoading) return;

    // Chuẩn bị lịch sử hội thoại (4 lượt gần nhất) gửi lên Backend
    const historyPayload = messages
      .slice(-4)
      .map((m) => ({ role: m.role, text: m.text }));

    const userMessage = { role: 'user', text: textToSend };
    setMessages((prev) => [...prev, userMessage]);
    if (!questionText) setInput('');
    setIsLoading(true);

    try {
      const response = await axios.post(`${API_BASE_URL}/chat`, {
        question: textToSend,
        comparison_mode: isComparisonMode,
        history: historyPayload,
      });

      const { answer, naive_answer, symbolic_reasoning, graph_view, sources } = response.data;

      const botMessage = {
        role: 'bot',
        text: answer,
        naiveText: naive_answer,
        symbolicData: {
          reasoning: symbolic_reasoning,
          graph: graph_view,
          sources: sources,
        },
      };

      setMessages((prev) => [...prev, botMessage]);
      setCurrentSymbolicData(botMessage.symbolicData);
      setShowSymbolicPanel(true);
    } catch (error) {
      console.error('Lỗi gọi API:', error);
      setMessages((prev) => [
        ...prev,
        {
          role: 'bot',
          text: '⚠️ **Lỗi kết nối máy chủ Backend.**\nVui lòng đảm bảo server FastAPI đang chạy tại `http://localhost:8000` và Neo4j đang hoạt động.',
          symbolicData: null,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const resetChat = () => {
    setMessages([INITIAL_BOT_MESSAGE]);
    setCurrentSymbolicData(null);
  };

  const activeSymbolic =
    currentSymbolicData ||
    messages
      .slice()
      .reverse()
      .find((m) => m.symbolicData)?.symbolicData;

  return (
    <div className="app-container">
      {/* 1. SIDEBAR BÊN TRÁI */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="logo-icon">
            <Scale size={22} />
          </div>
          <div>
            <h1 className="sidebar-title">LexIT Assistant</h1>
            <span className="sidebar-sub">Neuro-Symbolic AI Platform</span>
          </div>
        </div>

        {/* Chế độ RAG */}
        <div className="sidebar-section">
          <h3 className="section-header">Chế độ Thử nghiệm</h3>
          <div className="setting-card">
            <div className="setting-row">
              <span className="setting-label">So sánh Đối chứng (A/B)</span>
              <button
                onClick={() => setIsComparisonMode(!isComparisonMode)}
                className="toggle-btn"
                title="Bật/Tắt chế độ so sánh Naive RAG vs Neuro-Symbolic RAG"
              >
                {isComparisonMode ? (
                  <ToggleRight size={34} color="#2563eb" />
                ) : (
                  <ToggleLeft size={34} color="#9ca3af" />
                )}
              </button>
            </div>
            <p className="setting-desc">
              {isComparisonMode
                ? 'Đang hiển thị song song: Naive RAG (dễ bịa số liệu) vs Neuro-Symbolic RAG (chính xác 100%).'
                : 'Chế độ chuẩn: Trợ lý Neuro-Symbolic AI tối ưu độ chính xác pháp lý.'}
            </p>
          </div>
        </div>

        {/* Trạng thái hệ thống */}
        <div className="sidebar-section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
            <h3 className="section-header" style={{ marginBottom: 0 }}>Hạ tầng Đa mô hình</h3>
            <button
              onClick={checkBackendHealth}
              title="Kiểm tra lại kết nối Backend"
              style={{ border: 'none', background: 'none', cursor: 'pointer', color: '#64748b', display: 'flex' }}
            >
              <RefreshCw size={12} />
            </button>
          </div>
          <div className="status-list">
            <div className="status-row">
              <span className={`status-indicator ${backendStatus.neo4j ? 'online' : 'checking'}`}></span>
              <span className="status-label">
                Khối Symbolic: <b>Neo4j 5.26</b>
              </span>
              <a
                href="http://localhost:7474"
                target="_blank"
                rel="noreferrer"
                className="status-link"
                title="Mở Neo4j Browser"
              >
                <ExternalLink size={12} />
              </a>
            </div>
            <div className="status-row">
              <span className={`status-indicator ${backendStatus.pgvector ? 'online' : 'checking'}`}></span>
              <span className="status-label">
                Khối Neural: <b>PostgreSQL + pgvector</b>
              </span>
            </div>
            <div className="status-row">
              <span className="status-indicator online"></span>
              <span className="status-label">
                Mô hình: <b>Gemini + DeepSeek</b>
              </span>
            </div>
          </div>
        </div>

        {/* Câu hỏi kiểm thử đồ án */}
        <div className="sidebar-section">
          <h3 className="section-header">Kịch bản Test Hội đồng</h3>
          <div className="sample-list">
            {SAMPLE_QUESTIONS.map((q, idx) => (
              <button
                key={idx}
                className="sample-item"
                onClick={() => sendMessage(q.text)}
                disabled={isLoading}
              >
                <Sparkles size={13} className="sample-icon" />
                <div className="sample-content">
                  <span className="sample-title">{q.title}</span>
                  <span className="sample-preview">{q.text}</span>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Kho tri thức văn bản */}
        <div className="sidebar-section">
          <h3 className="section-header">Văn bản đã nạp Đồ thị</h3>
          <div className="doc-item">
            <BookOpen size={14} className="doc-icon" />
            <div className="doc-info">
              <span className="doc-name">Nghị định 15/2020/NĐ-CP</span>
              <span className="doc-meta">Xử phạt VPHC CNTT & Viễn thông</span>
            </div>
          </div>
          <div className="doc-item">
            <BookOpen size={14} className="doc-icon" />
            <div className="doc-info">
              <span className="doc-name">Luật An ninh mạng 2018</span>
              <span className="doc-meta">Luật số 24/2018/QH14</span>
            </div>
          </div>
          <div className="doc-item">
            <BookOpen size={14} className="doc-icon" />
            <div className="doc-info">
              <span className="doc-name">Luật Công nghệ thông tin 2006</span>
              <span className="doc-meta">Luật số 67/2006/QH11</span>
            </div>
          </div>
          <div className="doc-item">
            <BookOpen size={14} className="doc-icon" />
            <div className="doc-info">
              <span className="doc-name">Luật Giao dịch điện tử & Dữ liệu</span>
              <span className="doc-meta">20/2023/QH15 • 24/2023/QH15 • 60/2024/QH15</span>
            </div>
          </div>
          <div className="doc-item">
            <BookOpen size={14} className="doc-icon" />
            <div className="doc-info">
              <span className="doc-name">Bộ luật Hình sự 2015 (SĐ 2017)</span>
              <span className="doc-meta">Mục 2 Chương XXI: Tội phạm CNTT</span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="sidebar-footer">
          <span className="footer-badge">Đồ án: Neuro-Symbolic Legal RAG</span>
        </div>
      </aside>

      {/* 2. KHU VỰC CHAT TRUNG TÂM */}
      <main className="chat-main">
        {/* Top Navbar */}
        <header className="chat-header">
          <div className="header-left">
            <h2 className="header-title">Hệ thống Trợ lý ảo tư vấn Luật Công nghệ thông tin</h2>
            <span className="header-tag">Hybrid Neuro-Symbolic Architecture (PGVector + Neo4j + Rule Engine)</span>
          </div>
          <div className="header-right" style={{ display: 'flex', gap: '8px' }}>
            <button
              className="panel-toggle-btn"
              onClick={resetChat}
              title="Làm mới cuộc trò chuyện"
            >
              <RefreshCw size={14} />
              <span>Làm mới</span>
            </button>
            <button
              className={`panel-toggle-btn ${showSymbolicPanel ? 'active' : ''}`}
              onClick={() => setShowSymbolicPanel(!showSymbolicPanel)}
            >
              <Cpu size={16} />
              <span>{showSymbolicPanel ? 'Ẩn Luồng Symbolic' : 'Xem Luồng Symbolic'}</span>
            </button>
          </div>
        </header>

        {/* Danh sách tin nhắn */}
        <div className="chat-viewport">
          {messages.map((msg, index) => {
            if (msg.role === 'user') {
              return (
                <div key={index} className="message-row user-row">
                  <div className="user-bubble">{msg.text}</div>
                  <div className="avatar user-avatar">
                    <User size={16} />
                  </div>
                </div>
              );
            }

            // Tin nhắn của Bot
            return (
              <div key={index} className="bot-turn">
                <div className="message-row bot-row">
                  <div className="avatar bot-avatar">
                    <Bot size={16} />
                  </div>

                  {/* Nếu đang bật chế độ so sánh đối chứng A/B */}
                  {isComparisonMode && msg.naiveText ? (
                    <div className="comparison-container">
                      {/* Cột trái: Naive RAG */}
                      <div className="comparison-card naive-card">
                        <div className="card-header naive-header">
                          <span className="card-badge">CỘT 1: NAIVE RAG (CHỈ DÙNG VECTOR)</span>
                          <span className="warning-chip">Dễ nhầm lẫn số phạt</span>
                        </div>
                        <div className="card-body">
                          <ReactMarkdown>{msg.naiveText}</ReactMarkdown>
                        </div>
                      </div>

                      {/* Cột phải: Neuro-Symbolic RAG */}
                      <div className="comparison-card hybrid-card">
                        <div className="card-header hybrid-header">
                          <span className="card-badge highlight">CỘT 2: NEURO-SYMBOLIC RAG (HYBRID)</span>
                          <span className="success-chip">Chính xác 100% theo Điều 4</span>
                        </div>
                        <div className="card-body">
                          <ReactMarkdown>{msg.text}</ReactMarkdown>
                        </div>
                      </div>
                    </div>
                  ) : (
                    // Chế độ xem chuẩn
                    <div className="bot-bubble">
                      <ReactMarkdown>{msg.text}</ReactMarkdown>
                    </div>
                  )}
                </div>

                {/* Nút xem chi tiết căn cứ suy luận nếu có dữ liệu */}
                {msg.symbolicData && (
                  <div className="reasoning-preview-bar">
                    <button
                      className="preview-btn"
                      onClick={() => {
                        setCurrentSymbolicData(msg.symbolicData);
                        setShowSymbolicPanel(true);
                      }}
                    >
                      <GitBranch size={14} className="preview-icon" />
                      <span>
                        Xem {msg.symbolicData.reasoning?.rule_steps?.length || 0} bước suy luận tất định &{' '}
                        {msg.symbolicData.graph?.nodes?.length || 0} Nodes đồ thị tri thức
                      </span>
                      <ChevronRight size={14} />
                    </button>
                  </div>
                )}
              </div>
            );
          })}

          {isLoading && (
            <div className="message-row bot-row">
              <div className="avatar bot-avatar">
                <Bot size={16} />
              </div>
              <div className="loading-card">
                <Loader2 size={18} className="spin-icon" />
                <div className="loading-text">
                  <span>Đang thực hiện truy vấn kép Neuro-Symbolic:</span>
                  <small>Vector Search (Neural) + Tra cứu Đồ thị 4 tầng & Rule Engine (Symbolic)...</small>
                </div>
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Thanh nhập câu hỏi */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            sendMessage();
          }}
          className="chat-form"
        >
          <div className="input-box">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Hỏi về quy định pháp luật, mức xử phạt, trách nhiệm pháp lý CNTT..."
              disabled={isLoading}
              className="main-input"
            />
            <button
              type="submit"
              disabled={isLoading || !input.trim()}
              className="send-button"
              title="Gửi câu hỏi"
            >
              {isLoading ? <Loader2 size={16} className="spin-icon" /> : <Send size={16} />}
            </button>
          </div>
          <div className="input-disclaimer">
            <span>
              🛡️ Khối Symbolic áp dụng quy định Điều 4 Khoản 3 Nghị định 15/2020/NĐ-CP (Tổ chức phạt gấp đôi Cá nhân, trừ Điều 106).
            </span>
          </div>
        </form>
      </main>

      {/* 3. KHUNG LUỒNG SUY LUẬN SYMBOLIC (EXPLAINABLE AI SIDECAR) */}
      {showSymbolicPanel && (
        <aside className="symbolic-panel">
          <div className="panel-header">
            <div className="panel-title-group">
              <Cpu size={18} className="panel-header-icon" />
              <div>
                <h3 className="panel-title">Luồng suy luận Symbolic</h3>
                <span className="panel-sub">Explainable Legal Intelligence (XAI)</span>
              </div>
            </div>
            <button className="panel-close-btn" onClick={() => setShowSymbolicPanel(false)}>
              <X size={16} />
            </button>
          </div>

          {/* Navigation Tabs */}
          <div className="panel-tabs">
            <button
              className={`panel-tab ${activeTab === 'rules' ? 'active' : ''}`}
              onClick={() => setActiveTab('rules')}
            >
              <GitBranch size={14} />
              <span>Dấu vết Logic</span>
            </button>
            <button
              className={`panel-tab ${activeTab === 'graph' ? 'active' : ''}`}
              onClick={() => setActiveTab('graph')}
            >
              <Network size={14} />
              <span>Đồ thị Tri thức</span>
            </button>
            <button
              className={`panel-tab ${activeTab === 'sources' ? 'active' : ''}`}
              onClick={() => setActiveTab('sources')}
            >
              <BookOpen size={14} />
              <span>Trích dẫn Luật</span>
            </button>
          </div>

          <div className="panel-content">
            {!activeSymbolic ? (
              <div className="empty-state">
                <Info size={32} className="empty-icon" />
                <p>Chưa có dữ liệu suy luận cho câu hỏi hiện tại.</p>
                <small>Hãy đặt câu hỏi để quan sát luồng suy luận tự động của hệ thống.</small>
              </div>
            ) : (
              <>
                {/* TAB 1: DẤU VẾT LOGIC & TÍNH TOÁN KHUNG PHẠT */}
                {activeTab === 'rules' && (
                  <div className="rules-view" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                    {/* Các thực thể phát hiện */}
                    <div className="card-box">
                      <div className="card-box-title">
                        <CheckCircle2 size={14} className="icon-success" />
                        <span>Thực thể phát hiện (Query Facts)</span>
                      </div>
                      <div className="facts-grid">
                        <div className="fact-item">
                          <span className="fact-label">Chủ thể nhận diện:</span>
                          <span className="fact-value">
                            {activeSymbolic.reasoning?.facts?.subjects
                              ?.map((s) => (s === 'ORGANIZATION' ? 'Tổ chức' : 'Cá nhân'))
                              .join(', ') || 'Chung'}
                          </span>
                        </div>
                        {activeSymbolic.reasoning?.facts?.age && (
                          <div className="fact-item">
                            <span className="fact-label">Độ tuổi phát hiện:</span>
                            <span className="fact-value highlight-age">
                              {activeSymbolic.reasoning?.facts?.age} tuổi
                            </span>
                          </div>
                        )}
                        {activeSymbolic.reasoning?.facts?.article_refs?.length > 0 && (
                          <div className="fact-item">
                            <span className="fact-label">Số Điều truy vấn:</span>
                            <span className="fact-value">
                              Điều {activeSymbolic.reasoning?.facts?.article_refs.join(', ')}
                            </span>
                          </div>
                        )}
                        {activeSymbolic.reasoning?.facts?.invalid_docs?.length > 0 && (
                          <div className="fact-item">
                            <span className="fact-label">Cảnh báo văn bản:</span>
                            <span className="fact-value" style={{ color: '#dc2626' }}>
                              {activeSymbolic.reasoning.facts.invalid_docs.join(', ')} (Không tồn tại)
                            </span>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Bảng kết quả tính toán khung phạt theo luật */}
                    {activeSymbolic.reasoning?.penalty_calculations?.length > 0 && (
                      <div className="card-box">
                        <div className="card-box-title">
                          <Scale size={14} className="icon-primary" />
                          <span>Mức phạt & Chế tài tính toán tất định</span>
                        </div>
                        <div className="calcs-list">
                          {activeSymbolic.reasoning.penalty_calculations.map((calc, i) => (
                            <div key={i} className="calc-card">
                              <div className="calc-action-title">{calc.action}</div>
                              <div className="calc-basis-tag">
                                {calc.clause}, {calc.article}
                              </div>
                              <div className="calc-results-list">
                                {calc.calculations.map((c, j) => (
                                  <div key={j} className="calc-result-row">
                                    <span className="result-subject">{c.subject_label}:</span>
                                    <span className="result-amount">{c.display}</span>
                                    <span className="result-formula">({c.formula})</span>
                                  </div>
                                ))}
                              </div>

                              {/* Hiển thị Hình thức phạt bổ sung / Biện pháp khắc phục hậu quả */}
                              {calc.sanctions?.length > 0 && (
                                <div
                                  style={{
                                    marginTop: '8px',
                                    paddingTop: '6px',
                                    borderTop: '1px dashed #e2e8f0',
                                    fontSize: '11px',
                                    color: '#6b21a8',
                                  }}
                                >
                                  <b>🛠️ Biện pháp bổ sung / Khắc phục:</b>
                                  <ul style={{ paddingLeft: '16px', margin: '3px 0 0 0' }}>
                                    {calc.sanctions.map((s, idx) => (
                                      <li key={idx}>{s}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}

                              {/* Hiển thị Điều khoản liên đới tham chiếu */}
                              {calc.ref_articles?.length > 0 && (
                                <div style={{ marginTop: '4px', fontSize: '10.5px', color: '#475569' }}>
                                  🔗 <b>Điều liên đới:</b> Điều {calc.ref_articles.join(', ')}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Nếu câu hỏi rơi vào Luật An ninh mạng / Luật CNTT (Quy phạm cấm/nghĩa vụ không có tiền phạt) */}
                    {(!activeSymbolic.reasoning?.penalty_calculations ||
                      activeSymbolic.reasoning.penalty_calculations.length === 0) &&
                      activeSymbolic.reasoning?.matched_actions?.length > 0 && (
                        <div className="card-box">
                          <div className="card-box-title">
                            <ShieldCheck size={14} className="icon-primary" />
                            <span>Quy phạm pháp luật phát hiện trên Đồ thị</span>
                          </div>
                          <div className="calcs-list">
                            {activeSymbolic.reasoning.matched_actions.map((act, i) => (
                              <div key={i} className="calc-card">
                                <div className="calc-action-title">{act.action_name}</div>
                                <div className="calc-basis-tag">
                                  Điều {act.article_number} ({act.doc_title})
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                    {/* Dấu vết từng bước suy luận (Rule Steps) */}
                    <div className="card-box">
                      <div className="card-box-title">
                        <GitBranch size={14} className="icon-purple" />
                        <span>Quy trình suy luận logic (Rule Trace)</span>
                      </div>
                      <div className="steps-timeline">
                        {activeSymbolic.reasoning?.rule_steps?.length > 0 ? (
                          activeSymbolic.reasoning.rule_steps.map((step, idx) => (
                            <div key={idx} className="timeline-item">
                              <div className="timeline-badge">{idx + 1}</div>
                              <div className="timeline-body">
                                <div className="timeline-rule-tag">[{step.rule}]</div>
                                <div className="timeline-text">{step.detail}</div>
                                <div className="timeline-basis">
                                  Căn cứ: <b>{step.basis}</b>
                                </div>
                              </div>
                            </div>
                          ))
                        ) : (
                          <div style={{ fontSize: '11.5px', color: '#64748b' }}>
                            Truy vấn không kích hoạt quy tắc quy đổi tiền phạt hành chính.
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {/* TAB 2: ĐỒ THỊ TRI THỨC (INTERACTIVE SVG GRAPH + NODES & EDGES) */}
                {activeTab === 'graph' && (
                  <div className="graph-view">
                    <div className="graph-banner">
                      <span>Đã kích hoạt {activeSymbolic.graph?.nodes?.length || 0} Nodes trên Neo4j</span>
                      <a href="http://localhost:7474" target="_blank" rel="noreferrer" className="neo4j-btn">
                        <span>Mở Neo4j Browser</span>
                        <ExternalLink size={12} />
                      </a>
                    </div>

                    {/* Sơ đồ mạng lưới trực quan bằng SVG */}
                    <KnowledgeGraphCanvas
                      nodes={activeSymbolic.graph?.nodes || []}
                      edges={activeSymbolic.graph?.edges || []}
                    />

                    <div className="nodes-container">
                      {activeSymbolic.graph?.nodes?.map((node, i) => (
                        <div key={i} className={`graph-node-card type-${node.type?.toLowerCase()}`}>
                          <div className="node-type-badge">{node.type}</div>
                          <div className="node-label-text">{node.label}</div>
                        </div>
                      ))}
                    </div>

                    <div className="edges-section">
                      <h4 className="edges-title">Mối quan hệ liên đới (Relationships):</h4>
                      <div className="edges-list">
                        {activeSymbolic.graph?.edges?.map((edge, i) => (
                          <div key={i} className="edge-item">
                            <span className="edge-node">{edge.source}</span>
                            <span className="edge-rel">--[{edge.label}]--&gt;</span>
                            <span className="edge-node">{edge.target}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* TAB 3: TRÍCH DẪN VĂN BẢN GỐC (NEURAL SOURCES) */}
                {activeTab === 'sources' && (
                  <div className="sources-view">
                    <div className="sources-list">
                      {activeSymbolic.sources?.length > 0 ? (
                        activeSymbolic.sources.map((src, i) => (
                          <div key={i} className="source-card">
                            <div className="source-header">
                              <span className="source-title">{src.title}</span>
                              <span className="source-page">Trang {src.page}</span>
                            </div>
                            <div className="source-article">{src.article}</div>
                            <p className="source-snippet">{src.snippet}</p>
                          </div>
                        ))
                      ) : (
                        <div className="card-box" style={{ textAlign: 'center', color: '#64748b' }}>
                          Không có đoạn trích Vector nào được sử dụng (Đã chặn bởi Symbolic Guardrail).
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </aside>
      )}
    </div>
  );
}

export default App;