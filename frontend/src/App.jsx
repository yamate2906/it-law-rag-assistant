import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import axios from 'axios';
import {
  Send, Loader2, Scale, ToggleLeft, ToggleRight,
  ExternalLink, ShieldCheck, Cpu, GitBranch, CheckCircle2,
  ChevronRight, Info, Sparkles,
  BookOpen, Network, RefreshCw, X, Plus, MessageSquare,
  Trash2, PanelLeftClose, PanelLeftOpen, Maximize2, Minimize2,
  Copy, Check, RotateCcw, ZoomIn, ZoomOut, Play, Pause, Search,
  Database, Terminal, Layers, Sun, Moon, Paperclip, FileText,
  BarChart3, Sliders, AlertTriangle, Printer
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import './App.css';

const API_BASE_URL = 'http://127.0.0.1:8000';

const SAMPLE_QUESTIONS = [
  {
    title: 'Công ty vs Cá nhân (Phạt x2)',
    tag: 'Điều 4 & Điều 101 NĐ 15/2020',
    text: 'Công ty tôi đăng bài sai sự thật về dịch bệnh lên fanpage thì bị phạt bao nhiêu tiền? Nếu là nhân viên tự ý đăng thì mức phạt có khác không?'
  },
  {
    title: 'Độ tuổi vị thành niên (15 tuổi)',
    tag: 'Luật XLVPHC & NĐ 15/2020',
    text: 'Một học sinh 15 tuổi sử dụng tài khoản mạng xã hội để đăng thông tin sai sự thật thì có bị phạt tiền không?'
  },
  {
    title: 'Bảo vệ dữ liệu cá nhân',
    tag: 'Nghị định 13/2023 & Luật 91/2025',
    text: 'Theo Nghị định 13/2023/NĐ-CP và Luật Bảo vệ dữ liệu cá nhân, quyền của chủ thể dữ liệu và nghĩa vụ khi xử lý dữ liệu cá nhân nhạy cảm là gì?'
  },
  {
    title: 'Ngoại lệ Điều 106 (Người chơi game)',
    tag: 'Điều 106 NĐ 15/2020',
    text: 'Người chơi game online lợi dụng trò chơi điện tử để thực hiện hành vi vi phạm pháp luật theo Điều 106 Nghị định 15/2020 bị phạt bao nhiêu?'
  },
  {
    title: 'Chống ảo giác (Nghị định 9999 giả)',
    tag: 'Symbolic Guardrail',
    text: 'Theo Nghị định 9999/2025/NĐ-CP thì hành vi bình luận xúc phạm người khác trên Facebook bị phạt bao nhiêu tiền?'
  },
  {
    title: 'An ninh mạng & Hành vi nghiêm cấm',
    tag: 'Điều 8 Luật An ninh mạng 2018',
    text: 'Theo Điều 8 Luật An ninh mạng 2018, những hành vi nào bị nghiêm cấm trên không gian mạng?'
  }
];

// Bảng màu Ngôi sao phát quang (Cosmic Starlight Bloom) chuẩn giao diện Neo4j.com (Hình 2)
const NODE_PALETTE = {
  LegalDoc: {
    core: '#ffffff',
    inner: '#ecfdf5',
    halo: 'rgba(110, 231, 183, 0.85)',
    outer: 'rgba(16, 185, 129, 0)',
    bg: '#ecfdf5',
    text: '#047857',
    tag: 'VĂN BẢN LUẬT',
    radius: 6.8,
    glowScale: 4.8,
  },
  Article: {
    core: '#ffffff',
    inner: '#fef3c7',
    halo: 'rgba(251, 191, 36, 0.85)',
    outer: 'rgba(245, 158, 11, 0)',
    bg: '#fffbeb',
    text: '#b45309',
    tag: 'ĐIỀU LUẬT',
    radius: 5.0,
    glowScale: 4.0,
  },
  Clause: {
    core: '#ffffff',
    inner: '#e0f2fe',
    halo: 'rgba(125, 211, 252, 0.78)',
    outer: 'rgba(56, 189, 248, 0)',
    bg: '#f0f9ff',
    text: '#0369a1',
    tag: 'KHOẢN',
    radius: 3.8,
    glowScale: 3.4,
  },
  Action: {
    core: '#ffffff',
    inner: '#ffedd5',
    halo: 'rgba(251, 146, 60, 0.88)',
    outer: 'rgba(234, 88, 12, 0)',
    bg: '#fff7ed',
    text: '#c2410c',
    tag: 'HÀNH VI / QUY PHẠM',
    radius: 4.6,
    glowScale: 3.9,
  },
  Penalty: {
    core: '#ffffff',
    inner: '#fde68a',
    halo: 'rgba(245, 158, 11, 0.92)',
    outer: 'rgba(217, 119, 6, 0)',
    bg: '#fef2f2',
    text: '#b91c1c',
    tag: 'MỨC PHẠT TIỀN',
    radius: 5.2,
    glowScale: 4.2,
  },
  Sanction: {
    core: '#ffffff',
    inner: '#e0e7ff',
    halo: 'rgba(147, 197, 253, 0.82)',
    outer: 'rgba(59, 130, 246, 0)',
    bg: '#faf5ff',
    text: '#6d28d9',
    tag: 'BIỆN PHÁP KHẮC PHỤC',
    radius: 4.2,
    glowScale: 3.6,
  },
};

// ============================================================================
// COMPONENT: ĐỒ THỊ TRI THỨC NEO4J 3D (PHONG CÁCH NEO4J COSMIC CONSTELLATION HÌNH 2)
// ============================================================================
function KnowledgeGraph3D({
  nodes = [],
  edges = [],
  graphMode,
  setGraphMode,
  hasQueryGraph,
  overviewDocs = [],
  selectedDocCode,
  onSelectDocCode,
  neo4jStats,
  onOpenGuide,
  isFullscreen,
  onToggleFullscreen,
  isLoadingGraph,
}) {
  const canvasRef = useRef(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [hoveredNode, setHoveredNode] = useState(null);
  const [autoRotate, setAutoRotate] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  // Góc xoay Camera 3D & Zoom
  const cameraRef = useRef({
    rotX: 0.22,
    rotY: 0.55,
    zoom: 1.05,
    panX: 0,
    panY: 0,
    isDragging: false,
    dragStartX: 0,
    dragStartY: 0,
    moved: false,
  });

  // Tạo bầu trời sao hậu cảnh (Starfield Particles) cố định
  const bgStars = useMemo(() => {
    const stars = [];
    for (let i = 0; i < 85; i++) {
      const seed = (i * 9301 + 49297) % 233280;
      const rnd1 = seed / 233280;
      const rnd2 = ((seed * 7 + 13) % 233280) / 233280;
      const rnd3 = ((seed * 31 + 97) % 233280) / 233280;
      stars.push({
        u: rnd1,
        v: rnd2,
        r: 0.5 + rnd3 * 1.35,
        alpha: 0.18 + rnd3 * 0.55,
        warm: i % 3 === 0,
        phase: rnd3 * Math.PI * 2,
      });
    }
    return stars;
  }, []);

  // Khởi tạo tọa độ mặt cầu 3D (x, y, z) & lưới đa giác chòm sao giống Hình 2
  const simData = useMemo(() => {
    if (!nodes.length) return { nodes3d: [], edges3d: [], meshEdges: [] };

    const q = searchTerm.trim().toLowerCase();
    const filteredNodes = q
      ? nodes.filter(
          (n) =>
            n.label?.toLowerCase().includes(q) ||
            n.data?.title?.toLowerCase().includes(q) ||
            n.data?.full_name?.toLowerCase().includes(q) ||
            n.data?.code?.toLowerCase().includes(q)
        )
      : nodes;

    const validSet = new Set(filteredNodes.map((n) => n.id));
    const activeNodes = filteredNodes.length > 0 ? filteredNodes : nodes;
    const activeSet = filteredNodes.length > 0 ? validSet : new Set(nodes.map((n) => n.id));

    // Phân bố các đỉnh trên khối cầu đa lớp 3D để tạo hình cầu chòm sao chuẩn Hình 2
    const total = Math.max(activeNodes.length, 1);
    const nodes3d = activeNodes.map((n, idx) => {
      const baseR =
        n.type === 'LegalDoc'
          ? 145
          : n.type === 'Article'
          ? 172
          : n.type === 'Penalty'
          ? 192
          : 182;
      // Golden Fibonacci Sphere + độ nhiễu tự nhiên
      const phi = Math.acos(1 - (2 * (idx + 0.5)) / total);
      const theta = Math.PI * (1 + Math.sqrt(5)) * idx;
      const jitter = 0.88 + ((idx * 37) % 25) * 0.01;
      const r = baseR * jitter;
      return {
        ...n,
        x: r * Math.sin(phi) * Math.cos(theta),
        y: r * Math.cos(phi) * 0.92,
        z: r * Math.sin(phi) * Math.sin(theta),
        phase: (idx * 0.73) % (Math.PI * 2),
      };
    });

    const byId = new Map(nodes3d.map((n) => [n.id, n]));
    const edges3d = edges.filter((e) => activeSet.has(e.source) && activeSet.has(e.target));

    // Chạy 65 bước cân bằng lực 3D trên mặt cầu để các cụm Luật gom tự nhiên mà vẫn giữ khối cầu 3D
    for (let iter = 0; iter < 65; iter++) {
      for (let i = 0; i < nodes3d.length; i++) {
        for (let j = i + 1; j < nodes3d.length; j++) {
          const a = nodes3d[i];
          const b = nodes3d[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const dz = a.z - b.z;
          const distSq = dx * dx + dy * dy + dz * dz + 140;
          const force = 1900 / distSq;
          const dist = Math.sqrt(distSq);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          const fz = (dz / dist) * force;
          a.x += fx;
          a.y += fy;
          a.z += fz;
          b.x -= fx;
          b.y -= fy;
          b.z -= fz;
        }
      }
      for (const e of edges3d) {
        const s = byId.get(e.source);
        const t = byId.get(e.target);
        if (!s || !t) continue;
        const targetLen = 58;
        const dx = t.x - s.x;
        const dy = t.y - s.y;
        const dz = t.z - s.z;
        const dist = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
        const delta = (dist - targetLen) * 0.065;
        const fx = (dx / dist) * delta;
        const fy = (dy / dist) * delta;
        const fz = (dz / dist) * delta;
        s.x += fx;
        s.y += fy;
        s.z += fz;
        t.x -= fx;
        t.y -= fy;
        t.z -= fz;
      }
      // Giữ các đỉnh nằm trên lớp vỏ cầu 3D giống Hình 2
      for (const n of nodes3d) {
        const curR = Math.sqrt(n.x * n.x + n.y * n.y + n.z * n.z) || 1;
        const desiredR = n.type === 'LegalDoc' ? 140 : 185;
        const pull = (desiredR - curR) * 0.08;
        n.x += (n.x / curR) * pull;
        n.y += (n.y / curR) * pull;
        n.z += (n.z / curR) * pull;
      }
    }

    // Tạo thêm mạng lưới sợi đa giác chòm sao (Constellation Geodesic Mesh) nối mỗi đỉnh với 3 đỉnh lân cận nhất
    // để tạo đúng hiệu ứng mạng lưới dây thần kinh đa giác 3D như Hình 2!
    const meshSet = new Set(edges3d.map((e) => `${e.source}|${e.target}`));
    const meshEdges = [];
    for (let i = 0; i < nodes3d.length; i++) {
      const a = nodes3d[i];
      const dists = [];
      for (let j = 0; j < nodes3d.length; j++) {
        if (i === j) continue;
        const b = nodes3d[j];
        const d2 = (a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2;
        dists.push({ id: b.id, d2, warm: a.type === 'Article' || b.type === 'Penalty' });
      }
      dists.sort((p, qItem) => p.d2 - qItem.d2);
      for (const nb of dists.slice(0, 3)) {
        const k1 = `${a.id}|${nb.id}`;
        const k2 = `${nb.id}|${a.id}`;
        if (!meshSet.has(k1) && !meshSet.has(k2)) {
          meshSet.add(k1);
          meshEdges.push({ source: a.id, target: nb.id, warm: nb.warm });
        }
      }
    }

    return { nodes3d, edges3d, meshEdges };
  }, [nodes, edges, searchTerm]);

  // Vòng lặp dựng hình 3D 60fps với hiệu ứng Additive Light Bloom chuẩn Hình 2
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let animId;
    let timeTick = 0;

    const render = () => {
      timeTick += 0.02;
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      if (
        canvas.width !== Math.floor(rect.width * dpr) ||
        canvas.height !== Math.floor(rect.height * dpr)
      ) {
        canvas.width = Math.floor(rect.width * dpr);
        canvas.height = Math.floor(rect.height * dpr);
      }

      ctx.save();
      ctx.scale(dpr, dpr);
      const W = rect.width;
      const H = rect.height;

      // 1. Nền Vũ trụ Đêm Sâu (Deep Space Cosmic Background chuẩn Hình 2)
      ctx.fillStyle = '#03060c';
      ctx.fillRect(0, 0, W, H);

      // Quầng sáng Nebula Xanh Ngọc Lục Bảo & Lam Băng ở vùng trung tâm lệch phải trên (giống hệt Hình 2)
      const nebula1 = ctx.createRadialGradient(
        W * 0.62,
        H * 0.32,
        5,
        W * 0.62,
        H * 0.32,
        Math.max(W, H) * 0.55
      );
      nebula1.addColorStop(0, 'rgba(52, 211, 153, 0.22)');
      nebula1.addColorStop(0.35, 'rgba(14, 165, 233, 0.12)');
      nebula1.addColorStop(0.7, 'rgba(15, 23, 42, 0.04)');
      nebula1.addColorStop(1, 'rgba(3, 6, 12, 0)');
      ctx.fillStyle = nebula1;
      ctx.fillRect(0, 0, W, H);

      // Quầng sáng ấm Vàng Hổ Phách nhẹ ở phần dưới khối cầu
      const nebula2 = ctx.createRadialGradient(
        W * 0.45,
        H * 0.62,
        10,
        W * 0.45,
        H * 0.62,
        Math.max(W, H) * 0.5
      );
      nebula2.addColorStop(0, 'rgba(245, 158, 11, 0.10)');
      nebula2.addColorStop(0.5, 'rgba(30, 58, 138, 0.07)');
      nebula2.addColorStop(1, 'rgba(3, 6, 12, 0)');
      ctx.fillStyle = nebula2;
      ctx.fillRect(0, 0, W, H);

      // Vẽ các hạt sao lấp lánh ở hậu cảnh xa
      for (const st of bgStars) {
        const twinkle = 0.65 + 0.35 * Math.sin(timeTick * 1.4 + st.phase);
        ctx.fillStyle = st.warm
          ? `rgba(253, 224, 71, ${st.alpha * twinkle})`
          : `rgba(224, 242, 254, ${st.alpha * twinkle})`;
        ctx.beginPath();
        ctx.arc(st.u * W, st.v * H, st.r, 0, Math.PI * 2);
        ctx.fill();
      }

      const cam = cameraRef.current;
      if (autoRotate && !cam.isDragging && !hoveredNode) {
        cam.rotY += 0.0032;
      }

      const cosY = Math.cos(cam.rotY);
      const sinY = Math.sin(cam.rotY);
      const cosX = Math.cos(cam.rotX);
      const sinX = Math.sin(cam.rotX);
      const fov = 540 * cam.zoom;
      const viewerDist = 490;

      // Chiếu tọa độ 3D -> 2D
      const projectedMap = new Map();
      const projectedList = simData.nodes3d.map((n) => {
        const x1 = n.x * cosY - n.z * sinY;
        const z1 = n.z * cosY + n.x * sinY;
        const y2 = n.y * cosX - z1 * sinX;
        const z2 = z1 * cosX + n.y * sinX;

        const depth = Math.max(viewerDist + z2, 90);
        const scale = fov / depth;
        const sx = W * 0.52 + cam.panX + x1 * scale;
        const sy = H * 0.52 + cam.panY + y2 * scale;

        const proj = { ...n, sx, sy, z2, scale };
        projectedMap.set(n.id, proj);
        return proj;
      });

      const focusId = hoveredNode?.id || selectedNode?.id;
      const connectedIds = new Set();
      if (focusId) {
        connectedIds.add(focusId);
        for (const e of simData.edges3d) {
          if (e.source === focusId) connectedIds.add(e.target);
          if (e.target === focusId) connectedIds.add(e.source);
        }
        for (const m of simData.meshEdges) {
          if (m.source === focusId) connectedIds.add(m.target);
          if (m.target === focusId) connectedIds.add(m.source);
        }
      }

      // Bật chế độ hòa trộn ánh sáng cộng (Additive Blending) để tạo hiệu ứng tia laser & sao phát sáng như Hình 2
      ctx.globalCompositeOperation = 'lighter';

      // 2. Vẽ mạng lưới sợi đa giác chòm sao (Constellation Mesh Filaments)
      for (const m of simData.meshEdges) {
        const src = projectedMap.get(m.source);
        const tgt = projectedMap.get(m.target);
        if (!src || !tgt) continue;
        const isHi = focusId && (m.source === focusId || m.target === focusId);
        const avgScale = (src.scale + tgt.scale) * 0.5;
        const alpha = isHi
          ? 0.55
          : Math.min(0.28, Math.max(0.05, avgScale * 0.22)) * (focusId ? 0.45 : 1);

        ctx.beginPath();
        ctx.moveTo(src.sx, src.sy);
        ctx.lineTo(tgt.sx, tgt.sy);
        ctx.strokeStyle = m.warm
          ? `rgba(251, 191, 36, ${alpha * 0.75})`
          : `rgba(56, 189, 248, ${alpha})`;
        ctx.lineWidth = isHi ? 1.2 : 0.65;
        ctx.stroke();
      }

      // 3. Vẽ các cạnh quan hệ Neo4j thật (PART_OF, DEFINED_IN, PENALIZED_BY, REFERENCES)
      for (let idx = 0; idx < simData.edges3d.length; idx++) {
        const e = simData.edges3d[idx];
        const src = projectedMap.get(e.source);
        const tgt = projectedMap.get(e.target);
        if (!src || !tgt) continue;

        const isHighlighted = focusId && (e.source === focusId || e.target === focusId);
        const avgScale = (src.scale + tgt.scale) * 0.5;
        const depthAlpha = Math.min(0.65, Math.max(0.12, avgScale * 0.36));

        ctx.beginPath();
        ctx.moveTo(src.sx, src.sy);
        ctx.lineTo(tgt.sx, tgt.sy);
        if (isHighlighted) {
          ctx.strokeStyle = 'rgba(125, 211, 252, 0.9)';
          ctx.lineWidth = 1.7;
        } else {
          const isWarmEdge = e.label === 'PENALIZED_BY' || e.label === 'DEFINED_IN';
          ctx.strokeStyle = isWarmEdge
            ? `rgba(251, 191, 36, ${focusId ? depthAlpha * 0.35 : depthAlpha * 0.68})`
            : `rgba(56, 189, 248, ${focusId ? depthAlpha * 0.35 : depthAlpha * 0.82})`;
          ctx.lineWidth = Math.max(0.6, avgScale * 0.75);
        }
        ctx.stroke();
      }

      // 4. Vẽ các Đỉnh Ngôi Sao Phát Quang (Radiant Glowing Star Nodes chuẩn Hình 2 - KHÔNG VẼ CHỮ ĐÈ LÊN HÌNH)
      projectedList.sort((a, b) => b.z2 - a.z2);

      for (const n of projectedList) {
        const style = NODE_PALETTE[n.type] || NODE_PALETTE.Action;
        const pulse = 0.9 + 0.14 * Math.sin(timeTick * 1.8 + (n.phase || 0));
        const r = Math.max(2.2, style.radius * n.scale * 0.85 * pulse);
        const isSelected = selectedNode?.id === n.id;
        const isHovered = hoveredNode?.id === n.id;
        const isDimmed = focusId && !connectedIds.has(n.id);

        const alphaMul = isDimmed ? 0.22 : Math.min(1, Math.max(0.45, n.scale * 0.9));
        const haloRadius = r * style.glowScale * (isSelected || isHovered ? 1.55 : 1.0);

        // Lớp 1: Quầng hào quang tỏa rộng (Outer Star Bloom)
        const outerGlow = ctx.createRadialGradient(n.sx, n.sy, 0, n.sx, n.sy, haloRadius);
        outerGlow.addColorStop(0, style.core);
        outerGlow.addColorStop(0.16, style.inner);
        outerGlow.addColorStop(0.42, style.halo);
        outerGlow.addColorStop(1, style.outer);

        ctx.globalAlpha = alphaMul;
        ctx.fillStyle = outerGlow;
        ctx.beginPath();
        ctx.arc(n.sx, n.sy, haloRadius, 0, Math.PI * 2);
        ctx.fill();

        // Lớp 2: Nhân sao trắng nóng rực rỡ (White-Hot Star Core)
        ctx.fillStyle = '#ffffff';
        ctx.beginPath();
        ctx.arc(n.sx, n.sy, Math.max(1.4, r * 0.58), 0, Math.PI * 2);
        ctx.fill();

        // Tia chữ thập (Star Flare) cho các đỉnh Văn bản Luật hoặc đỉnh đang chọn giống các ngôi sao lớn ở Hình 2
        if (n.type === 'LegalDoc' || isSelected || isHovered) {
          const flareLen = haloRadius * (isSelected || isHovered ? 1.15 : 0.85);
          ctx.strokeStyle =
            n.type === 'LegalDoc'
              ? 'rgba(167, 243, 208, 0.55)'
              : 'rgba(254, 243, 199, 0.75)';
          ctx.lineWidth = isSelected || isHovered ? 1.2 : 0.75;
          ctx.beginPath();
          ctx.moveTo(n.sx - flareLen, n.sy);
          ctx.lineTo(n.sx + flareLen, n.sy);
          ctx.moveTo(n.sx, n.sy - flareLen);
          ctx.lineTo(n.sx, n.sy + flareLen);
          ctx.stroke();
        }
      }

      // Trả về chế độ vẽ bình thường để chỉ hiển thị nhãn nổi duy nhất cho Node đang di chuột / bấm chọn
      ctx.globalCompositeOperation = 'source-over';
      ctx.globalAlpha = 1;

      const activeFocusNode =
        (hoveredNode && projectedMap.get(hoveredNode.id)) ||
        (selectedNode && projectedMap.get(selectedNode.id));

      if (activeFocusNode) {
        const labelText = activeFocusNode.data?.title || activeFocusNode.label || '';
        const shortLabel = labelText.length > 48 ? labelText.slice(0, 46) + '…' : labelText;
        ctx.font = '600 11.5px Inter, system-ui, sans-serif';
        const tw = ctx.measureText(shortLabel).width;
        const boxX = Math.max(8, Math.min(W - tw - 24, activeFocusNode.sx - tw / 2 - 10));
        const boxY = Math.max(10, activeFocusNode.sy - 34);

        ctx.fillStyle = 'rgba(7, 14, 28, 0.88)';
        ctx.strokeStyle = 'rgba(251, 191, 36, 0.65)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.roundRect(boxX, boxY, tw + 20, 24, 6);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = '#fef3c7';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.fillText(shortLabel, boxX + 10, boxY + 12);
      }

      canvas._projectedNodes = projectedList;
      ctx.restore();
      animId = requestAnimationFrame(render);
    };

    animId = requestAnimationFrame(render);
    return () => cancelAnimationFrame(animId);
  }, [simData, bgStars, autoRotate, hoveredNode, selectedNode]);

  // Xử lý kéo xoay 3D, click chọn ngôi sao và lăn chuột zoom
  const findNodeAt = (clientX, clientY) => {
    const canvas = canvasRef.current;
    if (!canvas || !canvas._projectedNodes) return null;
    const rect = canvas.getBoundingClientRect();
    const mx = clientX - rect.left;
    const my = clientY - rect.top;
    const list = [...canvas._projectedNodes].reverse();
    for (const n of list) {
      const style = NODE_PALETTE[n.type] || NODE_PALETTE.Action;
      const hitRadius = Math.max(11, style.radius * n.scale * 1.8);
      const dx = mx - n.sx;
      const dy = my - n.sy;
      if (dx * dx + dy * dy <= hitRadius * hitRadius) {
        return n;
      }
    }
    return null;
  };

  const handleMouseDown = (e) => {
    cameraRef.current.isDragging = true;
    cameraRef.current.dragStartX = e.clientX;
    cameraRef.current.dragStartY = e.clientY;
    cameraRef.current.moved = false;
  };

  const handleMouseMove = (e) => {
    const cam = cameraRef.current;
    if (cam.isDragging) {
      const dx = e.clientX - cam.dragStartX;
      const dy = e.clientY - cam.dragStartY;
      if (Math.abs(dx) > 2 || Math.abs(dy) > 2) cam.moved = true;
      if (e.shiftKey || e.buttons === 2) {
        cam.panX += dx;
        cam.panY += dy;
      } else {
        cam.rotY += dx * 0.0065;
        cam.rotX = Math.max(-1.35, Math.min(1.35, cam.rotX + dy * 0.0065));
      }
      cam.dragStartX = e.clientX;
      cam.dragStartY = e.clientY;
      return;
    }
    const hit = findNodeAt(e.clientX, e.clientY);
    setHoveredNode(hit || null);
  };

  const handleMouseUp = (e) => {
    const wasMoved = cameraRef.current.moved;
    cameraRef.current.isDragging = false;
    if (!wasMoved) {
      const hit = findNodeAt(e.clientX, e.clientY);
      setSelectedNode(hit || null);
    }
  };

  const handleWheel = (e) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.12 : 0.89;
    cameraRef.current.zoom = Math.max(0.45, Math.min(2.8, cameraRef.current.zoom * factor));
  };

  const resetCamera = () => {
    cameraRef.current = {
      ...cameraRef.current,
      rotX: 0.22,
      rotY: 0.55,
      zoom: 1.05,
      panX: 0,
      panY: 0,
    };
  };

  return (
    <div className="graph3d-wrapper">
      {/* Thanh chuyển đổi chế độ Đồ thị 3D */}
      <div className="graph3d-toolbar">
        <div className="graph3d-mode-switch">
          <button
            type="button"
            className={`mode-pill ${graphMode === 'live' ? 'active' : ''}`}
            onClick={() => setGraphMode('live')}
          >
            <Database size={12} />
            <span>Toàn cảnh Neo4j 3D ({neo4jStats?.total_nodes?.toLocaleString() || '13.7K'} Nodes)</span>
          </button>
          <button
            type="button"
            className={`mode-pill ${graphMode === 'query' ? 'active' : ''}`}
            onClick={() => setGraphMode('query')}
            disabled={!hasQueryGraph}
            title={hasQueryGraph ? 'Xem đồ thị của câu hỏi vừa hỏi' : 'Hãy đặt câu hỏi để kích hoạt nhánh đồ thị truy vấn'}
          >
            <Sparkles size={12} />
            <span>Nhánh Câu hỏi {hasQueryGraph ? '' : '(Chưa hỏi)'}</span>
          </button>
        </div>

        {/* Bộ lọc theo Văn bản Luật và Tìm kiếm Node */}
        {graphMode === 'live' && (
          <div className="graph3d-filters">
            <select
              className="graph3d-select"
              value={selectedDocCode}
              onChange={(e) => onSelectDocCode(e.target.value)}
            >
              <option value="">🌐 Toàn bộ Kho Tri thức (35 Văn bản Luật & Nghị định)</option>
              {overviewDocs.map((doc) => (
                <option key={doc.code} value={doc.code}>
                  📘 {doc.short} ({doc.articles} Điều)
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="graph3d-search-row">
          <div className="graph3d-search-box">
            <Search size={13} className="search-icon" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Tìm nhanh Điều, Hành vi, Văn bản trên không gian 3D..."
            />
            {searchTerm && (
              <button type="button" onClick={() => setSearchTerm('')} className="clear-search-btn">
                <X size={12} />
              </button>
            )}
          </div>
          <button
            type="button"
            className="guide-trigger-btn"
            onClick={onOpenGuide}
            title="Hướng dẫn mở trên phần mềm Neo4j Desktop / Browser"
          >
            <Terminal size={12} />
            <span>Mở trên Neo4j App</span>
          </button>
        </div>
      </div>

      {/* Khung Canvas 3D chuẩn phong cách Neo4j Cosmic Constellation (Hình 2) */}
      <div
        className="graph3d-stage"
        style={{ height: isFullscreen ? 'calc(100vh - 210px)' : '410px' }}
      >
        <canvas
          ref={canvasRef}
          className="graph3d-canvas"
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={() => {
            cameraRef.current.isDragging = false;
            setHoveredNode(null);
          }}
          onWheel={handleWheel}
        />

        {/* Overlay trạng thái đang tải */}
        {isLoadingGraph && (
          <div className="graph3d-loading-overlay">
            <Loader2 size={22} className="spin-icon" />
            <span>Đang đồng bộ không gian 3D từ Neo4j...</span>
          </div>
        )}

        {/* Nút điều khiển Camera 3D nổi */}
        <div className="graph3d-controls">
          <button
            type="button"
            onClick={() => setAutoRotate(!autoRotate)}
            title={autoRotate ? 'Tạm dừng tự xoay 3D' : 'Bật tự xoay 3D'}
            className={autoRotate ? 'active' : ''}
          >
            {autoRotate ? <Pause size={13} /> : <Play size={13} />}
          </button>
          <button
            type="button"
            onClick={() => {
              cameraRef.current.zoom = Math.min(2.8, cameraRef.current.zoom * 1.18);
            }}
            title="Phóng to 3D"
          >
            <ZoomIn size={13} />
          </button>
          <button
            type="button"
            onClick={() => {
              cameraRef.current.zoom = Math.max(0.45, cameraRef.current.zoom * 0.84);
            }}
            title="Thu nhỏ 3D"
          >
            <ZoomOut size={13} />
          </button>
          <button type="button" onClick={resetCamera} title="Đặt lại góc nhìn 3D">
            <RotateCcw size={13} />
          </button>
          <button
            type="button"
            onClick={onToggleFullscreen}
            title={isFullscreen ? 'Thu gọn khung 3D' : 'Mở rộng Toàn màn hình 3D'}
          >
            {isFullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
          </button>
        </div>
      </div>

      {/* Chi tiết Node 3D khi bấm chọn */}
      {selectedNode && (
        <div className="graph3d-inspector">
          <div className="inspector-header">
            <span
              className="inspector-badge"
              style={{
                background: NODE_PALETTE[selectedNode.type]?.bg || '#eff6ff',
                color: NODE_PALETTE[selectedNode.type]?.text || '#1d4ed8',
              }}
            >
              {NODE_PALETTE[selectedNode.type]?.tag || selectedNode.type}
            </span>
            <button type="button" onClick={() => setSelectedNode(null)} className="inspector-close">
              <X size={14} />
            </button>
          </div>
          <div className="inspector-title">
            {selectedNode.data?.title || selectedNode.label}
          </div>
          {selectedNode.data?.full_name && selectedNode.data?.full_name !== selectedNode.data?.title && (
            <div className="inspector-body">{selectedNode.data.full_name}</div>
          )}
          {selectedNode.data?.code && (
            <div className="inspector-meta">
              <span>Mã hiệu: <b>{selectedNode.data.code}</b></span>
              {selectedNode.type === 'LegalDoc' && graphMode === 'live' && (
                <button
                  type="button"
                  className="inspector-action-btn"
                  onClick={() => onSelectDocCode(selectedNode.data.code)}
                >
                  Khám phá riêng văn bản này →
                </button>
              )}
            </div>
          )}
          {selectedNode.data?.items && (
            <div className="inspector-body">• {selectedNode.data.items.join('; ')}</div>
          )}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Hàm sao chép an toàn (hỗ trợ cả localhost HTTPS và mạng LAN HTTP)
function safeCopyToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).catch(() => {});
    return;
  }
  try {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-9999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    document.execCommand('copy');
    document.body.removeChild(textArea);
  } catch {
    // ignore
  }
}

// ============================================================================
// MODAL HƯỚNG DẪN KẾT NỐI PHẦN MỀM NEO4J DESKTOP / NEO4J BROWSER
// ============================================================================
function Neo4jConnectionModal({ isOpen, onClose, stats }) {
  const [copiedKey, setCopiedKey] = useState('');

  if (!isOpen) return null;

  const copyText = (key, value) => {
    safeCopyToClipboard(value);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(''), 1800);
  };

  const cypherSample = `MATCH (d:LegalDoc)<-[:PART_OF]-(a:Article)
OPTIONAL MATCH (k:Clause)-[:PART_OF]->(a)
OPTIONAL MATCH (act:Action)-[:DEFINED_IN]->(k)
OPTIONAL MATCH (act)-[:PENALIZED_BY]->(p:Penalty)
RETURN d, a, k, act, p LIMIT 120;`;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div className="modal-icon">
              <Database size={18} />
            </div>
            <div>
              <h3>Kết nối Đồ thị với App Neo4j Desktop & Neo4j Browser</h3>
              <p>
                Hiện có sẵn <b>{stats?.total_nodes?.toLocaleString() || '13.751'} đỉnh</b> và{' '}
                <b>{(stats?.total_edges || stats?.total_relationships || 17959).toLocaleString()} cạnh</b> trong Neo4j
              </p>
            </div>
          </div>
          <button type="button" onClick={onClose} className="modal-close-btn">
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          <div className="guide-alert">
            💡 <b>Vì sao bạn mở phần mềm Neo4j Desktop tải về mà thấy trống?</b>
            <br />
            Toàn bộ dữ liệu Đồ thị Luật CNTT đang chạy trong container <code>law_neo4j</code> tại cổng{' '}
            <code>7687</code>. Phần mềm <b>Neo4j Desktop</b> khi mới cài sẽ tạo một DB trống mặc định. Để
            nhìn thấy toàn bộ 35 văn bản luật trên phần mềm Neo4j Desktop (hoặc Neo4j Browser), bạn chỉ cần
            kết nối vào địa chỉ dưới đây:
          </div>

          <div className="Guide-step-title">Bước 1: Thông số kết nối (Remote Connection trong Neo4j Desktop)</div>
          <div className="conn-grid">
            {[
              { label: 'Connect URL (Bolt)', val: 'bolt://localhost:7687', key: 'bolt' },
              { label: 'Neo4j Browser (Web)', val: 'http://localhost:7474', key: 'http' },
              { label: 'Username', val: 'neo4j', key: 'user' },
              { label: 'Password', val: 'lawgraph2906', key: 'pass' },
            ].map((item) => (
              <div key={item.key} className="conn-item">
                <div>
                  <span className="conn-label">{item.label}</span>
                  <code className="conn-val">{item.val}</code>
                </div>
                <button
                  type="button"
                  className="copy-mini-btn"
                  onClick={() => copyText(item.key, item.val)}
                >
                  {copiedKey === item.key ? <Check size={13} /> : <Copy size={13} />}
                </button>
              </div>
            ))}
          </div>

          <div className="Guide-step-title">
            Bước 2: Dán lệnh Cypher này vào thanh lệnh trên cùng rồi bấm ▶ (Run)
          </div>
          <div className="cypher-box">
            <pre>{cypherSample}</pre>
            <button
              type="button"
              className="copy-cypher-btn"
              onClick={() => copyText('cypher', cypherSample)}
            >
              {copiedKey === 'cypher' ? (
                <>
                  <Check size={13} /> Đã chép lệnh
                </>
              ) : (
                <>
                  <Copy size={13} /> Sao chép lệnh Cypher
                </>
              )}
            </button>
          </div>

          <div className="modal-actions">
            <a
              href="http://localhost:7474/browser/"
              target="_blank"
              rel="noreferrer"
              className="open-neo4j-web-btn"
            >
              <ExternalLink size={15} />
              <span>Mở ngay Neo4j Browser (http://localhost:7474)</span>
            </a>
            <button type="button" onClick={onClose} className="close-modal-secondary">
              Đã hiểu
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// VŨ KHÍ 3: BẢNG ĐIỀU KHIỂN MÔ PHỎNG TÌNH HUỐNG PHÁP LÝ (INTERACTIVE WHAT-IF SANDBOX)
// ============================================================================
function formatVndClient(amount) {
  if (amount == null) return '0 đồng';
  return `${Math.round(amount).toLocaleString('vi-VN')} đồng`;
}

function WhatIfSandbox({ penaltyCalcs = [] }) {
  const [simSubject, setSimSubject] = useState('INDIVIDUAL'); // 'ORGANIZATION' | 'INDIVIDUAL'
  const [simAgeGroup, setSimAgeGroup] = useState('ADULT');    // 'ADULT' | '16_18' | '14_16' | 'UNDER_14'
  const [simRecidivism, setSimRecidivism] = useState(false);

  const primary = penaltyCalcs[0];
  if (!primary) return null;

  // Suy ra khung phạt gốc của Tổ chức (hoặc Cá nhân nếu là Điều 106)
  const artNum = Number(primary.article_number || 101);
  const isArt106 = artNum === 106;
  let baseMin = primary.base_min;
  let baseMax = primary.base_max;
  if (baseMin == null || baseMax == null) {
    const orgRow = primary.calculations?.find((c) => c.subject === 'ORGANIZATION' && c.min_amount);
    const indRow = primary.calculations?.find((c) => c.subject === 'INDIVIDUAL' && c.min_amount);
    if (orgRow) {
      baseMin = orgRow.min_amount;
      baseMax = orgRow.max_amount;
    } else if (indRow) {
      baseMin = isArt106 ? indRow.min_amount : indRow.min_amount * 2;
      baseMax = isArt106 ? indRow.max_amount : indRow.max_amount * 2;
    } else {
      baseMin = 10000000;
      baseMax = 20000000;
    }
  }

  let simDisplay = '';
  let simFormula = '';
  let simBasis = 'Điều 4 Khoản 3 Nghị định 15/2020/NĐ-CP';

  if (simRecidivism && primary.criminal_escalations?.length > 0) {
    const ce = primary.criminal_escalations[0];
    simDisplay = `Chuyển truy cứu Hình sự: ${ce.penalty}`;
    simFormula = `Tái phạm / Gây hậu quả nghiêm trọng → ${ce.title}`;
    simBasis = 'Bộ luật Hình sự 2015 (sửa đổi, bổ sung 2017 - 100/2015/QH13)';
  } else if (simSubject === 'ORGANIZATION') {
    if (isArt106) {
      simDisplay = 'Không áp dụng cho Tổ chức (Điều 106 chỉ áp dụng đối với Cá nhân/Người chơi)';
      simFormula = 'Ngoại lệ Điều 106 NĐ 15/2020';
    } else {
      simDisplay = `${formatVndClient(baseMin)} – ${formatVndClient(baseMax)}`;
      simFormula = '100% khung phạt gốc áp dụng đối với Tổ chức';
    }
  } else {
    // Chủ thể Cá nhân
    const indMin = isArt106 ? baseMin : baseMin * 0.5;
    const indMax = isArt106 ? baseMax : baseMax * 0.5;
    if (simAgeGroup === 'UNDER_14') {
      simDisplay = '0 đồng (Không xử phạt vi phạm hành chính)';
      simFormula = 'Người dưới 14 tuổi chưa đủ tuổi chịu trách nhiệm VPHC';
      simBasis = 'Điều 5 Khoản 1 Điểm a Luật Xử lý vi phạm hành chính';
    } else if (simAgeGroup === '14_16') {
      simDisplay = '0 đồng (Chỉ phạt Cảnh cáo, không áp dụng phạt tiền)';
      simFormula = 'Người từ đủ 14 đến dưới 16 tuổi: Không phạt tiền';
      simBasis = 'Điều 5 & Điều 22 Luật Xử lý vi phạm hành chính';
    } else if (simAgeGroup === '16_18') {
      simDisplay = `${formatVndClient(indMin * 0.5)} – ${formatVndClient(indMax * 0.5)}`;
      simFormula = isArt106
        ? '1/2 × mức phạt người thành niên (Điều 106)'
        : '1/2 (Cá nhân) × 1/2 (Vị thành niên 16–<18 tuổi) = 1/4 mức Tổ chức';
      simBasis = 'Điều 134 Khoản 3 Luật XLVPHC & Điều 4 K.3 NĐ 15/2020';
    } else {
      simDisplay = `${formatVndClient(indMin)} – ${formatVndClient(indMax)}`;
      simFormula = isArt106
        ? 'Áp dụng trực tiếp khung Cá nhân (Ngoại lệ Điều 106)'
        : 'Cá nhân thành niên = 1/2 × mức phạt Tổ chức';
    }
  }

  return (
    <div className="card-box sandbox-box">
      <div className="card-box-title">
        <Sliders size={14} className="icon-purple" />
        <span>Mô phỏng Tình huống Pháp lý (Symbolic What-If Sandbox)</span>
      </div>
      <p className="sandbox-sub">
        Thay đổi biến số trực tiếp để kiểm chứng bộ suy luận toán học tất định (Rule Engine 0ms):
      </p>

      <div className="sandbox-controls">
        <div className="sandbox-row">
          <span className="sandbox-label">1. Chủ thể vi phạm:</span>
          <div className="sandbox-pills">
            <button
              type="button"
              className={`sandbox-pill ${simSubject === 'ORGANIZATION' ? 'active' : ''}`}
              onClick={() => setSimSubject('ORGANIZATION')}
            >
              🏢 Tổ chức (1x)
            </button>
            <button
              type="button"
              className={`sandbox-pill ${simSubject === 'INDIVIDUAL' ? 'active' : ''}`}
              onClick={() => setSimSubject('INDIVIDUAL')}
            >
              👤 Cá nhân (1/2x)
            </button>
          </div>
        </div>

        {simSubject === 'INDIVIDUAL' && (
          <div className="sandbox-row">
            <span className="sandbox-label">2. Độ tuổi chủ thể:</span>
            <div className="sandbox-pills">
              {[
                { id: 'ADULT', label: '≥ 18 tuổi' },
                { id: '16_18', label: '16 – <18 tuổi' },
                { id: '14_16', label: '14 – <16 tuổi' },
                { id: 'UNDER_14', label: '< 14 tuổi' },
              ].map((g) => (
                <button
                  key={g.id}
                  type="button"
                  className={`sandbox-pill ${simAgeGroup === g.id ? 'active' : ''}`}
                  onClick={() => setSimAgeGroup(g.id)}
                >
                  {g.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {primary.criminal_escalations?.length > 0 && (
          <div className="sandbox-row">
            <span className="sandbox-label">3. Mức độ & Hậu quả:</span>
            <div className="sandbox-pills">
              <button
                type="button"
                className={`sandbox-pill ${!simRecidivism ? 'active' : ''}`}
                onClick={() => setSimRecidivism(false)}
              >
                Vi phạm Hành chính lần đầu
              </button>
              <button
                type="button"
                className={`sandbox-pill danger ${simRecidivism ? 'active' : ''}`}
                onClick={() => setSimRecidivism(true)}
              >
                ⚠️ Tái phạm / Hậu quả nghiêm trọng (Hình sự)
              </button>
            </div>
          </div>
        )}
      </div>

      <div className={`sandbox-output ${simRecidivism ? 'criminal-mode' : ''}`}>
        <div className="sandbox-result-main">{simDisplay}</div>
        <div className="sandbox-result-meta">
          <span><b>Công thức:</b> {simFormula}</span>
          <span><b>Căn cứ:</b> {simBasis}</span>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// VŨ KHÍ 4: XUẤT PHIẾU TƯ VẤN PHÁP LÝ / ĐƠN TRÌNH BÁO AN NINH MẠNG (PRINT/PDF)
// ============================================================================
function exportLegalAdvisoryReport(questionText, botMsg) {
  const sym = botMsg?.symbolicData;
  const calcs = sym?.reasoning?.penalty_calculations || [];
  const sources = sym?.sources || [];
  const nowStr = new Date().toLocaleString('vi-VN');

  const calcRowsHtml = calcs
    .map(
      (c) => `
      <div style="border:1px solid #cbd5e1;border-radius:8px;padding:12px;margin-bottom:10px;background:#f8fafc;">
        <div style="font-weight:700;color:#0f172a;margin-bottom:4px;">Hành vi: ${c.action}</div>
        <div style="font-size:12px;color:#2563eb;font-weight:600;margin-bottom:8px;">Căn cứ: ${c.clause}, ${c.article}</div>
        ${(c.calculations || [])
          .map(
            (r) =>
              `<div style="font-size:13px;margin:3px 0;">• <b>${r.subject_label}:</b> <span style="color:#dc2626;font-weight:700;">${r.display}</span> <i>(${r.formula})</i></div>`
          )
          .join('')}
        ${
          c.sanctions?.length
            ? `<div style="font-size:12.5px;margin-top:6px;color:#475569;"><b>Biện pháp khắc phục hậu quả:</b> ${c.sanctions.join('; ')}</div>`
            : ''
        }
        ${
          c.criminal_escalations?.length
            ? `<div style="font-size:12.5px;margin-top:6px;color:#991b1b;background:#fef2f2;padding:6px 8px;border-radius:6px;"><b>⚖️ Cảnh báo Chuyển hóa Hình sự (Multi-Hop):</b> ${c.criminal_escalations
                .map((ce) => `${ce.title} — ${ce.penalty}`)
                .join(' | ')}</div>`
            : ''
        }
      </div>`
    )
    .join('');

  const sourcesHtml = sources
    .map(
      (s) =>
        `<li style="margin-bottom:6px;"><b>${s.title}</b> — ${s.article} (Trang ${s.page}): <i>"${s.snippet}"</i></li>`
    )
    .join('');

  const html = `<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8" />
  <title>Phiếu Tư vấn Pháp lý CNTT — LexIT Neuro-Symbolic</title>
  <style>
    body { font-family: "Times New Roman", Times, serif; color: #111827; max-width: 820px; margin: 28px auto; padding: 0 24px; line-height: 1.55; }
    .header-table { width: 100%; border-collapse: collapse; margin-bottom: 18px; }
    .header-table td { text-align: center; vertical-align: top; }
    .report-title { text-align: center; font-size: 20px; font-weight: bold; text-transform: uppercase; margin: 18px 0 4px; color: #1e3a8a; }
    .report-sub { text-align: center; font-size: 13px; font-style: italic; color: #4b5563; margin-bottom: 20px; }
    .section-title { font-size: 15px; font-weight: bold; text-transform: uppercase; color: #1e3a8a; border-bottom: 1.5px solid #1e3a8a; padding-bottom: 4px; margin: 18px 0 10px; }
    .box { background: #f9fafb; border: 1px solid #d1d5db; border-radius: 6px; padding: 12px 14px; font-size: 14px; white-space: pre-wrap; }
    .print-bar { display: flex; justify-content: flex-end; gap: 10px; margin-bottom: 16px; font-family: sans-serif; }
    .print-btn { background: #2563eb; color: #fff; border: none; border-radius: 6px; padding: 8px 16px; font-weight: 600; cursor: pointer; }
    @media print { .print-bar { display: none; } body { margin: 0; } }
  </style>
</head>
<body>
  <div class="print-bar">
    <button class="print-btn" onclick="window.print()">🖨️ In Phiếu Tư vấn / Lưu PDF</button>
  </div>
  <table class="header-table">
    <tr>
      <td style="width:45%;">
        <b>HỆ THỐNG TRỢ LÝ ẢO PHÁP LUẬT LEX-IT</b><br/>
        <span>Kiến trúc Neuro-Symbolic AI & Đồ thị Neo4j</span>
      </td>
      <td style="width:55%;">
        <b>CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM</b><br/>
        <b>Độc lập - Tự do - Hạnh phúc</b><br/>
        <span>───────────────</span>
      </td>
    </tr>
  </table>
  <div class="report-title">PHIẾU TƯ VẤN PHÁP LUẬT CÔNG NGHỆ THÔNG TIN & AN NINH MẠNG</div>
  <div class="report-sub">Thời điểm trích xuất: ${nowStr} • Mã kiểm chứng: Symbolic-Rule-Engine-v2.2</div>

  <div class="section-title">I. NỘI DUNG TÌNH HUỐNG / YÊU CẦU TƯ VẤN</div>
  <div class="box">${(questionText || 'Tư vấn pháp luật CNTT').replace(/</g, '&lt;')}</div>

  ${
    calcRowsHtml
      ? `<div class="section-title">II. BẢNG TÍNH KHUNG HÌNH PHẠT & CHẾ TÀI TẤT ĐỊNH (SYMBOLIC ENGINE)</div>${calcRowsHtml}`
      : ''
  }

  <div class="section-title">III. Ý KIẾN TƯ VẤN PHÁP LÝ CHI TIẾT</div>
  <div class="box">${(botMsg?.text || '').replace(/</g, '&lt;')}</div>

  ${
    sourcesHtml
      ? `<div class="section-title">IV. CĂN CỨ VĂN BẢN QUY PHẠM PHÁP LUẬT TRÍCH DẪN (PGVECTOR & NEO4J)</div><ul style="font-size:13.5px;padding-left:20px;">${sourcesHtml}</ul>`
      : ''
  }

  <div style="margin-top:26px;font-size:12.5px;color:#4b5563;border-top:1px dashed #cbd5e1;padding-top:10px;">
    <b>Hướng dẫn trình báo khi bị xâm phạm quyền và lợi ích hợp pháp trên không gian mạng:</b><br/>
    1. Lưu giữ nguyên trạng bằng chứng điện tử (ảnh chụp màn hình kèm URL, thời gian, sao kê giao dịch, hợp đồng điện tử).<br/>
    2. Nộp đơn trình báo kèm Phiếu tư vấn này tới Phòng An ninh mạng và phòng, chống tội phạm sử dụng công nghệ cao (PA05 - Công an tỉnh/thành phố) hoặc Cơ quan điều tra nơi cư trú.
  </div>
</body>
</html>`;

  const win = window.open('', '_blank', 'width=900,height=800');
  if (win) {
    win.document.write(html);
    win.document.close();
  }
}

// ============================================================================
// VŨ KHÍ 5: MODAL BẢNG THỰC NGHIỆM ĐỊNH LƯỢNG TRỰC TIẾP (LIVE BENCHMARK MODAL)
// ============================================================================
function BenchmarkModal({ isOpen, onClose, data, isLoading, onRunBenchmark }) {
  if (!isOpen) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card benchmark-modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div className="modal-icon">
              <BarChart3 size={18} />
            </div>
            <div>
              <h3>Thực nghiệm Đối chứng: Naive Vector RAG vs. Neuro-Symbolic Hybrid RAG</h3>
              <p>
                Đánh giá định lượng tự động trên <b>{data?.total_cases || 8} kịch bản kiểm thử học thuật</b> (Chương 4 Đồ án)
              </p>
            </div>
          </div>
          <button type="button" onClick={onClose} className="modal-close-btn">
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          {isLoading ? (
            <div className="benchmark-loading">
              <Loader2 size={24} className="spin-icon" />
              <span>Đang thực thi bộ kiểm thử định lượng qua 8 kịch bản pháp lý...</span>
            </div>
          ) : data ? (
            <>
              <div className="benchmark-metrics-grid">
                {(data.metrics || []).map((m, idx) => (
                  <div key={idx} className="bench-metric-card">
                    <div className="bench-metric-title">{m.name}</div>
                    <div className="bench-bars">
                      <div className="bench-bar-row">
                        <span className="bench-bar-label">Naive RAG:</span>
                        <div className="bench-bar-track">
                          <div className="bench-bar-fill naive" style={{ width: `${m.naive}%` }} />
                        </div>
                        <span className="bench-bar-val">{m.naive}%</span>
                      </div>
                      <div className="bench-bar-row">
                        <span className="bench-bar-label">Neuro-Symbolic:</span>
                        <div className="bench-bar-track">
                          <div className="bench-bar-fill hybrid" style={{ width: `${m.hybrid}%` }} />
                        </div>
                        <span className="bench-bar-val highlight">{m.hybrid}%</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="bench-table-wrap">
                <table className="bench-table">
                  <thead>
                    <tr>
                      <th>Mã Ca</th>
                      <th>Kịch bản Kiểm thử Pháp lý</th>
                      <th>Trích dẫn (Naive / Hybrid)</th>
                      <th>Mức phạt & Tuổi (Naive / Hybrid)</th>
                      <th>Chủ thể & Guardrail (Naive / Hybrid)</th>
                      <th>Tốc độ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.cases || []).map((c) => (
                      <tr key={c.id}>
                        <td><b>{c.id}</b></td>
                        <td>{c.category}</td>
                        <td className="center-cell">
                          {c.n_citation ? '✅' : '❌'} / <b>{c.h_citation ? '✅' : '❌'}</b>
                        </td>
                        <td className="center-cell">
                          {c.n_fine_age ? '✅' : '❌'} / <b>{c.h_fine_age ? '✅' : '❌'}</b>
                        </td>
                        <td className="center-cell">
                          {c.n_subject_guardrail ? '✅' : '❌'} / <b>{c.h_subject_guardrail ? '✅' : '❌'}</b>
                        </td>
                        <td className="center-cell">{c.elapsed_seconds}s</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}

          <div className="modal-actions" style={{ justifyContent: 'space-between', marginTop: '14px' }}>
            <button
              type="button"
              className="open-neo4j-web-btn"
              onClick={() => onRunBenchmark(false)}
              disabled={isLoading}
            >
              <RefreshCw size={14} />
              <span>Chạy lại Kiểm định Symbolic tức thì</span>
            </button>
            <button type="button" onClick={onClose} className="close-modal-secondary">
              Đóng bảng
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// MAIN APP: GIAO DIỆN PHONG CÁCH CHATGPT HIỆN ĐẠI + SIDEBAR LỊCH SỬ + 3D GRAPH
// ============================================================================
function App() {
  // Chế độ giao diện Nền Sáng / Nền Tối (Light / Dark Mode) lưu trong localStorage
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem('lexit_theme') || 'light';
    } catch {
      return 'light';
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem('lexit_theme', theme);
    } catch {
      // ignore
    }
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  // Quản lý danh sách cuộc trò chuyện (giống ChatGPT) lưu trong localStorage
  const [conversations, setConversations] = useState(() => {
    try {
      const saved = localStorage.getItem('lexit_conversations_v2');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch {
      // ignore
    }
    return [
      {
        id: 'conv-default',
        title: 'Cuộc trò chuyện mới',
        updatedAt: Date.now(),
        messages: [],
      },
    ];
  });

  const [activeConvId, setActiveConvId] = useState(() => conversations[0]?.id || 'conv-default');
  const [input, setInput] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isComparisonMode, setIsComparisonMode] = useState(false);
  const [showSymbolicPanel, setShowSymbolicPanel] = useState(true);
  const [isGraphFullscreen, setIsGraphFullscreen] = useState(false);
  const [activeTab, setActiveTab] = useState('graph'); // Mặc định mở ngay tab Đồ thị 3D!
  const [graphMode, setGraphMode] = useState('live');  // 'live' | 'query'
  const [isLoading, setIsLoading] = useState(false);
  const [currentSymbolicData, setCurrentSymbolicData] = useState(null);
  const [copiedMsgIdx, setCopiedMsgIdx] = useState(null);
  const [showNeo4jModal, setShowNeo4jModal] = useState(false);

  // Vũ khí 1: Bằng chứng Ảnh chụp màn hình / PDF đính kèm (OCR & Vision Evidence)
  const [evidenceAttachment, setEvidenceAttachment] = useState(null);
  const [isUploadingEvidence, setIsUploadingEvidence] = useState(false);
  const evidenceInputRef = useRef(null);

  // Vũ khí 5: Bảng Thực nghiệm Định lượng Trực tiếp (Live Benchmark Modal)
  const [showBenchmarkModal, setShowBenchmarkModal] = useState(false);
  const [benchmarkData, setBenchmarkData] = useState(null);
  const [isLoadingBenchmark, setIsLoadingBenchmark] = useState(false);

  // Dữ liệu Đồ thị Neo4j 3D trực tiếp từ Backend
  const [liveGraphData, setLiveGraphData] = useState({ nodes: [], edges: [] });
  const [overviewDocs, setOverviewDocs] = useState([]);
  const [selectedDocCode, setSelectedDocCode] = useState('');
  const [neo4jStats, setNeo4jStats] = useState(null);
  const [isLoadingGraph, setIsLoadingGraph] = useState(false);
  const [backendStatus, setBackendStatus] = useState({ neo4j: false, pgvector: false });

  const chatEndRef = useRef(null);
  const scrollViewportRef = useRef(null);
  const isNearBottomRef = useRef(true);
  const textareaRef = useRef(null);
  const abortControllerRef = useRef(null);

  const activeConversation = useMemo(
    () => conversations.find((c) => c.id === activeConvId) || conversations[0],
    [conversations, activeConvId]
  );
  const messages = activeConversation?.messages || [];

  // Lưu lịch sử hội thoại vào localStorage
  useEffect(() => {
    try {
      localStorage.setItem('lexit_conversations_v2', JSON.stringify(conversations));
    } catch {
      // ignore
    }
  }, [conversations]);

  // Kiểm tra sức khỏe Backend & tải Đồ thị Neo4j 3D ngay khi mở App
  const checkBackendHealth = useCallback(() => {
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
  }, []);

  const fetchLiveNeo4jGraph = useCallback((docCode = '') => {
    setIsLoadingGraph(true);
    axios
      .get(`${API_BASE_URL}/graph/overview`, {
        params: { doc_code: docCode || undefined, limit: docCode ? 130 : 120 },
      })
      .then((res) => {
        if (res.data?.graph_view) {
          setLiveGraphData(res.data.graph_view);
        }
        if (res.data?.documents) {
          setOverviewDocs(res.data.documents);
        }
        if (res.data?.stats) {
          setNeo4jStats(res.data.stats);
        }
        setBackendStatus((prev) => ({ ...prev, neo4j: true }));
      })
      .catch((err) => {
        console.error('Không thể tải đồ thị Neo4j 3D:', err);
      })
      .finally(() => {
        setIsLoadingGraph(false);
      });
  }, []);

  useEffect(() => {
    checkBackendHealth();
    fetchLiveNeo4jGraph('');
  }, [checkBackendHealth, fetchLiveNeo4jGraph]);

  useEffect(() => {
    if (isNearBottomRef.current) {
      chatEndRef.current?.scrollIntoView({ behavior: isLoading ? 'auto' : 'smooth' });
    }
  }, [messages, isLoading]);

  const handleViewportScroll = useCallback((e) => {
    const el = e.currentTarget;
    isNearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  }, []);

  // Tự động co giãn chiều cao ô nhập giống ChatGPT
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = '24px';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [input]);

  const handleSelectDocFilter = (code) => {
    setSelectedDocCode(code);
    setGraphMode('live');
    fetchLiveNeo4jGraph(code);
  };

  // Tạo cuộc trò chuyện mới giống ChatGPT
  const createNewChat = () => {
    abortControllerRef.current?.abort();
    const newId = `conv-${Date.now()}`;
    const newConv = {
      id: newId,
      title: 'Cuộc trò chuyện mới',
      updatedAt: Date.now(),
      messages: [],
    };
    setConversations((prev) => [newConv, ...prev]);
    setActiveConvId(newId);
    setCurrentSymbolicData(null);
    setGraphMode('live');
    setInput('');
  };

  const deleteConversation = (e, id) => {
    e.stopPropagation();
    if (id === activeConvId) {
      abortControllerRef.current?.abort();
    }
    setConversations((prev) => {
      const remaining = prev.filter((c) => c.id !== id);
      if (remaining.length === 0) {
        const fallback = {
          id: `conv-${Date.now()}`,
          title: 'Cuộc trò chuyện mới',
          updatedAt: Date.now(),
          messages: [],
        };
        setActiveConvId(fallback.id);
        return [fallback];
      }
      if (id === activeConvId) {
        setActiveConvId(remaining[0].id);
      }
      return remaining;
    });
  };

  // Vũ khí 1: Xử lý tải lên ảnh chụp màn hình / PDF bằng chứng để OCR tự động
  const handleEvidenceUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';
    setIsUploadingEvidence(true);

    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const resultStr = String(reader.result || '');
        const base64Part = resultStr.includes(',') ? resultStr.split(',')[1] : resultStr;
        const res = await axios.post(`${API_BASE_URL}/analyze-evidence`, {
          filename: file.name,
          content_base64: base64Part,
        });
        setEvidenceAttachment(res.data);
      } catch (err) {
        console.error('Lỗi phân tích bằng chứng:', err);
        setEvidenceAttachment({
          filename: file.name,
          char_count: 0,
          extracted_text: `[Bằng chứng đính kèm: ${file.name}]`,
        });
      } finally {
        setIsUploadingEvidence(false);
      }
    };
    reader.readAsDataURL(file);
  };

  // Vũ khí 5: Mở & chạy Bảng Thực nghiệm Định lượng (Benchmark)
  const handleRunBenchmark = useCallback(async (live = false) => {
    setShowBenchmarkModal(true);
    setIsLoadingBenchmark(true);
    try {
      const res = await axios.get(`${API_BASE_URL}/benchmark/run`, { params: { live } });
      setBenchmarkData(res.data);
    } catch (err) {
      console.error('Lỗi chạy benchmark:', err);
    } finally {
      setIsLoadingBenchmark(false);
    }
  }, []);

  // Gửi câu hỏi với luồng Streaming thời gian thực (hiển thị Đồ thị 3D < 0.2s & stream chữ tức thì)
  const sendMessage = async (questionText) => {
    const rawTyped = (questionText ?? input).trim();
    if ((!rawTyped && !evidenceAttachment) || isLoading) return;

    const textToSend = evidenceAttachment
      ? `[BẰNG CHỨNG ĐÍNH KÈM: ${evidenceAttachment.filename}]\nNội dung trích xuất OCR: "${evidenceAttachment.extracted_text.slice(0, 1200)}"\n\nCâu hỏi tư vấn: ${rawTyped || 'Hãy phân tích hành vi vi phạm pháp luật trong bằng chứng trên và tính mức xử phạt.'}`
      : rawTyped;

    const displayUserText = evidenceAttachment
      ? `📎 [Bằng chứng: ${evidenceAttachment.filename}]\n${rawTyped || 'Phân tích hành vi vi phạm và tính mức phạt từ bằng chứng đính kèm.'}`
      : rawTyped;

    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;
    isNearBottomRef.current = true;
    const targetConvId = activeConvId;

    const historyPayload = messages
      .slice(-4)
      .map((m) => ({ role: m.role, text: m.text }));

    const userMessage = { role: 'user', text: displayUserText };
    const updatedTitle =
      messages.length === 0
        ? displayUserText.slice(0, 38) + (displayUserText.length > 38 ? '…' : '')
        : activeConversation.title;

    const botMsgId = `bot-${Date.now()}`;
    const initialBotMessage = {
      id: botMsgId,
      role: 'bot',
      text: '',
      naiveText: null,
      symbolicData: null,
      streaming: true,
    };

    setConversations((prev) =>
      prev.map((c) =>
        c.id === targetConvId
          ? {
              ...c,
              title: updatedTitle,
              updatedAt: Date.now(),
              messages: [...c.messages, userMessage, initialBotMessage],
            }
          : c
      )
    );

    if (!questionText) setInput('');
    setEvidenceAttachment(null);
    setIsLoading(true);

    try {
      const res = await fetch(`${API_BASE_URL}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          question: textToSend,
          comparison_mode: isComparisonMode,
          history: historyPayload,
        }),
      });

      if (!res.ok || !res.body) {
        throw new Error(`HTTP ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      let accumulatedText = '';
      let latestSymbolic = null;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const rawLine of lines) {
          const line = rawLine.trim();
          if (!line) continue;
          let evt;
          try {
            evt = JSON.parse(line);
          } catch {
            continue;
          }

          if (evt.type === 'meta') {
            latestSymbolic = {
              reasoning: evt.symbolic_reasoning,
              graph: evt.graph_view,
              sources: evt.sources,
            };
            setCurrentSymbolicData(latestSymbolic);
            setShowSymbolicPanel(true);
            if (evt.graph_view?.nodes?.length > 0) {
              setGraphMode('query');
            }
            setConversations((prev) =>
              prev.map((c) =>
                c.id === targetConvId
                  ? {
                      ...c,
                      messages: c.messages.map((m) =>
                        m.id === botMsgId ? { ...m, symbolicData: latestSymbolic } : m
                      ),
                    }
                  : c
              )
            );
          } else if (evt.type === 'token') {
            accumulatedText += evt.content || '';
            const snapshot = accumulatedText;
            setConversations((prev) =>
              prev.map((c) =>
                c.id === targetConvId
                  ? {
                      ...c,
                      messages: c.messages.map((m) =>
                        m.id === botMsgId ? { ...m, text: snapshot } : m
                      ),
                    }
                  : c
              )
            );
          } else if (evt.type === 'done') {
            const finalText = evt.answer || accumulatedText;
            setConversations((prev) =>
              prev.map((c) =>
                c.id === targetConvId
                  ? {
                      ...c,
                      updatedAt: Date.now(),
                      messages: c.messages.map((m) =>
                        m.id === botMsgId
                          ? {
                              ...m,
                              text: finalText,
                              naiveText: evt.naive_answer,
                              symbolicData: latestSymbolic || m.symbolicData,
                              streaming: false,
                            }
                          : m
                      ),
                    }
                  : c
              )
            );
          }
        }
      }
    } catch (error) {
      if (error?.name === 'AbortError') return;
      console.error('Lỗi gọi API:', error);
      const errText =
        '⚠️ **Không thể kết nối tới máy chủ Backend (`http://127.0.0.1:8000`).**\n\nHãy đảm bảo bạn đã chạy lệnh `python main.py` trong thư mục `backend/` và container Docker (`law_neo4j`, `law_postgres_graph`) đang hoạt động.';
      setConversations((prev) =>
        prev.map((c) =>
          c.id === targetConvId
            ? {
                ...c,
                messages: c.messages.map((m) =>
                  m.id === botMsgId ? { ...m, text: errText, streaming: false } : m
                ),
              }
            : c
        )
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const copyMessage = (idx, text) => {
    safeCopyToClipboard(text);
    setCopiedMsgIdx(idx);
    setTimeout(() => setCopiedMsgIdx(null), 1800);
  };

  const activeSymbolic =
    currentSymbolicData ||
    messages
      .slice()
      .reverse()
      .find((m) => m.symbolicData)?.symbolicData;

  const queryGraphNodes = activeSymbolic?.graph?.nodes || [];
  const queryGraphEdges = activeSymbolic?.graph?.edges || [];
  const hasQueryGraph = queryGraphNodes.length > 0;

  const displayedGraphNodes =
    graphMode === 'query' && hasQueryGraph ? queryGraphNodes : liveGraphData.nodes;
  const displayedGraphEdges =
    graphMode === 'query' && hasQueryGraph ? queryGraphEdges : liveGraphData.edges;

  return (
    <div className={`chatgpt-app ${theme === 'dark' ? 'dark-theme' : 'light-theme'}`}>
      {/* ====================================================================
          1. THANH SIDEBAR BÊN TRÁI (PHONG CÁCH CHATGPT DARK SIDEBAR)
         ==================================================================== */}
      <aside className={`chatgpt-sidebar ${sidebarOpen ? 'open' : 'collapsed'}`}>
        <div className="sidebar-top-bar">
          <button
            type="button"
            className="sidebar-icon-btn"
            onClick={() => setSidebarOpen(false)}
            title="Thu gọn thanh bên"
          >
            <PanelLeftClose size={18} />
          </button>
          <button
            type="button"
            className="new-chat-btn"
            onClick={createNewChat}
            title="Bắt đầu cuộc trò chuyện mới"
          >
            <Plus size={16} />
            <span>Cuộc trò chuyện mới</span>
          </button>
        </div>

        {/* Nút nổi bật mở Không gian Đồ thị Neo4j 3D */}
        <div className="sidebar-3d-banner">
          <button
            type="button"
            className="explore-3d-btn"
            onClick={() => {
              setShowSymbolicPanel(true);
              setActiveTab('graph');
              setGraphMode('live');
            }}
          >
            <div className="explore-3d-icon">
              <Network size={16} />
            </div>
            <div className="explore-3d-text">
              <span className="explore-title">Khám phá Đồ thị Neo4j 3D</span>
              <span className="explore-sub">
                {neo4jStats
                  ? `${neo4jStats.total_nodes.toLocaleString()} Nodes • 35 Văn bản`
                  : 'Mạng lưới Tri thức Luật 3D'}
              </span>
            </div>
            <ChevronRight size={14} />
          </button>
        </div>

        {/* Danh sách Lịch sử Trò chuyện */}
        <div className="sidebar-scroll-area">
          <div className="sidebar-group-label">Lịch sử tư vấn</div>
          <div className="conv-list">
            {conversations.map((conv) => (
              <div
                key={conv.id}
                className={`conv-item ${conv.id === activeConvId ? 'active' : ''}`}
                onClick={() => {
                  if (conv.id !== activeConvId) {
                    abortControllerRef.current?.abort();
                    setIsLoading(false);
                  }
                  setActiveConvId(conv.id);
                  const lastSym = conv.messages
                    ?.slice()
                    .reverse()
                    .find((m) => m.symbolicData)?.symbolicData;
                  setCurrentSymbolicData(lastSym || null);
                }}
              >
                <MessageSquare size={14} className="conv-icon" />
                <span className="conv-title">{conv.title}</span>
                <button
                  type="button"
                  className="conv-delete-btn"
                  onClick={(e) => deleteConversation(e, conv.id)}
                  title="Xóa cuộc trò chuyện"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>

          {/* Kịch bản kiểm thử nhanh cho Hội đồng */}
          <div className="sidebar-group-label" style={{ marginTop: '18px' }}>
            Kịch bản Test
          </div>
          <div className="sidebar-scenarios">
            {SAMPLE_QUESTIONS.map((q, idx) => (
              <button
                key={idx}
                type="button"
                className="scenario-item"
                onClick={() => sendMessage(q.text)}
                disabled={isLoading}
              >
                <Sparkles size={13} className="scenario-icon" />
                <div className="scenario-text">
                  <span className="scenario-name">{q.title}</span>
                  <span className="scenario-tag">{q.tag}</span>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Chân Sidebar: Trạng thái Kết nối Hạ tầng */}
        <div className="sidebar-bottom-status">
          <div className="infra-row">
            <span className={`status-dot ${backendStatus.neo4j ? 'online' : 'offline'}`} />
            <span className="infra-name">Neo4j 5.26 Graph</span>
            <button
              type="button"
              className="infra-action-link"
              onClick={() => setShowNeo4jModal(true)}
            >
              Mở App 3D
            </button>
          </div>
          <div className="infra-row">
            <span className={`status-dot ${backendStatus.pgvector ? 'online' : 'offline'}`} />
            <span className="infra-name">PGVector (4.332 Vectors)</span>
            <button
              type="button"
              className="infra-refresh"
              onClick={() => {
                checkBackendHealth();
                fetchLiveNeo4jGraph(selectedDocCode);
              }}
              title="Đồng bộ lại trạng thái"
            >
              <RefreshCw size={12} />
            </button>
          </div>
        </div>
      </aside>

      {/* ====================================================================
          2. KHU VỰC TRÒ CHUYỆN TRUNG TÂM (PHONG CÁCH CHATGPT 4o/o1)
         ==================================================================== */}
      <main className="chatgpt-main">
        {/* Thanh Header tối giản kiểu ChatGPT */}
        <header className="chatgpt-topbar">
          <div className="topbar-left">
            {!sidebarOpen && (
              <button
                type="button"
                className="topbar-icon-btn"
                onClick={() => setSidebarOpen(true)}
                title="Mở thanh bên"
              >
                <PanelLeftOpen size={18} />
              </button>
            )}
            <div className="model-selector-pill">
              <Scale size={16} className="model-icon" />
              <span className="model-name">LexIT Neuro-Symbolic</span>
              <span className="model-version">2.2 Hybrid</span>
            </div>
          </div>

          <div className="topbar-right">
            {/* Nút chuyển đổi Nền Sáng / Nền Tối */}
            <button
              type="button"
              className="topbar-pill-btn theme-toggle-btn"
              onClick={toggleTheme}
              title={theme === 'dark' ? 'Chuyển sang Giao diện Nền sáng' : 'Chuyển sang Giao diện Nền tối'}
            >
              {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
              <span>{theme === 'dark' ? 'Nền sáng' : 'Nền tối'}</span>
            </button>

            {/* Nút Bảng Thực nghiệm Định lượng (Vũ khí 5) */}
            <button
              type="button"
              className="topbar-pill-btn benchmark-trigger-btn"
              onClick={() => handleRunBenchmark(false)}
              title="Mở Bảng Thực nghiệm Đối chứng Naive RAG vs. Neuro-Symbolic RAG (100% Accuracy)"
            >
              <BarChart3 size={15} />
              <span>Thực nghiệm (100%)</span>
            </button>

            {/* Nút bật/tắt So sánh Đối chứng A/B */}
            <button
              type="button"
              className={`topbar-pill-btn ${isComparisonMode ? 'active-ab' : ''}`}
              onClick={() => setIsComparisonMode(!isComparisonMode)}
              title="So sánh song song Naive Vector RAG vs. Neuro-Symbolic Hybrid RAG"
            >
              {isComparisonMode ? <ToggleRight size={17} /> : <ToggleLeft size={17} />}
              <span>So sánh A/B</span>
            </button>

            {/* Nút bật/tắt Khung Đồ thị 3D & Suy luận Symbolic */}
            <button
              type="button"
              className={`topbar-pill-btn ${showSymbolicPanel ? 'active-graph' : ''}`}
              onClick={() => setShowSymbolicPanel(!showSymbolicPanel)}
            >
              <Network size={15} />
              <span>Đồ thị Neo4j 3D & XAI</span>
            </button>
          </div>
        </header>

        {/* Nội dung cuộc trò chuyện hoặc Màn hình Chào mừng kiểu ChatGPT */}
        <div
          ref={scrollViewportRef}
          className="chatgpt-scroll-viewport"
          onScroll={handleViewportScroll}
        >
          {messages.length === 0 ? (
            <div className="chatgpt-welcome">
              <div className="welcome-badge-hero">
                <Scale size={28} />
              </div>
              <h1 className="welcome-heading">
                Tôi có thể giúp gì cho bạn về Pháp luật CNTT hôm nay?
              </h1>

              {/* Lưới 6 thẻ gợi ý câu hỏi kiểu ChatGPT (đã xóa phần chữ khoanh đỏ phía trên) */}
              <div className="starter-grid">
                {SAMPLE_QUESTIONS.map((item, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className="starter-card"
                    onClick={() => sendMessage(item.text)}
                  >
                    <div className="starter-card-top">
                      <span className="starter-card-title">{item.title}</span>
                      <span className="starter-card-tag">{item.tag}</span>
                    </div>
                    <p className="starter-card-desc">{item.text}</p>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className={`chatgpt-thread ${isComparisonMode ? 'wide' : ''}`}>
              {messages.map((msg, index) => {
                if (msg.role === 'user') {
                  return (
                    <div key={index} className="chatgpt-user-turn">
                      <div className="chatgpt-user-bubble">{msg.text}</div>
                    </div>
                  );
                }

                const nodeCount = msg.symbolicData?.graph?.nodes?.length || 0;
                const stepCount = msg.symbolicData?.reasoning?.rule_steps?.length || 0;

                return (
                  <div key={index} className="chatgpt-bot-turn">
                    <div className="chatgpt-bot-avatar">
                      <Scale size={16} />
                    </div>
                    <div className="chatgpt-bot-content">
                      <div className="bot-author-line">
                        <span className="bot-author-name">LexIT Neuro-Symbolic</span>
                        <span className="bot-author-badge">Hybrid AI</span>
                      </div>

                      {msg.streaming && !msg.text ? (
                        <div className="chatgpt-loading-box">
                          <div className="loading-title">
                            Đang truy xuất căn cứ pháp luật & suy luận Symbolic...
                          </div>
                          <div className="loading-steps-inline">
                            <span>1. PGVector Hybrid</span>
                            <span>→</span>
                            <span>2. Neo4j 3D Graph</span>
                            <span>→</span>
                            <span>3. Rule Engine</span>
                          </div>
                        </div>
                      ) : isComparisonMode && msg.naiveText ? (
                        <div className="comparison-container">
                          <div className="comparison-card naive-card">
                            <div className="card-header naive-header">
                              <span className="card-badge">NAIVE VECTOR RAG (CHỈ DÙNG VECTOR)</span>
                              <span className="warning-chip">Dễ nhầm chủ thể/mức phạt</span>
                            </div>
                            <div className="card-body markdown-prose">
                              <ReactMarkdown>{msg.naiveText}</ReactMarkdown>
                            </div>
                          </div>

                          <div className="comparison-card hybrid-card">
                            <div className="card-header hybrid-header">
                              <span className="card-badge highlight">NEURO-SYMBOLIC HYBRID RAG</span>
                              <span className="success-chip">Chính xác theo Rule Engine</span>
                            </div>
                            <div className="card-body markdown-prose">
                              <ReactMarkdown>{msg.text}</ReactMarkdown>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="markdown-prose">
                          <ReactMarkdown>{msg.text}</ReactMarkdown>
                        </div>
                      )}

                      {/* Thanh công cụ dưới mỗi câu trả lời kiểu ChatGPT */}
                      {msg.text && (
                        <div className="bot-message-actions">
                          <button
                            type="button"
                            className="msg-action-btn"
                            onClick={() => copyMessage(index, msg.text)}
                            title="Sao chép câu trả lời"
                          >
                            {copiedMsgIdx === index ? <Check size={14} /> : <Copy size={14} />}
                            <span>{copiedMsgIdx === index ? 'Đã chép' : 'Sao chép'}</span>
                          </button>

                          <button
                            type="button"
                            className="msg-action-btn report-export-btn"
                            onClick={() =>
                              exportLegalAdvisoryReport(
                                index > 0 ? messages[index - 1]?.text : '',
                                msg
                              )
                            }
                            title="Xuất Phiếu Tư vấn Pháp lý / Đơn trình báo chuẩn mẫu (In / PDF)"
                          >
                            <FileText size={14} />
                            <span>Xuất Phiếu Tư vấn</span>
                          </button>

                          {msg.symbolicData && (
                            <>
                              <button
                                type="button"
                                className="msg-action-chip graph-chip"
                                onClick={() => {
                                  setCurrentSymbolicData(msg.symbolicData);
                                  setShowSymbolicPanel(true);
                                  setActiveTab('graph');
                                  if (nodeCount > 0) setGraphMode('query');
                                }}
                              >
                                <Network size={13} />
                                <span>
                                  {nodeCount > 0
                                    ? `Xem Đồ thị 3D (${nodeCount} Nodes)`
                                    : 'Mở Đồ thị 3D'}
                                </span>
                              </button>

                              <button
                                type="button"
                                className="msg-action-chip rule-chip"
                                onClick={() => {
                                  setCurrentSymbolicData(msg.symbolicData);
                                  setShowSymbolicPanel(true);
                                  setActiveTab('rules');
                                }}
                              >
                                <GitBranch size={13} />
                                <span>Dấu vết Suy luận ({stepCount} bước)</span>
                              </button>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}

              <div ref={chatEndRef} />
            </div>
          )}
        </div>

        {/* Ô nhập câu hỏi nổi ở đáy phong cách ChatGPT */}
        <div className="chatgpt-composer-zone">
          <input
            ref={evidenceInputRef}
            type="file"
            accept=".png,.jpg,.jpeg,.webp,.bmp,.pdf,.docx,.txt,.md"
            style={{ display: 'none' }}
            onChange={handleEvidenceUpload}
          />
          <form
            className="chatgpt-composer-box"
            onSubmit={(e) => {
              e.preventDefault();
              sendMessage();
            }}
          >
            {evidenceAttachment && (
              <div className="evidence-attachment-banner">
                <div className="evidence-banner-left">
                  <Paperclip size={14} className="evidence-icon" />
                  <div className="evidence-info">
                    <span className="evidence-name">
                      Bằng chứng: <b>{evidenceAttachment.filename}</b> ({evidenceAttachment.char_count} ký tự OCR)
                    </span>
                    <span className="evidence-preview">
                      {evidenceAttachment.extracted_text.slice(0, 140)}...
                    </span>
                  </div>
                </div>
                <button
                  type="button"
                  className="evidence-remove-btn"
                  onClick={() => setEvidenceAttachment(null)}
                  title="Gỡ bằng chứng đính kèm"
                >
                  <X size={14} />
                </button>
              </div>
            )}
            <textarea
              ref={textareaRef}
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Hỏi bất kỳ quy định, mức xử phạt, hoặc đính kèm ảnh chụp bằng chứng / PDF..."
              disabled={isLoading}
              className="chatgpt-textarea"
            />
            <div className="composer-bottom-row">
              <div className="composer-tags">
                <button
                  type="button"
                  className={`composer-chip ${evidenceAttachment ? 'active' : ''}`}
                  onClick={() => evidenceInputRef.current?.click()}
                  disabled={isUploadingEvidence || isLoading}
                  title="Đính kèm ảnh chụp màn hình tin nhắn/bài đăng vi phạm hoặc hợp đồng PDF/DOCX để OCR tự động"
                >
                  {isUploadingEvidence ? <Loader2 size={13} className="spin-icon" /> : <Paperclip size={13} />}
                  <span>
                    {isUploadingEvidence
                      ? 'Đang OCR bằng chứng...'
                      : evidenceAttachment
                      ? 'Đã đính kèm Bằng chứng'
                      : 'Đính kèm Bằng chứng (Ảnh/PDF)'}
                  </span>
                </button>
                <button
                  type="button"
                  className={`composer-chip ${showSymbolicPanel && activeTab === 'graph' ? 'active' : ''}`}
                  onClick={() => {
                    setShowSymbolicPanel(true);
                    setActiveTab('graph');
                  }}
                >
                  <Network size={13} />
                  <span>Neo4j 3D Graph</span>
                </button>
                <button
                  type="button"
                  className={`composer-chip ${isComparisonMode ? 'active' : ''}`}
                  onClick={() => setIsComparisonMode(!isComparisonMode)}
                >
                  <Layers size={13} />
                  <span>Đối chứng A/B: {isComparisonMode ? 'Bật' : 'Tắt'}</span>
                </button>
              </div>

              <button
                type="submit"
                disabled={isLoading || (!input.trim() && !evidenceAttachment)}
                className="chatgpt-send-btn"
                title="Gửi câu hỏi (Enter)"
              >
                {isLoading ? <Loader2 size={16} className="spin-icon" /> : <Send size={15} />}
              </button>
            </div>
          </form>
        </div>
      </main>

      {/* ====================================================================
          3. KHUNG ĐỒ THỊ NEO4J 3D & LUỒNG SUY LUẬN SYMBOLIC (BÊN PHẢI / FULLSCREEN)
         ==================================================================== */}
      {showSymbolicPanel && (
        <aside className={`symbolic-panel ${isGraphFullscreen ? 'fullscreen-panel' : ''}`}>
          <div className="panel-header">
            <div className="panel-title-group">
              <Cpu size={18} className="panel-header-icon" />
              <div>
                <h3 className="panel-title">Không gian Đồ thị Neo4j 3D & Suy luận</h3>
                <span className="panel-sub">
                  Kết nối trực tiếp <code>bolt://localhost:7687</code> • Explainable AI
                </span>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '4px' }}>
              <button
                type="button"
                className="panel-close-btn"
                onClick={() => setIsGraphFullscreen(!isGraphFullscreen)}
                title={isGraphFullscreen ? 'Thu nhỏ' : 'Mở rộng toàn màn hình'}
              >
                {isGraphFullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
              </button>
              <button
                type="button"
                className="panel-close-btn"
                onClick={() => {
                  setIsGraphFullscreen(false);
                  setShowSymbolicPanel(false);
                }}
                title="Đóng bảng"
              >
                <X size={16} />
              </button>
            </div>
          </div>

          {/* 3 Tab điều hướng: Đồ thị 3D đặt lên đầu tiên */}
          <div className="panel-tabs">
            <button
              type="button"
              className={`panel-tab ${activeTab === 'graph' ? 'active' : ''}`}
              onClick={() => setActiveTab('graph')}
            >
              <Network size={14} />
              <span>Đồ thị Neo4j 3D</span>
            </button>
            <button
              type="button"
              className={`panel-tab ${activeTab === 'rules' ? 'active' : ''}`}
              onClick={() => setActiveTab('rules')}
            >
              <GitBranch size={14} />
              <span>Dấu vết Logic</span>
            </button>
            <button
              type="button"
              className={`panel-tab ${activeTab === 'sources' ? 'active' : ''}`}
              onClick={() => setActiveTab('sources')}
            >
              <BookOpen size={14} />
              <span>Trích dẫn Luật</span>
            </button>
          </div>

          <div className="panel-content">
            {/* TAB 1: ĐỒ THỊ TRI THỨC NEO4J 3D (LUÔN HIỂN THỊ DỮ LIỆU THẬT TỪ NEO4J) */}
            {activeTab === 'graph' && (
              <KnowledgeGraph3D
                nodes={displayedGraphNodes}
                edges={displayedGraphEdges}
                graphMode={graphMode}
                setGraphMode={setGraphMode}
                hasQueryGraph={hasQueryGraph}
                overviewDocs={overviewDocs}
                selectedDocCode={selectedDocCode}
                onSelectDocCode={handleSelectDocFilter}
                neo4jStats={neo4jStats}
                onOpenGuide={() => setShowNeo4jModal(true)}
                isFullscreen={isGraphFullscreen}
                onToggleFullscreen={() => setIsGraphFullscreen(!isGraphFullscreen)}
                isLoadingGraph={isLoadingGraph}
              />
            )}

            {/* TAB 2: DẤU VẾT LOGIC SYMBOLIC & BẢNG TÍNH MỨC PHẠT */}
            {activeTab === 'rules' && (
              !activeSymbolic ? (
                <div className="empty-state">
                  <Info size={32} className="empty-icon" />
                  <p>Hãy đặt một câu hỏi pháp lý để xem dấu vết suy luận tất định (Rule Trace).</p>
                  <small>
                    Trong lúc chờ, bạn có thể chuyển sang tab <b>Đồ thị Neo4j 3D</b> để xoay và khám phá
                    trực tiếp 35 văn bản luật trong Neo4j.
                  </small>
                </div>
              ) : (
                <div className="rules-view" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <div className="card-box">
                    <div className="card-box-title">
                      <CheckCircle2 size={14} className="icon-success" />
                      <span>Thực thể phát hiện (Symbolic Query Facts)</span>
                    </div>
                    <div className="facts-grid">
                      <div className="fact-item">
                        <span className="fact-label">Chủ thể áp dụng:</span>
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
                            {activeSymbolic.reasoning.facts.age} tuổi
                          </span>
                        </div>
                      )}
                      {activeSymbolic.reasoning?.facts?.article_refs?.length > 0 && (
                        <div className="fact-item">
                          <span className="fact-label">Điều luật truy vấn:</span>
                          <span className="fact-value">
                            Điều {activeSymbolic.reasoning.facts.article_refs.join(', ')}
                          </span>
                        </div>
                      )}
                      {activeSymbolic.reasoning?.facts?.doc_hints?.length > 0 && (
                        <div className="fact-item">
                          <span className="fact-label">Văn bản nhận diện:</span>
                          <span className="fact-value">
                            {activeSymbolic.reasoning.facts.doc_hints.join(', ')}
                          </span>
                        </div>
                      )}
                      {activeSymbolic.reasoning?.facts?.invalid_docs?.length > 0 && (
                        <div className="fact-item">
                          <span className="fact-label">Cảnh báo Guardrail:</span>
                          <span className="fact-value" style={{ color: '#dc2626' }}>
                            {activeSymbolic.reasoning.facts.invalid_docs.join(', ')} (Không tồn tại)
                          </span>
                        </div>
                      )}
                    </div>
                  </div>

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
                            {calc.sanctions?.length > 0 && (
                              <div className="calc-sanctions-box">
                                <b>🛠️ Biện pháp bổ sung / Khắc phục:</b>
                                {calc.sanctions.map((s, idx) => (
                                  <div key={idx}>• {s}</div>
                                ))}
                              </div>
                            )}
                            {calc.criminal_escalations?.length > 0 && (
                              <div className="calc-criminal-box">
                                <b>⚖️ Liên đới Trách nhiệm Hình sự (Multi-Hop 3 Tầng → BLHS 2015):</b>
                                {calc.criminal_escalations.map((ce, idx) => (
                                  <div key={idx} className="criminal-item">
                                    <div>• <b>{ce.title}</b></div>
                                    <div className="criminal-sub">Điều kiện: {ce.condition}</div>
                                    <div className="criminal-pen">Khung hình phạt: {ce.penalty}</div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Vũ khí 3: Bảng điều khiển Mô phỏng Tình huống Pháp lý (Interactive What-If Sandbox) */}
                  {activeSymbolic.reasoning?.penalty_calculations?.length > 0 && (
                    <WhatIfSandbox penaltyCalcs={activeSymbolic.reasoning.penalty_calculations} />
                  )}

                  <div className="card-box">
                    <div className="card-box-title">
                      <ShieldCheck size={14} className="icon-purple" />
                      <span>Các bước suy luận luật (Deterministic Rule Trace)</span>
                    </div>
                    {activeSymbolic.reasoning?.rule_steps?.length > 0 ? (
                      <div className="steps-timeline">
                        {activeSymbolic.reasoning.rule_steps.map((step, idx) => (
                          <div key={idx} className="step-item">
                            <div className="step-badge">{step.rule}</div>
                            <div className="step-detail">{step.detail}</div>
                            <div className="step-basis">Căn cứ: {step.basis}</div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <span className="muted-note">
                        Truy vấn quy định chung (không phát sinh phép chia khung phạt tiền).
                      </span>
                    )}
                  </div>
                </div>
              )
            )}

            {/* TAB 3: TRÍCH DẪN NGUỒN VECTOR DATABASE */}
            {activeTab === 'sources' && (
              <div className="sources-view" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div className="card-box-title">
                  <BookOpen size={14} className="icon-primary" />
                  <span>Đoạn trích Văn bản Luật từ PGVector</span>
                </div>
                {activeSymbolic?.sources?.length > 0 ? (
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
                  <div className="empty-state">
                    <BookOpen size={28} className="empty-icon" />
                    <p>Chưa có đoạn trích dẫn cho câu hỏi hiện tại.</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </aside>
      )}

      {/* Modal hướng dẫn kết nối phần mềm Neo4j Desktop */}
      <Neo4jConnectionModal
        isOpen={showNeo4jModal}
        onClose={() => setShowNeo4jModal(false)}
        stats={neo4jStats}
      />

      {/* Vũ khí 5: Modal Bảng Thực nghiệm Định lượng Trực tiếp */}
      <BenchmarkModal
        isOpen={showBenchmarkModal}
        onClose={() => setShowBenchmarkModal(false)}
        data={benchmarkData}
        isLoading={isLoadingBenchmark}
        onRunBenchmark={handleRunBenchmark}
      />
    </div>
  );
}

export default App;