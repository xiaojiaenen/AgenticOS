"""SVG structural templates for each of the 36 html-ppt layout types.

Each value is a self-contained ``<svg>`` snippet that the AI can copy-paste
and then replace placeholder content with real data.  Templates use
``var(--token)`` for colours so the token resolver can swap in actual values
at storage time.
"""

from __future__ import annotations

# Each template is a triple-quoted SVG string keyed by layout name.
# The AI receives these via _inject_svg_design_catalog().

SVG_LAYOUTS: dict[str, str] = {
    # ── Opening ────────────────────────────────────────────────────────
    "cover": """<!-- layout: cover | 开篇 | 居中大标题 + 副标题 + 标签 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <!-- 顶部装饰条 -->
  <rect x="0" y="0" width="1280" height="4" fill="var(--accent)"/>
  <g text-anchor="middle" font-family="var(--font-sans)" id="bg-layer">
        <g id="cover-header">
<text x="640" y="180" font-size="18" fill="var(--accent)" font-weight="600">KICKER · 分类标签</text>
    <text x="640" y="300" font-size="68" font-weight="800" fill="var(--text-1)" font-family="var(--font-display)">
      <tspan x="640" dy="0">主标题第一行</tspan>
      <tspan x="640" dy="82" fill="var(--accent)">高亮关键词</tspan>
      <tspan x="640" dy="82">主标题第三行</tspan>
    </text>
    <text x="640" y="480" font-size="22" fill="var(--text-2)">副标题或日期 · 演讲者姓名</text>
    <!-- 底部标签 -->
        
    </g>
<g id="cover-tagline">
<rect x="500" y="540" width="110" height="36" rx="18" fill="var(--accent)"/>
    <text x="555" y="564" font-size="14" fill="var(--bg)" font-weight="600">标签</text>
    <rect x="630" y="540" width="150" height="36" rx="18" fill="var(--surface)" stroke="var(--border)"/>
    <text x="705" y="564" font-size="14" fill="var(--text-2)">副标签</text>
  </g>
  <!-- 页脚 -->
      
    
<g id="cover-footer">

    </g>
</g>
  <!-- 页脚 -->
  <text x="80" y="680" font-size="12" fill="var(--text-3)" font-family="var(--font-sans)">公司名</text>
  <text x="1200" y="680" text-anchor="middle" font-size="12" fill="var(--text-3)" font-family="var(--font-sans)">1 / 10</text>
  <!-- notes: 开场白，150-300 字 -->
</svg>""",

    "toc": """<!-- layout: toc | 目录 | 2×3 网格目录（可保留编号或替换为图标） -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="70" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">目录</text>
  <text x="80" y="120" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">内容概览</text>
  <!-- 6 个目录卡片 2×3 网格 -->
  <g font-family="var(--font-sans)" id="bg-layer">
    
    <g id="toc-01">
<rect x="60" y="170" width="370" height="150" rx="8" fill="var(--surface)"/>
    <rect x="60" y="170" width="370" height="4" rx="2" fill="var(--accent)"/>
    <text x="100" y="240" font-size="48" font-weight="800" fill="var(--accent)">01</text>
    <text x="190" y="240" font-size="22" font-weight="600" fill="var(--text-1)">章节名称</text>
    <text x="100" y="280" font-size="14" fill="var(--text-2)">章节简要描述</text>

    
    </g>

    <g id="toc-02">
<rect x="455" y="170" width="370" height="150" rx="8" fill="var(--surface)"/>
    <rect x="455" y="170" width="370" height="4" rx="2" fill="var(--accent-2)"/>
    <text x="495" y="240" font-size="48" font-weight="800" fill="var(--accent-2)">02</text>
    <text x="585" y="240" font-size="22" font-weight="600" fill="var(--text-1)">章节名称</text>
    <text x="495" y="280" font-size="14" fill="var(--text-2)">章节简要描述</text>

    
    </g>

    <g id="toc-03">
<rect x="850" y="170" width="370" height="150" rx="12" fill="var(--surface)"/>
    <rect x="850" y="170" width="6" height="150" rx="3" fill="var(--accent-3)"/>
    <text x="890" y="240" font-size="48" font-weight="800" fill="var(--accent-3)">03</text>
    <text x="980" y="240" font-size="22" font-weight="600" fill="var(--text-1)">章节名称</text>
    <text x="890" y="280" font-size="14" fill="var(--text-2)">章节简要描述</text>

    
    </g>

    <g id="toc-04">
<rect x="60" y="350" width="370" height="150" rx="12" fill="var(--surface)"/>
    <rect x="60" y="350" width="6" height="150" rx="3" fill="var(--good)"/>
    <text x="100" y="420" font-size="48" font-weight="800" fill="var(--good)">04</text>
    <text x="190" y="420" font-size="22" font-weight="600" fill="var(--text-1)">章节名称</text>
    <text x="100" y="460" font-size="14" fill="var(--text-2)">章节简要描述</text>

    
    </g>

    <g id="toc-05">
<rect x="455" y="350" width="370" height="150" rx="12" fill="var(--surface)"/>
    <rect x="455" y="350" width="6" height="150" rx="3" fill="var(--warn)"/>
    <text x="495" y="420" font-size="48" font-weight="800" fill="var(--warn)">05</text>
    <text x="585" y="420" font-size="22" font-weight="600" fill="var(--text-1)">章节名称</text>
    <text x="495" y="460" font-size="14" fill="var(--text-2)">章节简要描述</text>

    
    </g>

    <g id="toc-06">
<rect x="850" y="350" width="370" height="150" rx="12" fill="var(--surface)"/>
    <rect x="850" y="350" width="6" height="150" rx="3" fill="var(--bad)"/>
    <text x="890" y="420" font-size="48" font-weight="800" fill="var(--bad)">06</text>
    <text x="980" y="420" font-size="22" font-weight="600" fill="var(--text-1)">章节名称</text>
    <text x="890" y="460" font-size="14" fill="var(--text-2)">章节简要描述</text>
  
    </g>
</g>
</svg>""",

    "section-divider": """<!-- layout: section-divider | 章节分隔 | 大号编号 + 章节标题 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg-soft)"/>
  <!-- 顶部装饰条 + 右侧装饰几何 -->
  <rect x="0" y="0" width="1280" height="4" fill="var(--accent)"/>
  <circle cx="1100" cy="360" r="220" fill="var(--accent)" opacity="0.04"/>
  <circle cx="1100" cy="360" r="140" fill="var(--accent)" opacity="0.06"/>
  <g font-family="var(--font-sans)" id="bg-layer">
    <text x="120" y="260" font-size="140" font-weight="900" fill="var(--accent)" opacity="0.12">03</text>
    <text x="120" y="310" font-size="20" fill="var(--accent)" font-weight="600" letter-spacing="4">SECTION 03</text>
    <text x="120" y="380" font-size="48" font-weight="800" fill="var(--text-1)">章节标题</text>
    <text x="120" y="440" font-size="20" fill="var(--text-2)">本章节的核心问题或主题引导语</text>
  </g>
</svg>""",

    # ── Data ───────────────────────────────────────────────────────────
    "stat-highlight": """<!-- layout: stat-highlight | 数据突出 | 超大数字 + 说明 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <g text-anchor="middle" font-family="var(--font-sans)" id="bg-layer">
    <text x="640" y="140" font-size="18" fill="var(--accent)" font-weight="600">KICKER</text>
    <text x="640" y="240" font-size="120" font-weight="900" fill="var(--text-1)" font-family="var(--font-display)">+42%</text>
    <text x="640" y="320" font-size="28" fill="var(--text-1)" font-weight="600">核心指标标题</text>
    <text x="640" y="380" font-size="16" fill="var(--text-2)">对比周期：2024 Q3 vs 2025 Q3</text>
    <!-- 三个支撑数据点 -->
    
    <g id="stat-support-1">
<rect x="240" y="450" width="220" height="80" rx="12" fill="var(--surface)"/>
    <text x="350" y="485" font-size="32" font-weight="800" fill="var(--accent)">2.4M</text>
    <text x="350" y="510" font-size="12" fill="var(--text-2)">月活用户</text>
    
    </g>

    <g id="stat-support-2">
<rect x="530" y="450" width="220" height="80" rx="12" fill="var(--surface)"/>
    <text x="640" y="485" font-size="32" font-weight="800" fill="var(--accent-2)">$12.8M</text>
    <text x="640" y="510" font-size="12" fill="var(--text-2)">营收</text>
    
    </g>

    <g id="stat-support-3">
<rect x="820" y="450" width="220" height="80" rx="12" fill="var(--surface)"/>
    <text x="930" y="485" font-size="32" font-weight="800" fill="var(--good)">78</text>
    <text x="930" y="510" font-size="12" fill="var(--text-2)">NPS 得分</text>
  
    </g>
</g>
</svg>""",

    "kpi-grid": """<!-- layout: kpi-grid | KPI 面板 | 2×2 指标卡片带涨跌 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">核心指标</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">Q3 关键数据</text>
  <g font-family="var(--font-sans)" id="bg-layer">
    
    <g id="kpi-1">
<!-- 卡片 1 -->
    <rect x="60" y="160" width="560" height="220" rx="16" fill="var(--surface)"/>
    <!-- 图标：先用 search_icons 搜索关键词，再填入 data-icon -->
    <use data-icon="chunk-filled/users" x="100" y="188" width="24" height="24" fill="var(--accent)"/>
    <text x="135" y="210" font-size="14" fill="var(--text-2)">月活跃用户 (MAU)</text>
    <text x="100" y="290" font-size="64" font-weight="800" fill="var(--text-1)">2.4M</text>
    <rect x="100" y="320" width="80" height="28" rx="14" fill="var(--good)" opacity="0.15"/>
    <text x="140" y="339" font-size="14" fill="var(--good)" font-weight="600">↑ 12.5%</text>
    <text x="200" y="339" font-size="13" fill="var(--text-3)">vs 上季度</text>
    
    </g>

    <g id="kpi-2">
<!-- 卡片 2 -->
    <rect x="660" y="160" width="560" height="220" rx="16" fill="var(--surface)"/>
    <use data-icon="chunk-filled/dollar" x="700" y="188" width="24" height="24" fill="var(--accent-2)"/>
    <text x="735" y="210" font-size="14" fill="var(--text-2)">总营收 (MRR)</text>
    <text x="700" y="290" font-size="64" font-weight="800" fill="var(--text-1)">$12.8M</text>
    <rect x="700" y="320" width="80" height="28" rx="14" fill="var(--good)" opacity="0.15"/>
    <text x="740" y="339" font-size="14" fill="var(--good)" font-weight="600">↑ 8.2%</text>
    <text x="800" y="339" font-size="13" fill="var(--text-3)">vs 上季度</text>
    
    </g>

    <g id="kpi-3">
<!-- 卡片 3 -->
    <rect x="60" y="420" width="560" height="220" rx="16" fill="var(--surface)"/>
    <use data-icon="chunk-filled/chart" x="100" y="448" width="24" height="24" fill="var(--bad)"/>
    <text x="135" y="470" font-size="14" fill="var(--text-2)">客户流失率</text>
    <text x="100" y="550" font-size="64" font-weight="800" fill="var(--text-1)">1.8%</text>
    <rect x="100" y="580" width="80" height="28" rx="14" fill="var(--good)" opacity="0.15"/>
    <text x="140" y="599" font-size="14" fill="var(--good)" font-weight="600">↓ 0.3%</text>
    <text x="200" y="599" font-size="13" fill="var(--text-3)">vs 上季度</text>
    
    </g>

    <g id="kpi-4">
<!-- 卡片 4 -->
    <rect x="660" y="420" width="560" height="220" rx="16" fill="var(--surface)"/>
    <use data-icon="chunk-filled/star" x="700" y="448" width="24" height="24" fill="var(--good)"/>
    <text x="735" y="470" font-size="14" fill="var(--text-2)">NPS 净推荐值</text>
    <text x="700" y="550" font-size="64" font-weight="800" fill="var(--text-1)">78</text>
    <rect x="700" y="580" width="80" height="28" rx="14" fill="var(--good)" opacity="0.15"/>
    <text x="740" y="599" font-size="14" fill="var(--good)" font-weight="600">↑ 5 分</text>
    <text x="800" y="599" font-size="13" fill="var(--text-3)">vs 上季度</text>
  
    </g>
</g>
</svg>""",

    "chart-bar": """<!-- layout: chart-bar | 柱状图 | 7 根柱子 + 标签 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">数据分析</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">月度营收趋势</text>
  <g font-family="var(--font-sans)" font-size="13" text-anchor="middle" id="bg-layer">
    <!-- Y 轴网格线 -->
    <line x1="100" y1="150" x2="100" y2="620" stroke="var(--border)"/>
    <line x1="100" y1="620" x2="1180" y2="620" stroke="var(--border)"/>
    <!-- 7 根柱子：前 6 根用 surface-2 作中性底色，最新/最高柱子用 accent 突出 -->
    <!-- 1月 -->
    <rect x="150" y="420" width="80" height="200" rx="4" fill="var(--surface-2)" stroke="var(--border)"/>
    <text x="190" y="650" fill="var(--text-2)">1月</text>
    <text x="190" y="405" fill="var(--text-2)" font-weight="600">2.1M</text>
    <!-- 2月 -->
    <rect x="280" y="380" width="80" height="240" rx="4" fill="var(--surface-2)" stroke="var(--border)"/>
    <text x="320" y="650" fill="var(--text-2)">2月</text>
    <text x="320" y="365" fill="var(--text-2)" font-weight="600">2.5M</text>
    <!-- 3月 -->
    <rect x="410" y="350" width="80" height="270" rx="4" fill="var(--surface-2)" stroke="var(--border)"/>
    <text x="450" y="650" fill="var(--text-2)">3月</text>
    <text x="450" y="335" fill="var(--text-2)" font-weight="600">2.8M</text>
    <!-- 4月 -->
    <rect x="540" y="310" width="80" height="310" rx="4" fill="var(--surface-2)" stroke="var(--border)"/>
    <text x="580" y="650" fill="var(--text-2)">4月</text>
    <text x="580" y="295" fill="var(--text-2)" font-weight="600">3.2M</text>
    <!-- 5月 -->
    <rect x="670" y="290" width="80" height="330" rx="4" fill="var(--surface-2)" stroke="var(--border)"/>
    <text x="710" y="650" fill="var(--text-2)">5月</text>
    <text x="710" y="275" fill="var(--text-2)" font-weight="600">3.4M</text>
    <!-- 6月 -->
    <rect x="800" y="240" width="80" height="380" rx="4" fill="var(--surface-2)" stroke="var(--border)"/>
    <text x="840" y="650" fill="var(--text-2)">6月</text>
    <text x="840" y="225" fill="var(--text-2)" font-weight="600">3.9M</text>
    <!-- 7月 ★ 最新高亮 -->
    <rect x="930" y="160" width="80" height="460" rx="4" fill="var(--accent)"/>
    <text x="970" y="650" fill="var(--text-2)">7月</text>
    <text x="970" y="145" fill="var(--accent)" font-weight="700">4.7M</text>
  </g>
</svg>""",

    "chart-line": """<!-- layout: chart-line | 折线图 | 双折线对比 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">趋势对比</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">营收 vs 用户增长</text>
  <g font-family="var(--font-sans)" font-size="12" text-anchor="middle" id="bg-layer">
    <line x1="100" y1="150" x2="100" y2="600" stroke="var(--border)"/>
    <line x1="100" y1="600" x2="1180" y2="600" stroke="var(--border)"/>
    <!-- 网格线 -->
    <line x1="246" y1="150" x2="246" y2="600" stroke="var(--border)" stroke-dasharray="4"/>
    <line x1="392" y1="150" x2="392" y2="600" stroke="var(--border)" stroke-dasharray="4"/>
    <line x1="538" y1="150" x2="538" y2="600" stroke="var(--border)" stroke-dasharray="4"/>
    <line x1="684" y1="150" x2="684" y2="600" stroke="var(--border)" stroke-dasharray="4"/>
    <line x1="830" y1="150" x2="830" y2="600" stroke="var(--border)" stroke-dasharray="4"/>
    <line x1="976" y1="150" x2="976" y2="600" stroke="var(--border)" stroke-dasharray="4"/>
    <line x1="1122" y1="150" x2="1122" y2="600" stroke="var(--border)" stroke-dasharray="4"/>
    <!-- 折线 1（蓝色） -->
    <polyline fill="none" stroke="var(--accent)" stroke-width="3"
      points="246,480 392,430 538,380 684,350 830,310 976,260 1122,200"/>
    <circle cx="246" cy="480" r="5" fill="var(--accent)"/><text x="246" y="470" fill="var(--accent)" font-weight="600">2.1M</text>
    <circle cx="392" cy="430" r="5" fill="var(--accent)"/><text x="392" y="420" fill="var(--accent)" font-weight="600">2.5M</text>
    <circle cx="538" cy="380" r="5" fill="var(--accent)"/><text x="538" y="370" fill="var(--accent)" font-weight="600">2.8M</text>
    <circle cx="684" cy="350" r="5" fill="var(--accent)"/><text x="684" y="340" fill="var(--accent)" font-weight="600">3.2M</text>
    <circle cx="830" cy="310" r="5" fill="var(--accent)"/><text x="830" y="300" fill="var(--accent)" font-weight="600">3.4M</text>
    <circle cx="976" cy="260" r="5" fill="var(--accent)"/><text x="976" y="250" fill="var(--accent)" font-weight="600">3.9M</text>
    <circle cx="1122" cy="200" r="5" fill="var(--accent)"/><text x="1122" y="190" fill="var(--accent)" font-weight="600">4.7M</text>
    <!-- 折线 2（绿色，虚线） -->
    <polyline fill="none" stroke="var(--good)" stroke-width="3" stroke-dasharray="8,4"
      points="246,400 392,370 538,440 684,420 830,370 976,340 1122,330"/>
    <circle cx="246" cy="400" r="5" fill="var(--good)"/><text x="246" y="640" fill="var(--good)" font-weight="600">850K</text>
    <circle cx="392" cy="370" r="5" fill="var(--good)"/><text x="392" y="640" fill="var(--good)" font-weight="600">920K</text>
    <circle cx="538" cy="440" r="5" fill="var(--good)"/><text x="538" y="640" fill="var(--good)" font-weight="600">880K</text>
    <circle cx="684" cy="420" r="5" fill="var(--good)"/><text x="684" y="640" fill="var(--good)" font-weight="600">950K</text>
    <circle cx="830" cy="370" r="5" fill="var(--good)"/><text x="830" y="640" fill="var(--good)" font-weight="600">1.0M</text>
    <circle cx="976" cy="340" r="5" fill="var(--good)"/><text x="976" y="640" fill="var(--good)" font-weight="600">1.1M</text>
    <circle cx="1122" cy="330" r="5" fill="var(--good)"/><text x="1122" y="640" fill="var(--good)" font-weight="600">1.2M</text>
    <!-- 图例 -->
    <rect x="100" y="660" width="12" height="12" rx="2" fill="var(--accent)"/>
    <text x="120" y="670" text-anchor="start" font-size="13" fill="var(--text-2)">营收</text>
    <rect x="200" y="660" width="12" height="12" rx="2" fill="var(--good)"/>
    <text x="220" y="670" text-anchor="start" font-size="13" fill="var(--text-2)">新增用户</text>
    <!-- X 轴标签 -->
    <text x="246" y="620" fill="var(--text-2)">1月</text>
    <text x="392" y="620" fill="var(--text-2)">2月</text>
    <text x="538" y="620" fill="var(--text-2)">3月</text>
    <text x="684" y="620" fill="var(--text-2)">4月</text>
    <text x="830" y="620" fill="var(--text-2)">5月</text>
    <text x="976" y="620" fill="var(--text-2)">6月</text>
    <text x="1122" y="620" fill="var(--text-2)">7月</text>
  </g>
</svg>""",

    "chart-pie": """<!-- layout: chart-pie | 饼图 | 5 块扇形 + 图例 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">构成分析</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">营收来源分布</text>
  <g font-family="var(--font-sans)" text-anchor="middle" id="bg-layer">
    <!-- 饼图扇形：5 块，从 12 点方向顺时针，用 SVG path A 命令绘制 -->
    <!-- 45%: 0°→162°, 25%: 162°→252°, 15%: 252°→306°, 10%: 306°→342°, 5%: 342°→360° -->
    <path d="M 480 420 L 480.0 240.0 A 180 180 0 0 1 535.6 591.2 Z" fill="var(--accent)"/>
    <path d="M 480 420 L 535.6 591.2 A 180 180 0 0 1 308.8 475.6 Z" fill="var(--accent-2)"/>
    <path d="M 480 420 L 308.8 475.6 A 180 180 0 0 1 334.4 314.2 Z" fill="var(--good)"/>
    <path d="M 480 420 L 334.4 314.2 A 180 180 0 0 1 424.4 248.8 Z" fill="var(--warn)"/>
    <path d="M 480 420 L 424.4 248.8 A 180 180 0 0 1 480.0 240.0 Z" fill="var(--bad)"/>
    <!-- 中心圆（环形图效果） -->
    <circle cx="480" cy="420" r="80" fill="var(--bg)"/>
    <text x="480" y="420" font-size="16" fill="var(--text-2)">总营收</text>
    <text x="480" y="442" font-size="24" font-weight="700" fill="var(--text-1)">¥1,200万</text>
    <!-- 图例 -->
    <rect x="750" y="280" width="14" height="14" rx="3" fill="var(--accent)"/>
    <text x="775" y="292" text-anchor="start" font-size="14" fill="var(--text-1)">企业订阅 45%</text>
    <rect x="750" y="320" width="14" height="14" rx="3" fill="var(--accent-2)"/>
    <text x="775" y="332" text-anchor="start" font-size="14" fill="var(--text-1)">API 调用 25%</text>
    <rect x="750" y="360" width="14" height="14" rx="3" fill="var(--good)"/>
    <text x="775" y="372" text-anchor="start" font-size="14" fill="var(--text-1)">咨询服务 15%</text>
    <rect x="750" y="400" width="14" height="14" rx="3" fill="var(--warn)"/>
    <text x="775" y="412" text-anchor="start" font-size="14" fill="var(--text-1)">培训 10%</text>
    <rect x="750" y="440" width="14" height="14" rx="3" fill="var(--bad)"/>
    <text x="775" y="452" text-anchor="start" font-size="14" fill="var(--text-1)">其他 5%</text>
  </g>
</svg>""",

    "chart-radar": """<!-- layout: chart-radar | 雷达图 | 5 维度评估 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">能力评估</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">五维度雷达图</text>
  <g font-family="var(--font-sans)" text-anchor="middle" id="bg-layer">
    <!-- 5 条轴线（从中心到顶点） -->
    <!-- 中心: (640, 390), 半径: 180 -->
    <!-- 顶点角度（12 点方向起顺时针）: 技术=0°, 产品=72°, 运营=144°, 商业=216°, 组织=288° -->
    <line x1="640" y1="390" x2="640" y2="210" stroke="var(--border)" stroke-width="1"/>
    <line x1="640" y1="390" x2="811.2" y2="333.9" stroke="var(--border)" stroke-width="1"/>
    <line x1="640" y1="390" x2="745.6" y2="556.2" stroke="var(--border)" stroke-width="1"/>
    <line x1="640" y1="390" x2="534.4" y2="556.2" stroke="var(--border)" stroke-width="1"/>
    <line x1="640" y1="390" x2="468.8" y2="333.9" stroke="var(--border)" stroke-width="1"/>
    <!-- 背景五边形网格（40%, 60%, 80%） -->
    <polygon points="640,318 708.5,367.6 682.2,456.5 597.8,456.5 571.5,367.6" fill="none" stroke="var(--border)" stroke-dasharray="4,4"/>
    <polygon points="640,282 742.7,356.9 703.4,489.7 576.6,489.7 537.3,356.9" fill="none" stroke="var(--border)"/>
    <!-- 数据五边形（示例：技术 85%, 产品 72%, 运营 60%, 商业 55%, 组织 80%） -->
    <polygon points="640,237 767.6,349.5 717.5,536.0 574.0,536.0 512.4,349.5" fill="var(--accent)" fill-opacity="0.15" stroke="var(--accent)" stroke-width="2.5"/>
    <!-- 数据点 -->
    <circle cx="640" cy="237" r="5" fill="var(--accent)"/><text x="640" y="225" font-size="13" fill="var(--accent)" font-weight="600">85%</text>
    <circle cx="767.6" cy="349.5" r="5" fill="var(--accent)"/><text x="790" y="345" font-size="13" fill="var(--accent)" font-weight="600">72%</text>
    <circle cx="717.5" cy="536.0" r="5" fill="var(--accent)"/><text x="740" y="545" font-size="13" fill="var(--accent)" font-weight="600">60%</text>
    <circle cx="574.0" cy="536.0" r="5" fill="var(--accent)"/><text x="540" y="545" font-size="13" fill="var(--accent)" font-weight="600">55%</text>
    <circle cx="512.4" cy="349.5" r="5" fill="var(--accent)"/><text x="490" y="345" font-size="13" fill="var(--accent)" font-weight="600">80%</text>
    <!-- 维度标签 -->
    <text x="640" y="195" font-size="16" font-weight="600" fill="var(--text-1)">技术</text>
    <text x="835" y="330" font-size="16" font-weight="600" fill="var(--text-1)">产品</text>
    <text x="755" y="585" font-size="16" font-weight="600" fill="var(--text-1)">运营</text>
    <text x="525" y="585" font-size="16" font-weight="600" fill="var(--text-1)">商业</text>
    <text x="430" y="330" font-size="16" font-weight="600" fill="var(--text-1)">组织</text>
  </g>
</svg>""",

    "table": """<!-- layout: table | 数据表格 | 6 行 × 4 列 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">数据明细</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">Top 5 客户</text>
  <g font-family="var(--font-sans)" id="bg-layer">
    <!-- 表头 -->
    <rect x="60" y="150" width="1160" height="44" rx="8" fill="var(--accent)"/>
    <text x="100" y="177" font-size="14" font-weight="700" fill="var(--bg)">客户名称</text>
    <text x="400" y="177" font-size="14" font-weight="700" fill="var(--bg)">行业</text>
    <text x="620" y="177" font-size="14" font-weight="700" fill="var(--bg)">合同金额</text>
    <text x="900" y="177" font-size="14" font-weight="700" fill="var(--bg)">状态</text>
    <!-- 行 1 -->
    <rect x="60" y="198" width="1160" height="48" rx="4" fill="var(--surface)"/>
    <line x1="60" y1="246" x2="1220" y2="246" stroke="var(--border)"/>
    <text x="100" y="228" font-size="15" fill="var(--text-1)">某科技有限公司</text>
    <text x="400" y="228" font-size="15" fill="var(--text-2)">电商</text>
    <text x="620" y="228" font-size="15" fill="var(--text-1)" font-weight="600">$2,400,000</text>
    <rect x="900" y="213" width="64" height="28" rx="14" fill="var(--good)" opacity="0.12"/>
    <text x="932" y="232" font-size="13" fill="var(--good)" font-weight="600">已完成</text>
    <!-- 行 2 -->
    <rect x="60" y="250" width="1160" height="48" rx="4" fill="var(--bg)"/>
    <line x1="60" y1="298" x2="1220" y2="298" stroke="var(--border)"/>
    <text x="100" y="280" font-size="15" fill="var(--text-1)">某金融集团</text>
    <text x="400" y="280" font-size="15" fill="var(--text-2)">金融</text>
    <text x="620" y="280" font-size="15" fill="var(--text-1)" font-weight="600">$1,850,000</text>
    <rect x="900" y="265" width="64" height="28" rx="14" fill="var(--warn)" opacity="0.12"/>
    <text x="932" y="284" font-size="13" fill="var(--warn)" font-weight="600">执行中</text>
    <!-- 行 3 -->
    <rect x="60" y="302" width="1160" height="48" rx="4" fill="var(--surface)"/>
    <line x1="60" y1="350" x2="1220" y2="350" stroke="var(--border)"/>
    <text x="100" y="332" font-size="15" fill="var(--text-1)">某制造企业</text>
    <text x="400" y="332" font-size="15" fill="var(--text-2)">制造业</text>
    <text x="620" y="332" font-size="15" fill="var(--text-1)" font-weight="600">$1,200,000</text>
    <rect x="900" y="317" width="64" height="28" rx="14" fill="var(--warn)" opacity="0.12"/>
    <text x="932" y="336" font-size="13" fill="var(--warn)" font-weight="600">执行中</text>
    <!-- 行 4 -->
    <rect x="60" y="354" width="1160" height="48" rx="4" fill="var(--bg)"/>
    <line x1="60" y1="402" x2="1220" y2="402" stroke="var(--border)"/>
    <text x="100" y="384" font-size="15" fill="var(--text-1)">某医疗公司</text>
    <text x="400" y="384" font-size="15" fill="var(--text-2)">医疗</text>
    <text x="620" y="384" font-size="15" fill="var(--text-1)" font-weight="600">$980,000</text>
    <rect x="900" y="369" width="64" height="28" rx="14" fill="var(--good)" opacity="0.12"/>
    <text x="932" y="388" font-size="13" fill="var(--good)" font-weight="600">已完成</text>
  </g>
</svg>""",

    # ── Text ────────────────────────────────────────────────────────────
    "bullets": """<!-- layout: bullets | 要点列表 | 图标 + 标题 + 描述 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">要点</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">核心观点</text>
  <g font-family="var(--font-sans)" id="bg-layer">
    
    <g id="bullet-1">
<rect x="80" y="170" width="1120" height="120" rx="8" fill="var(--surface)"/>
    <!-- 图标：先用 search_icons 工具搜索关键词，再填入 data-icon -->
    <use data-icon="chunk-filled/rocket" x="120" y="195" width="28" height="28" fill="var(--accent)"/>
    <text x="165" y="220" font-size="22" font-weight="600" fill="var(--text-1)">要点标题 1</text>
    <text x="165" y="255" font-size="15" fill="var(--text-2)">展开说明：可以写 1-2 行具体细节、数据支撑或案例引用</text>
    
    </g>

    <g id="bullet-2">
<rect x="80" y="310" width="1120" height="120" rx="8" fill="var(--surface)"/>
    <use data-icon="chunk-filled/star" x="120" y="335" width="28" height="28" fill="var(--accent-2)"/>
    <text x="165" y="360" font-size="22" font-weight="600" fill="var(--text-1)">要点标题 2</text>
    <text x="165" y="395" font-size="15" fill="var(--text-2)">展开说明：可以写 1-2 行具体细节、数据支撑或案例引用</text>
    
    </g>

    <g id="bullet-3">
<rect x="80" y="450" width="1120" height="120" rx="8" fill="var(--surface)"/>
    <use data-icon="chunk-filled/check-circle" x="120" y="475" width="28" height="28" fill="var(--good)"/>
    <text x="165" y="500" font-size="22" font-weight="600" fill="var(--text-1)">要点标题 3</text>
    <text x="165" y="535" font-size="15" fill="var(--text-2)">展开说明：可以写 1-2 行具体细节、数据支撑或案例引用</text>
  
    </g>
</g>
</svg>""",

    "two-column": """<!-- layout: two-column | 双栏对比 | 左概念右示例 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">对比分析</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">方案 A vs 方案 B</text>
  <g font-family="var(--font-sans)" id="bg-layer">
    <!-- 左栏 -->
        <g id="column-left">
<rect x="60" y="160" width="560" height="480" rx="16" fill="var(--surface)"/>
    <rect x="60" y="160" width="560" height="6" rx="3" fill="var(--accent)"/>
    <text x="340" y="210" text-anchor="middle" font-size="24" font-weight="700" fill="var(--accent)">方案 A</text>
    <line x1="100" y1="230" x2="580" y2="230" stroke="var(--border)"/>
    <text x="100" y="270" font-size="15" fill="var(--text-1)">核心优势：...</text>
    <text x="100" y="310" font-size="15" fill="var(--text-1)">关键指标：...</text>
    <text x="100" y="350" font-size="15" fill="var(--text-1)">风险等级：...</text>
    <text x="100" y="390" font-size="15" fill="var(--text-1)">实施周期：...</text>
    <text x="100" y="430" font-size="15" fill="var(--text-1)">团队规模：...</text>
    <!-- 右栏 -->
        
    </g>
<g id="column-right">
<rect x="660" y="160" width="560" height="480" rx="16" fill="var(--surface)"/>
    <rect x="660" y="160" width="560" height="6" rx="3" fill="var(--accent-2)"/>
    <text x="940" y="210" text-anchor="middle" font-size="24" font-weight="700" fill="var(--accent-2)">方案 B</text>
    <line x1="700" y1="230" x2="1180" y2="230" stroke="var(--border)"/>
    <text x="700" y="270" font-size="15" fill="var(--text-1)">核心优势：...</text>
    <text x="700" y="310" font-size="15" fill="var(--text-1)">关键指标：...</text>
    <text x="700" y="350" font-size="15" fill="var(--text-1)">风险等级：...</text>
    <text x="700" y="390" font-size="15" fill="var(--text-1)">实施周期：...</text>
    <text x="700" y="430" font-size="15" fill="var(--text-1)">团队规模：...</text>
  
    </g>
</g>
</svg>""",

    "three-column": """<!-- layout: three-column | 三栏展示 | 图标 + 标题 + 描述 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">三大支柱</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">战略方向</text>
  <g font-family="var(--font-sans)" text-anchor="middle" id="bg-layer">
    
    <g id="column-1">
<rect x="60" y="170" width="370" height="420" rx="16" fill="var(--surface)"/>
    <!-- 图标：先用 search_icons 搜索，再替换 data-icon 值 -->
    <use data-icon="chunk-filled/cube" x="210" y="195" width="48" height="48" fill="var(--accent)"/>
    <text x="245" y="300" font-size="22" font-weight="700" fill="var(--text-1)">产品创新</text>
    <text x="245" y="340" font-size="14" fill="var(--text-2)">三行以内的简要说明，概括这个方向的核心内容</text>
    
    </g>

    <g id="column-2">
<rect x="455" y="170" width="370" height="420" rx="16" fill="var(--surface)"/>
    <use data-icon="chunk-filled/globe" x="600" y="195" width="48" height="48" fill="var(--accent-2)"/>
    <text x="640" y="300" font-size="22" font-weight="700" fill="var(--text-1)">市场拓展</text>
    <text x="640" y="340" font-size="14" fill="var(--text-2)">三行以内的简要说明，概括这个方向的核心内容</text>
    
    </g>

    <g id="column-3">
<rect x="850" y="170" width="370" height="420" rx="16" fill="var(--surface)"/>
    <use data-icon="chunk-filled/lightning" x="1000" y="195" width="48" height="48" fill="var(--good)"/>
    <text x="1035" y="300" font-size="22" font-weight="700" fill="var(--text-1)">效能提升</text>
    <text x="1035" y="340" font-size="14" fill="var(--text-2)">三行以内的简要说明，概括这个方向的核心内容</text>
  
    </g>
</g>
</svg>""",

    "big-quote": """<!-- layout: big-quote | 引用金句 | 居中大字引用 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <rect x="0" y="0" width="1280" height="6" fill="var(--accent)"/>
  <g text-anchor="middle" font-family="var(--font-sans)" id="bg-layer">
        <g id="quote-text">
<text x="640" y="240" font-size="120" font-weight="900" fill="var(--accent)" opacity="0.12">"</text>
    <text x="640" y="340" font-size="32" fill="var(--text-1)" font-weight="600" font-family="var(--font-display)">
      <tspan x="640" dy="0">好的产品不是功能的堆砌，</tspan>
      <tspan x="640" dy="48">而是每一个决策背后的用户洞察。</tspan>
    </text>
        
    </g>
<g id="quote-author">
<line x1="540" y1="420" x2="740" y2="420" stroke="var(--accent)" stroke-width="2"/>
    <text x="640" y="470" font-size="18" fill="var(--accent)" font-weight="600">—— 史蒂夫·乔布斯</text>
    <text x="640" y="510" font-size="14" fill="var(--text-2)">Apple Inc. 联合创始人</text>
  
    </g>
</g>
</svg>""",

    # ── Comparison ──────────────────────────────────────────────────────
    "comparison": """<!-- layout: comparison | 对比 | 左右对比 + 中间 VS -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">对比分析</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">传统方案 vs 新方案</text>
  <g font-family="var(--font-sans)" text-anchor="middle" id="bg-layer">
        <g id="cmp-old">
<rect x="60" y="160" width="520" height="440" rx="16" fill="var(--surface)"/>
    <rect x="60" y="160" width="520" height="6" rx="3" fill="var(--bad)"/>
    <!-- 图标：先用 search_icons 搜索关键词，再填入 data-icon -->
    <use data-icon="chunk-filled/close" x="290" y="192" width="28" height="28" fill="var(--bad)"/>
    <text x="340" y="216" font-size="24" font-weight="700" fill="var(--bad)">传统方案</text>
    <text x="320" y="290" font-size="14" fill="var(--text-2)">劣势项 1</text>
    <text x="320" y="340" font-size="14" fill="var(--text-2)">劣势项 2</text>
    <text x="320" y="390" font-size="14" fill="var(--text-2)">劣势项 3</text>
    <text x="320" y="440" font-size="14" fill="var(--text-2)">劣势项 4</text>
        
    </g>
<g id="cmp-vs">
<circle cx="640" cy="380" r="36" fill="var(--surface)" stroke="var(--border)" stroke-width="3"/>
    <text x="640" y="388" font-size="18" font-weight="800" fill="var(--text-2)">VS</text>
        
    </g>
<g id="cmp-new">
<rect x="700" y="160" width="520" height="440" rx="16" fill="var(--surface)"/>
    <rect x="700" y="160" width="520" height="6" rx="3" fill="var(--good)"/>
    <use data-icon="chunk-filled/check" x="930" y="192" width="28" height="28" fill="var(--good)"/>
    <text x="980" y="216" font-size="24" font-weight="700" fill="var(--good)">新方案</text>
    <text x="960" y="290" font-size="14" fill="var(--text-2)">优势项 1</text>
    <text x="960" y="340" font-size="14" fill="var(--text-2)">优势项 2</text>
    <text x="960" y="390" font-size="14" fill="var(--text-2)">优势项 3</text>
    <text x="960" y="440" font-size="14" fill="var(--text-2)">优势项 4</text>
  
    </g>
</g>
</svg>""",

    "pros-cons": """<!-- layout: pros-cons | 优缺点 | 绿色优点 + 红色缺点 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">评估</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">方案优缺点</text>
  <g font-family="var(--font-sans)" id="bg-layer">
        <g id="pc-pros">
<rect x="60" y="160" width="560" height="460" rx="16" fill="var(--surface)"/>
    <!-- 图标：先用 search_icons 搜索关键词，再填入 data-icon -->
    <use data-icon="chunk-filled/check-circle" x="300" y="188" width="28" height="28" fill="var(--good)"/>
    <text x="345" y="210" font-size="24" font-weight="700" fill="var(--good)">优点 Pros</text>
    <line x1="100" y1="230" x2="580" y2="230" stroke="var(--good)" opacity="0.3"/>
    <circle cx="120" cy="280" r="6" fill="var(--good)"/>
    <text x="150" y="285" font-size="16" fill="var(--text-1)">优点项 1</text>
    <circle cx="120" cy="340" r="6" fill="var(--good)"/>
    <text x="150" y="345" font-size="16" fill="var(--text-1)">优点项 2</text>
    <circle cx="120" cy="400" r="6" fill="var(--good)"/>
    <text x="150" y="405" font-size="16" fill="var(--text-1)">优点项 3</text>
    <circle cx="120" cy="460" r="6" fill="var(--good)"/>
    <text x="150" y="465" font-size="16" fill="var(--text-1)">优点项 4</text>
        
    </g>
<g id="pc-cons">
<rect x="660" y="160" width="560" height="460" rx="16" fill="var(--surface)"/>
    <use data-icon="chunk-filled/close-circle" x="900" y="188" width="28" height="28" fill="var(--bad)"/>
    <text x="945" y="210" font-size="24" font-weight="700" fill="var(--bad)">缺点 Cons</text>
    <line x1="700" y1="230" x2="1180" y2="230" stroke="var(--bad)" opacity="0.3"/>
    <circle cx="720" cy="280" r="6" fill="var(--bad)"/>
    <text x="750" y="285" font-size="16" fill="var(--text-1)">缺点项 1</text>
    <circle cx="720" cy="340" r="6" fill="var(--bad)"/>
    <text x="750" y="345" font-size="16" fill="var(--text-1)">缺点项 2</text>
    <circle cx="720" cy="400" r="6" fill="var(--bad)"/>
    <text x="750" y="405" font-size="16" fill="var(--text-1)">缺点项 3</text>
    <circle cx="720" cy="460" r="6" fill="var(--bad)"/>
    <text x="750" y="465" font-size="16" fill="var(--text-1)">缺点项 4</text>
  
    </g>
</g>
</svg>""",

    "diff": """<!-- layout: diff | 代码差异 | +/- 对比视图 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">变更分析</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">代码变更 diff</text>
  <g font-family="var(--font-mono)" font-size="14" id="bg-layer">
    <rect x="60" y="150" width="1160" height="500" rx="12" fill="var(--surface)"/>
    <!-- 上下文 -->
    <text x="90" y="185" fill="var(--text-2)">  123  function processData(input) {</text>
    <!-- 删除行 -->
    <rect x="60" y="200" width="1160" height="22" fill="var(--bad)" opacity="0.08"/>
    <text x="90" y="216" fill="var(--bad)">- 124    const result = input.map(x =&gt; x * 2);</text>
    <!-- 新增行 -->
    <rect x="60" y="225" width="1160" height="22" fill="var(--good)" opacity="0.08"/>
    <text x="90" y="241" fill="var(--good)">+ 124    const result = input.map(x =&gt; x ** 2);</text>
    <!-- 上下文 -->
    <text x="90" y="275" fill="var(--text-2)">  125    return result.filter(Boolean);</text>
    <text x="90" y="310" fill="var(--text-2)">  126  }</text>
    <text x="90" y="360" fill="var(--text-2)">  127</text>
    <!-- 更多删除/新增 -->
    <rect x="60" y="380" width="1160" height="22" fill="var(--bad)" opacity="0.08"/>
    <text x="90" y="396" fill="var(--bad)">- 128  export default processData;</text>
    <rect x="60" y="405" width="1160" height="22" fill="var(--good)" opacity="0.08"/>
    <text x="90" y="421" fill="var(--good)">+ 128  export { processData as default };</text>
    <!-- 图例 -->
    <rect x="90" y="610" width="12" height="12" rx="2" fill="var(--bad)" opacity="0.15"/>
    <text x="110" y="621" font-family="var(--font-sans)" font-size="13" fill="var(--text-2)">删除</text>
    <rect x="180" y="610" width="12" height="12" rx="2" fill="var(--good)" opacity="0.15"/>
    <text x="200" y="621" font-family="var(--font-sans)" font-size="13" fill="var(--text-2)">新增</text>
  </g>
</svg>""",

    # ── Flow / Architecture ─────────────────────────────────────────────
    "flow-diagram": """<!-- layout: flow-diagram | 流程图 | 5 步骤水平管道 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">流程</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">数据处理管道</text>
  <g font-family="var(--font-sans)" text-anchor="middle" id="bg-layer">
    
    <g id="step-1">
<!-- 步骤 1 -->
    <rect x="60" y="260" width="200" height="100" rx="12" fill="var(--accent)"/>
    <!-- 图标：先用 search_icons 搜索关键词，再填入 data-icon -->
    <use data-icon="chunk-filled/download" x="150" y="288" width="22" height="22" fill="var(--bg)"/>
    <text x="160" y="318" font-size="18" font-weight="700" fill="var(--bg)">数据采集</text>
    <text x="160" y="344" font-size="12" fill="var(--bg)" opacity="0.8">采集原始数据</text>
    <!-- 箭头 1→2 -->
    <line x1="264" y1="310" x2="306" y2="310" stroke="var(--accent)" stroke-width="3"/>
    <polygon points="310,305 320,310 310,315" fill="var(--accent)"/>
    
    </g>

    <g id="step-2">
<!-- 步骤 2 -->
    <rect x="320" y="260" width="200" height="100" rx="12" fill="var(--accent-2)"/>
    <use data-icon="chunk-filled/filter" x="410" y="288" width="22" height="22" fill="var(--bg)"/>
    <text x="420" y="318" font-size="18" font-weight="700" fill="var(--bg)">数据清洗</text>
    <text x="420" y="344" font-size="12" fill="var(--bg)" opacity="0.8">去重 / 缺失处理</text>
    <!-- 箭头 2→3 -->
    <line x1="524" y1="310" x2="566" y2="310" stroke="var(--accent)" stroke-width="3"/>
    <polygon points="570,305 580,310 570,315" fill="var(--accent)"/>
    
    </g>

    <g id="step-3">
<!-- 步骤 3 -->
    <rect x="580" y="260" width="200" height="100" rx="12" fill="var(--surface)"/>
    <rect x="580" y="260" width="200" height="100" rx="12" fill="none" stroke="var(--accent-3)" stroke-width="2"/>
    <use data-icon="chunk-filled/code" x="670" y="288" width="22" height="22" fill="var(--accent-3)"/>
    <text x="680" y="305" font-size="18" font-weight="700" fill="var(--accent-3)">特征工程</text>
    <text x="680" y="335" font-size="12" fill="var(--text-2)">归一化 / 编码</text>
    <!-- 箭头 3→4 -->
    <line x1="784" y1="310" x2="826" y2="310" stroke="var(--accent)" stroke-width="3"/>
    <polygon points="830,305 840,310 830,315" fill="var(--accent)"/>
    
    </g>

    <g id="step-4">
<!-- 步骤 4 -->
    <rect x="840" y="260" width="200" height="100" rx="12" fill="var(--surface)"/>
    <rect x="840" y="260" width="200" height="100" rx="12" fill="none" stroke="var(--accent-3)" stroke-width="2"/>
    <use data-icon="chunk-filled/settings" x="930" y="288" width="22" height="22" fill="var(--accent-3)"/>
    <text x="940" y="305" font-size="18" font-weight="700" fill="var(--accent-3)">模型训练</text>
    <text x="940" y="335" font-size="12" fill="var(--text-2)">超参调优</text>
    <!-- 箭头 4→5 -->
    <line x1="1044" y1="310" x2="1086" y2="310" stroke="var(--accent)" stroke-width="3"/>
    <polygon points="1090,305 1100,310 1090,315" fill="var(--accent)"/>
    
    </g>

    <g id="step-5">
<!-- 步骤 5 -->
    <rect x="1100" y="260" width="120" height="100" rx="12" fill="var(--good)"/>
    <use data-icon="chunk-filled/rocket" x="1150" y="288" width="22" height="22" fill="var(--bg)"/>
    <text x="1160" y="318" font-size="18" font-weight="700" fill="var(--bg)">上线</text>
    <text x="1160" y="344" font-size="12" fill="var(--bg)" opacity="0.8">部署发布</text>
  
    </g>
</g>
</svg>""",

    "arch-diagram": """<!-- layout: arch-diagram | 架构图 | 3 层架构 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">架构</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">系统架构总览</text>
  <g font-family="var(--font-sans)" text-anchor="middle" id="bg-layer">
    <!-- 展示层 -->
    <rect x="80" y="160" width="1120" height="130" rx="12" fill="var(--accent)" opacity="0.08"/>
    <text x="640" y="190" font-size="18" font-weight="700" fill="var(--accent)">展示层 Presentation</text>
    <text x="640" y="230" font-size="14" fill="var(--text-2)">React / Vue · 响应式 UI · PWA 支持</text>
    <text x="640" y="260" font-size="14" fill="var(--text-2)">API Gateway → 请求路由 · 认证拦截 · 限流</text>
    <!-- 箭头 -->
    <polygon points="640,300 650,320 630,320" fill="var(--accent)"/>
    <!-- 业务层 -->
    <rect x="80" y="330" width="1120" height="130" rx="12" fill="var(--accent-2)" opacity="0.08"/>
    <text x="640" y="360" font-size="18" font-weight="700" fill="var(--accent-2)">业务层 Business Logic</text>
    <text x="640" y="400" font-size="14" fill="var(--text-2)">用户服务 · 订单服务 · 推荐引擎 · 通知中心</text>
    <text x="640" y="430" font-size="14" fill="var(--text-2)">消息队列 (Kafka/RabbitMQ) · 事件驱动</text>
    <!-- 箭头 -->
    <polygon points="640,470 650,490 630,490" fill="var(--accent)"/>
    <!-- 数据层 -->
    <rect x="80" y="500" width="1120" height="130" rx="12" fill="var(--good)" opacity="0.08"/>
    <text x="640" y="530" font-size="18" font-weight="700" fill="var(--good)">数据层 Data</text>
    <text x="640" y="570" font-size="14" fill="var(--text-2)">PostgreSQL (OLTP) · Redis (缓存) · Elasticsearch (搜索)</text>
    <text x="640" y="600" font-size="14" fill="var(--text-2)">S3 对象存储 · ClickHouse (OLAP 分析)</text>
  </g>
</svg>""",

    "process-steps": """<!-- layout: process-steps | 步骤 | 4 步编号卡片（图标+编号） -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">步骤</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">4 步实施流程</text>
  <g font-family="var(--font-sans)" text-anchor="middle" id="bg-layer">
    
    <g id="step-1">
<rect x="60" y="170" width="270" height="380" rx="16" fill="var(--surface)"/>
    <!-- 图标：先用 search_icons 搜索，再替换 data-icon -->
    <use data-icon="chunk-filled/search" x="175" y="195" width="40" height="40" fill="var(--accent)"/>
    <circle cx="195" cy="220" r="14" fill="var(--accent)"/>
    <text x="195" y="225" font-size="13" font-weight="800" fill="var(--bg)">1</text>
    <text x="195" y="290" font-size="20" font-weight="700" fill="var(--text-1)">调研分析</text>
    <text x="195" y="340" font-size="13" fill="var(--text-2)">需求收集和现状分析阶段</text>
    
    </g>

    <g id="step-2">
<rect x="350" y="170" width="270" height="380" rx="16" fill="var(--surface)"/>
    <use data-icon="chunk-filled/edit" x="465" y="195" width="40" height="40" fill="var(--accent-2)"/>
    <circle cx="485" cy="220" r="14" fill="var(--accent-2)"/>
    <text x="485" y="225" font-size="13" font-weight="800" fill="var(--bg)">2</text>
    <text x="485" y="290" font-size="20" font-weight="700" fill="var(--text-1)">方案设计</text>
    <text x="485" y="340" font-size="13" fill="var(--text-2)">架构设计和原型验证</text>
    
    </g>

    <g id="step-3">
<rect x="640" y="170" width="270" height="380" rx="16" fill="var(--surface)"/>
    <use data-icon="chunk-filled/code" x="755" y="195" width="40" height="40" fill="var(--accent-3)"/>
    <circle cx="775" cy="220" r="14" fill="var(--accent-3)"/>
    <text x="775" y="225" font-size="13" font-weight="800" fill="var(--bg)">3</text>
    <text x="775" y="290" font-size="20" font-weight="700" fill="var(--text-1)">迭代开发</text>
    <text x="775" y="340" font-size="13" fill="var(--text-2)">敏捷迭代和持续集成</text>
    
    </g>

    <g id="step-4">
<rect x="930" y="170" width="270" height="380" rx="16" fill="var(--surface)"/>
    <use data-icon="chunk-filled/rocket" x="1045" y="195" width="40" height="40" fill="var(--good)"/>
    <circle cx="1065" cy="220" r="14" fill="var(--good)"/>
    <text x="1065" y="225" font-size="13" font-weight="800" fill="var(--bg)">4</text>
    <text x="1065" y="290" font-size="20" font-weight="700" fill="var(--text-1)">上线运营</text>
    <text x="1065" y="340" font-size="13" fill="var(--text-2)">灰度发布和持续优化</text>
  
    </g>
</g>
</svg>""",

    "mindmap": """<!-- layout: mindmap | 思维导图 | 中心 + 4 分支 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">思维导图</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">产品规划全景</text>
  <g font-family="var(--font-sans)" text-anchor="middle" id="bg-layer">
    <!-- 中心节点 -->
    <circle cx="640" cy="380" r="70" fill="var(--accent)"/>
    <text x="640" y="375" font-size="20" font-weight="800" fill="var(--bg)">产品</text>
    <text x="640" y="400" font-size="14" fill="var(--bg)" opacity="0.8">规划</text>
    
    <g id="mm-branch-1">
<!-- 分支 1（左上） -->
    <line x1="600" y1="325" x2="350" y2="220" stroke="var(--accent)" stroke-width="2"/>
    <rect x="230" y="190" width="240" height="60" rx="10" fill="var(--surface)"/>
    <text x="350" y="215" font-size="16" font-weight="600" fill="var(--text-1)">用户体验</text>
    <text x="350" y="238" font-size="12" fill="var(--text-2)">可用性 · 无障碍 · 交互</text>
    
    </g>

    <g id="mm-branch-2">
<!-- 分支 2（右上） -->
    <line x1="690" y1="325" x2="930" y2="220" stroke="var(--accent-2)" stroke-width="2"/>
    <rect x="810" y="190" width="240" height="60" rx="10" fill="var(--surface)"/>
    <text x="930" y="215" font-size="16" font-weight="600" fill="var(--text-1)">技术架构</text>
    <text x="930" y="238" font-size="12" fill="var(--text-2)">微服务 · API · 数据库</text>
    
    </g>

    <g id="mm-branch-3">
<!-- 分支 3（左下） -->
    <line x1="600" y1="430" x2="350" y2="520" stroke="var(--good)" stroke-width="2"/>
    <rect x="230" y="490" width="240" height="60" rx="10" fill="var(--surface)"/>
    <text x="350" y="515" font-size="16" font-weight="600" fill="var(--text-1)">商业模型</text>
    <text x="350" y="538" font-size="12" fill="var(--text-2)">订阅 · 按量付费 · 增值</text>
    
    </g>

    <g id="mm-branch-4">
<!-- 分支 4（右下） -->
    <line x1="690" y1="430" x2="930" y2="520" stroke="var(--warn)" stroke-width="2"/>
    <rect x="810" y="490" width="240" height="60" rx="10" fill="var(--surface)"/>
    <text x="930" y="515" font-size="16" font-weight="600" fill="var(--text-1)">运营策略</text>
    <text x="930" y="538" font-size="12" fill="var(--text-2)">获客 · 留存 · 裂变</text>
  
    </g>
</g>
</svg>""",

    # ── Time / Planning ─────────────────────────────────────────────────
    "timeline": """<!-- layout: timeline | 时间线 | 5 事件水平时间轴 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">时间线</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">项目里程碑</text>
  <g font-family="var(--font-sans)" text-anchor="middle" id="bg-layer">
    <!-- 水平线 -->
    <line x1="100" y1="350" x2="1180" y2="350" stroke="var(--accent)" stroke-width="2"/>
    
    <g id="tl-node-1">
<!-- 节点 1 -->
    <circle cx="150" cy="350" r="12" fill="var(--accent)"/>
    <line x1="150" y1="338" x2="150" y2="280" stroke="var(--accent)" stroke-width="2"/>
    <text x="150" y="265" font-size="16" font-weight="700" fill="var(--text-1)">Q1 启动</text>
    <text x="150" y="250" font-size="12" fill="var(--text-2)">1月</text>
    <text x="150" y="400" font-size="13" fill="var(--text-2)">项目启动</text>
    <text x="150" y="420" font-size="13" fill="var(--text-2)">需求分析</text>
    
    </g>

    <g id="tl-node-2">
<!-- 节点 2 -->
    <circle cx="400" cy="350" r="12" fill="var(--accent)"/>
    <line x1="400" y1="362" x2="400" y2="420" stroke="var(--accent)" stroke-width="2"/>
    <text x="400" y="440" font-size="16" font-weight="700" fill="var(--text-1)">Q2 原型</text>
    <text x="400" y="455" font-size="12" fill="var(--text-2)">4月</text>
    <text x="400" y="250" font-size="13" fill="var(--text-2)">原型设计完成</text>
    
    </g>

    <g id="tl-node-3">
<!-- 节点 3 -->
    <circle cx="650" cy="350" r="12" fill="var(--accent-2)"/>
    <line x1="650" y1="338" x2="650" y2="280" stroke="var(--accent-2)" stroke-width="2"/>
    <text x="650" y="265" font-size="16" font-weight="700" fill="var(--text-1)">Q3 MVP</text>
    <text x="650" y="250" font-size="12" fill="var(--text-2)">7月</text>
    <text x="650" y="400" font-size="13" fill="var(--text-2)">MVP 发布</text>
    
    </g>

    <g id="tl-node-4">
<!-- 节点 4 -->
    <circle cx="900" cy="350" r="12" fill="var(--accent-2)"/>
    <line x1="900" y1="362" x2="900" y2="420" stroke="var(--accent-2)" stroke-width="2"/>
    <text x="900" y="440" font-size="16" font-weight="700" fill="var(--text-1)">Q4 正式</text>
    <text x="900" y="455" font-size="12" fill="var(--text-2)">10月</text>
    <text x="900" y="250" font-size="13" fill="var(--text-2)">正式版发布</text>
    
    </g>

    <g id="tl-node-5">
<!-- 节点 5 -->
    <circle cx="1150" cy="350" r="12" fill="var(--good)"/>
    <line x1="1150" y1="338" x2="1150" y2="280" stroke="var(--good)" stroke-width="2"/>
    <text x="1150" y="265" font-size="16" font-weight="700" fill="var(--text-1)">次年</text>
    <text x="1150" y="250" font-size="12" fill="var(--text-2)">持续</text>
  
    </g>
</g>
</svg>""",

    "roadmap": """<!-- layout: roadmap | 路线图 | NOW/NEXT/LATER/VISION 4 列 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">路线图</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">产品路线图</text>
  <g font-family="var(--font-sans)" text-anchor="middle" id="bg-layer">
    <!-- NOW -->
    
    <g id="rm-now">
<rect x="50" y="160" width="280" height="470" rx="12" fill="var(--accent)" opacity="0.06"/>
    
    </g>

    <g id="rm-next">
<rect x="50" y="160" width="280" height="6" rx="3" fill="var(--accent)"/>
    <text x="190" y="200" font-size="20" font-weight="800" fill="var(--accent)">NOW 今</text>
    <rect x="70" y="230" width="240" height="60" rx="8" fill="var(--surface)"/>
    <text x="190" y="255" font-size="14" font-weight="600" fill="var(--text-1)">核心功能 A</text>
    <text x="190" y="275" font-size="12" fill="var(--text-2)">Q1 交付</text>
    <rect x="70" y="310" width="240" height="60" rx="8" fill="var(--surface)"/>
    <text x="190" y="335" font-size="14" font-weight="600" fill="var(--text-1)">Bug 修复</text>
    <text x="190" y="355" font-size="12" fill="var(--text-2)">持续</text>
    <!-- NEXT -->
    
    </g>

    <g id="rm-later">
<rect x="345" y="160" width="280" height="470" rx="12" fill="var(--accent-2)" opacity="0.06"/>
    
    </g>

    <g id="rm-vision">
<rect x="345" y="160" width="280" height="6" rx="3" fill="var(--accent-2)"/>
    <text x="485" y="200" font-size="20" font-weight="800" fill="var(--accent-2)">NEXT 下</text>
    <rect x="365" y="230" width="240" height="60" rx="8" fill="var(--surface)"/>
    <text x="485" y="255" font-size="14" font-weight="600" fill="var(--text-1)">智能推荐</text>
    <text x="485" y="275" font-size="12" fill="var(--text-2)">Q2 开发</text>
    <rect x="365" y="310" width="240" height="60" rx="8" fill="var(--surface)"/>
    <text x="485" y="335" font-size="14" font-weight="600" fill="var(--text-1)">API 2.0</text>
    <text x="485" y="355" font-size="12" fill="var(--text-2)">Q2 设计</text>
    <!-- LATER -->
    
    </g>
<rect x="640" y="160" width="280" height="470" rx="12" fill="var(--accent-3)" opacity="0.06"/>
    <rect x="640" y="160" width="280" height="6" rx="3" fill="var(--accent-3)"/>
    <text x="780" y="200" font-size="20" font-weight="800" fill="var(--accent-3)">LATER 后</text>
    <rect x="660" y="230" width="240" height="60" rx="8" fill="var(--surface)"/>
    <text x="780" y="255" font-size="14" font-weight="600" fill="var(--text-1)">移动端 App</text>
    <text x="780" y="275" font-size="12" fill="var(--text-2)">H2 规划</text>
    <!-- VISION -->
    <rect x="935" y="160" width="280" height="470" rx="12" fill="var(--good)" opacity="0.06"/>
    <rect x="935" y="160" width="280" height="6" rx="3" fill="var(--good)"/>
    <text x="1075" y="200" font-size="20" font-weight="800" fill="var(--good)">VISION</text>
    <rect x="955" y="230" width="240" height="60" rx="8" fill="var(--surface)"/>
    <text x="1075" y="255" font-size="14" font-weight="600" fill="var(--text-1)">国际化</text>
    <text x="1075" y="275" font-size="12" fill="var(--text-2)">长期愿景</text>
    <rect x="955" y="310" width="240" height="60" rx="8" fill="var(--surface)"/>
    <text x="1075" y="335" font-size="14" font-weight="600" fill="var(--text-1)">AI 助理</text>
    <text x="1075" y="355" font-size="12" fill="var(--text-2)">前瞻探索</text>
  </g>
</svg>""",

    "gantt": """<!-- layout: gantt | 甘特图 | 4 条轨道的进度条 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">项目计划</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">甘特图</text>
  <g font-family="var(--font-sans)" id="bg-layer">
    <!-- 表头 -->
    <rect x="300" y="150" width="900" height="30" rx="4" fill="var(--surface)"/>
    <text x="340" y="170" font-size="11" fill="var(--text-2)">Q1</text><text x="430" y="170" font-size="11" fill="var(--text-2)">Q2</text>
    <text x="520" y="170" font-size="11" fill="var(--text-2)">Q3</text><text x="610" y="170" font-size="11" fill="var(--text-2)">Q4</text>
    <text x="700" y="170" font-size="11" fill="var(--text-2)">Q1</text><text x="790" y="170" font-size="11" fill="var(--text-2)">Q2</text>
    <text x="880" y="170" font-size="11" fill="var(--text-2)">Q3</text><text x="970" y="170" font-size="11" fill="var(--text-2)">Q4</text>
    <!-- 轨道 1 -->
    <text x="80" y="225" font-size="15" font-weight="600" fill="var(--text-1)">需求分析</text>
    <rect x="300" y="205" width="220" height="30" rx="6" fill="var(--accent)"/>
    <text x="410" y="225" text-anchor="middle" font-size="12" fill="var(--bg)">Q1-Q2</text>
    <!-- 轨道 2 -->
    <text x="80" y="285" font-size="15" font-weight="600" fill="var(--text-1)">UI 设计</text>
    <rect x="390" y="265" width="180" height="30" rx="6" fill="var(--accent-2)"/>
    <text x="480" y="285" text-anchor="middle" font-size="12" fill="var(--bg)">Q2</text>
    <!-- 轨道 3 -->
    <text x="80" y="345" font-size="15" font-weight="600" fill="var(--text-1)">后端开发</text>
    <rect x="480" y="325" width="300" height="30" rx="6" fill="var(--accent-3)"/>
    <text x="630" y="345" text-anchor="middle" font-size="12" fill="var(--bg)">Q2-Q3</text>
    <!-- 轨道 4 -->
    <text x="80" y="405" font-size="15" font-weight="600" fill="var(--text-1)">前端开发</text>
    <rect x="450" y="385" width="350" height="30" rx="6" fill="var(--accent-3)"/>
    <text x="625" y="405" text-anchor="middle" font-size="12" fill="var(--bg)">Q2-Q4</text>
    <!-- 轨道 5 -->
    <text x="80" y="465" font-size="15" font-weight="600" fill="var(--text-1)">测试上线</text>
    <rect x="750" y="445" width="250" height="30" rx="6" fill="var(--good)"/>
    <text x="875" y="465" text-anchor="middle" font-size="12" fill="var(--bg)">Q4</text>
  </g>
</svg>""",

    # ── Code ────────────────────────────────────────────────────────────
    "code": """<!-- layout: code | 代码块 | 语法高亮代码展示 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">代码示例</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">核心实现</text>
  <g font-family="var(--font-mono)" font-size="14" id="bg-layer">
    <!-- 代码框 -->
    <rect x="60" y="150" width="1160" height="470" rx="12" fill="var(--surface)"/>
    <!-- 窗口控制点 -->
    <circle cx="85" cy="185" r="7" fill="var(--bad)"/>
    <circle cx="110" cy="185" r="7" fill="var(--warn)"/>
    <circle cx="135" cy="185" r="7" fill="var(--good)"/>
    <!-- 代码行 -->
    <text x="90" y="230" fill="var(--text-3)"> 1</text>
    <text x="130" y="230" fill="var(--accent-2)">import</text>
    <text x="210" y="230" fill="var(--text-1)"> { useEffect, useState } </text>
    <text x="440" y="230" fill="var(--accent-2)">from</text>
    <text x="490" y="230" fill="var(--good)"> "react"</text>
    <text x="90" y="260" fill="var(--text-3)"> 2</text>
    <text x="90" y="290" fill="var(--text-3)"> 3</text>
    <text x="130" y="290" fill="var(--accent-2)">export function</text>
    <text x="300" y="290" fill="var(--warn)"> useData</text>
    <text x="400" y="290" fill="var(--text-1)">(url: </text>
    <text x="480" y="290" fill="var(--good)">string</text>
    <text x="550" y="290" fill="var(--text-1)">) {"{"}</text>
    <text x="90" y="320" fill="var(--text-3)"> 4</text>
    <text x="130" y="320" fill="var(--accent-2)">  const</text>
    <text x="220" y="320" fill="var(--text-1)"> [data, setData] = </text>
    <text x="430" y="320" fill="var(--warn)">useState</text>
    <text x="530" y="320" fill="var(--text-1)">(</text>
    <text x="550" y="320" fill="var(--accent-3)">null</text>
    <text x="600" y="320" fill="var(--text-1)">);</text>
    <text x="90" y="350" fill="var(--text-3)"> 5</text>
    <text x="90" y="380" fill="var(--text-3)"> 6</text>
    <text x="130" y="380" fill="var(--accent-2)">  useEffect</text>
    <text x="250" y="380" fill="var(--text-1)">(() => {"{"}</text>
    <text x="90" y="410" fill="var(--text-3)"> 7</text>
    <text x="160" y="410" fill="var(--accent-2)">    fetch</text>
    <text x="240" y="410" fill="var(--text-1)">(url)</text>
    <text x="90" y="440" fill="var(--text-3)"> 8</text>
    <text x="160" y="440" fill="var(--text-1)">      .then(r => r.json())</text>
    <text x="90" y="470" fill="var(--text-3)"> 9</text>
    <text x="160" y="470" fill="var(--text-1)">      .then(setData);</text>
    <text x="90" y="500" fill="var(--text-3)">10</text>
    <text x="130" y="500" fill="var(--text-1)">  }}, [url]);</text>
    <text x="90" y="530" fill="var(--text-3)">11</text>
    <text x="130" y="530" fill="var(--accent-2)">  return</text>
    <text x="220" y="530" fill="var(--text-1)"> data;</text>
    <text x="90" y="560" fill="var(--text-3)">12</text>
    <text x="130" y="560" fill="var(--text-1)">}</text>
  </g>
</svg>""",

    "terminal": """<!-- layout: terminal | 终端窗口 | 命令行录屏 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">操作演示</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">命令行部署</text>
  <g font-family="var(--font-mono)" font-size="14" id="bg-layer">
    <rect x="60" y="160" width="1160" height="440" rx="12" fill="#1a1b26"/>
    <circle cx="85" cy="195" r="7" fill="#ff5f57"/>
    <circle cx="110" cy="195" r="7" fill="#febc2e"/>
    <circle cx="135" cy="195" r="7" fill="#28c840"/>
    <!-- 命令 -->
    <text x="90" y="240" fill="#28c840">$</text>
    <text x="110" y="240" fill="#f8f8f2"> docker build -t myapp:latest .</text>
    <text x="90" y="275" fill="#8a8f9e">Building image...</text>
    <text x="90" y="305" fill="#8a8f9e">Step 1/8 : FROM node:20-alpine</text>
    <text x="90" y="335" fill="#8a8f9e">Step 2/8 : WORKDIR /app</text>
    <text x="90" y="365" fill="#8a8f9e">...</text>
    <text x="90" y="395" fill="#28c840">Successfully built abc123def456</text>
    <text x="90" y="425" fill="#28c840">$</text>
    <text x="110" y="425" fill="#f8f8f2"> docker push myapp:latest</text>
    <text x="90" y="460" fill="#8a8f9e">The push refers to repository [docker.io/myapp]</text>
    <text x="90" y="490" fill="#8a8f9e">abc123: Pushed</text>
    <text x="90" y="520" fill="#28c840">latest: digest: sha256:abc... size: 2415</text>
    <text x="90" y="560" fill="#28c840">$</text>
    <rect x="110" y="545" width="8" height="17" fill="#f8f8f2" opacity="0.8"/>
  </g>
</svg>""",

    # ── Visual ──────────────────────────────────────────────────────────
    "image-hero": """<!-- layout: image-hero | 大图背景 | 渐变蒙版文字叠加 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg-soft)"/>
  <!-- 模拟大图区域（用渐变 + pattern 表示） -->
  <rect x="0" y="0" width="1280" height="520" fill="var(--surface)"/>
  <text x="640" y="250" text-anchor="middle" font-family="var(--font-sans)" font-size="24" fill="var(--text-3)">[ 图片区域 ]</text>
  <!-- 底部蒙版 -->
  <rect x="0" y="380" width="1280" height="140" fill="var(--bg)" opacity="0.85"/>
  <!-- 叠加文字 -->
  <g text-anchor="middle" font-family="var(--font-sans)" id="bg-layer">
    <text x="640" y="450" font-size="44" font-weight="800" fill="var(--text-1)">视觉冲击标题</text>
    <text x="640" y="500" font-size="18" fill="var(--text-2)">副标题或描述文字</text>
  </g>
  <!-- 底部信息 -->
  <text x="80" y="620" font-size="14" fill="var(--text-2)" font-family="var(--font-sans)">图片来源 · 摄影师</text>
</svg>""",

    "image-grid": """<!-- layout: image-grid | 图片网格 | Bento 风格 7 宫格 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">产品展示</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">界面截图</text>
  <g font-family="var(--font-sans)" text-anchor="middle" id="bg-layer">
    <!-- Bento 网格布局 -->
    <!-- 大图（左） -->
    
    <g id="img-main">
<rect x="40" y="150" width="600" height="380" rx="16" fill="var(--surface)"/>
    <text x="340" y="350" font-size="18" fill="var(--text-2)">[ 主图 600×380 ]</text>
    <!-- 小图 1（右上） -->
    
    </g>

    <g id="img-thumb-1">
<rect x="660" y="150" width="280" height="180" rx="12" fill="var(--surface)"/>
    <text x="800" y="246" font-size="14" fill="var(--text-2)">[ 图 280×180 ]</text>
    <!-- 小图 2（中右） -->
    
    </g>

    <g id="img-thumb-2">
<rect x="960" y="150" width="280" height="180" rx="12" fill="var(--surface)"/>
    <text x="1100" y="246" font-size="14" fill="var(--text-2)">[ 图 280×180 ]</text>
    <!-- 中图（右下） -->
    
    </g>

    <g id="img-thumb-3">
<rect x="660" y="350" width="280" height="180" rx="12" fill="var(--surface)"/>
    <text x="800" y="446" font-size="14" fill="var(--text-2)">[ 图 280×180 ]</text>
    <!-- 小图 3（右下） -->
    <rect x="960" y="350" width="280" height="180" rx="12" fill="var(--surface)"/>
    <text x="1100" y="446" font-size="14" fill="var(--text-2)">[ 图 280×180 ]</text>
    <!-- 底部宽图 -->
    
    </g>

    <g id="img-banner">
<rect x="40" y="550" width="1200" height="120" rx="12" fill="var(--surface)"/>
    <text x="640" y="618" font-size="14" fill="var(--text-2)">[ 横幅 1200×120 ] — 时间线或对比图</text>
  
    </g>
</g>
</svg>""",

    # ── Closing ─────────────────────────────────────────────────────────
    "cta": """<!-- layout: cta | 行动号召 | 居中大字 CTA + 按钮 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg-soft)"/>
  <g text-anchor="middle" font-family="var(--font-sans)" id="bg-layer">
        <g id="cta-text">
<text x="640" y="220" font-size="52" font-weight="800" fill="var(--text-1)">
      <tspan x="640" dy="0">准备好了吗？</tspan>
    </text>
    <text x="640" y="310" font-size="22" fill="var(--text-2)">立即开始你的 14 天免费试用，无需信用卡</text>
        
    </g>
<g id="cta-buttons">
<!-- CTA 按钮 -->
    <rect x="440" y="370" width="240" height="56" rx="28" fill="var(--accent)"/>
    <text x="560" y="405" font-size="18" font-weight="700" fill="var(--bg)">免费试用</text>
    <rect x="700" y="370" width="140" height="56" rx="28" fill="var(--surface)" stroke="var(--border)"/>
    <text x="770" y="405" font-size="16" fill="var(--text-2)">了解更多</text>
    <text x="640" y="500" font-size="14" fill="var(--text-3)">已有 10,000+ 团队在使用</text>
        
    </g>
<g id="cta-logos">
<!-- 客户 logo 占位 -->
    <rect x="340" y="530" width="80" height="32" rx="6" fill="var(--surface)"/>
    <rect x="440" y="530" width="80" height="32" rx="6" fill="var(--surface)"/>
    <rect x="540" y="530" width="80" height="32" rx="6" fill="var(--surface)"/>
    <rect x="640" y="530" width="80" height="32" rx="6" fill="var(--surface)"/>
    <rect x="740" y="530" width="80" height="32" rx="6" fill="var(--surface)"/>
    <rect x="840" y="530" width="80" height="32" rx="6" fill="var(--surface)"/>
  
    </g>
</g>
</svg>""",

    "thanks": """<!-- layout: thanks | 致谢 | 居中感谢 + 联系方式 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <!-- 装饰色块 -->
  <rect x="0" y="0" width="1280" height="8" fill="var(--accent)"/>
  <circle cx="640" cy="320" r="80" fill="var(--accent)" opacity="0.08"/>
  <g text-anchor="middle" font-family="var(--font-sans)" id="bg-layer">
        <g id="thanks-text">
<text x="640" y="310" font-size="64" font-weight="900" fill="var(--text-1)" font-family="var(--font-display)">Thank You</text>
    <text x="640" y="360" font-size="22" fill="var(--text-2)">感谢您的宝贵时间</text>
    <line x1="520" y1="420" x2="760" y2="420" stroke="var(--accent)" stroke-width="2"/>
        
    </g>
<g id="thanks-contact">
<text x="640" y="470" font-size="16" fill="var(--text-1)">email@company.com</text>
    <text x="640" y="510" font-size="16" fill="var(--text-2)">twitter · github · linkedin</text>
    <text x="640" y="580" font-size="14" fill="var(--text-3)">© 2025 Company. All rights reserved.</text>
  
    </g>
</g>
</svg>""",

    # ── Asymmetric & Magazine (new archetypes) ──────────────────────────
    "asymmetric-spread": """<!-- layout: asymmetric-spread | 杂志跨页 | 左右不对称 + 文字叠图 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <g font-family="var(--font-sans)" id="bg-layer">
    <g id="asymmetric-layout">
      <!-- 左侧大图片区：占比 55% -->
      <rect x="0" y="0" width="700" height="720" fill="var(--surface)" rx="0"/>
      <rect x="0" y="0" width="700" height="400" fill="var(--bg-soft)" rx="0"/>
      <text x="350" y="200" text-anchor="middle" font-size="16" fill="var(--text-3)">[ 主视觉图片区域 700x400 ]</text>
      <!-- 左下方装饰图形 -->
      <circle cx="350" cy="560" r="120" fill="var(--accent)" opacity="0.06"/>
      <rect x="60" y="440" width="580" height="80" rx="8" fill="var(--surface-2)"/>
      <text x="350" y="488" text-anchor="middle" font-size="14" fill="var(--text-2)">说明文字 / 数据标注</text>
      <!-- 右侧文字区：偏移叠加 -->
      <rect x="620" y="100" width="600" height="140" fill="var(--bg)" rx="4" opacity="0.95"/>
      <text x="660" y="145" font-size="20" fill="var(--accent)" font-weight="600" font-family="var(--font-display)">CHAPTER 01</text>
      <text x="660" y="205" font-size="48" fill="var(--text-1)" font-weight="800" font-family="var(--font-display)">
        <tspan x="660" dy="0">大标题跨越</tspan>
        <tspan x="660" dy="60" fill="var(--accent)">左右不对称</tspan>
      </text>
      <!-- 右侧正文 -->
      <text x="660" y="300" font-size="18" fill="var(--text-2)">
        <tspan x="660" dy="0">正文内容从右侧开始，与左侧图片区域</tspan>
        <tspan x="660" dy="28">形成自然的视觉张力。标题可以跨越</tspan>
        <tspan x="660" dy="28">左右分界线，制造层次感。</tspan>
      </text>
      <!-- 右下角数据点 -->
      <rect x="660" y="420" width="180" height="100" rx="12" fill="var(--surface-2)"/>
      <text x="750" y="455" text-anchor="middle" font-size="36" font-weight="800" fill="var(--accent)">73%</text>
      <text x="750" y="488" text-anchor="middle" font-size="12" fill="var(--text-3)">关键指标</text>
      <rect x="870" y="420" width="180" height="100" rx="12" fill="var(--surface-2)"/>
      <text x="960" y="455" text-anchor="middle" font-size="36" font-weight="800" fill="var(--text-1)">2.4x</text>
      <text x="960" y="488" text-anchor="middle" font-size="12" fill="var(--text-3)">同比增长</text>
      <!-- 底部装饰线 -->
      <rect x="660" y="640" width="540" height="3" fill="var(--accent)" opacity="0.3"/>
      <text x="660" y="680" font-size="13" fill="var(--text-3)">数据来源：2026 Q3 内部统计 · 基准年 2025</text>
    </g>
  </g>
</svg>""",

    "overlap-cards": """<!-- layout: overlap-cards | 叠层卡片 | 卡片故意重叠 + 偏移阴影 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <defs>
    <filter id="cardShadow" x="-10%" y="-10%" width="130%" height="130%">
      <feDropShadow dx="0" dy="6" stdDeviation="12" flood-color="#000" flood-opacity="0.10"/>
    </filter>
  </defs>
  <g font-family="var(--font-sans)" id="bg-layer">
    <g id="overlap-cards-layout">
      <!-- 顶部标题：右对齐 -->
      <text x="1200" y="80" text-anchor="end" font-size="18" fill="var(--accent)" font-weight="600">OVERLAPPING CARDS</text>
      <text x="1200" y="130" text-anchor="end" font-size="40" fill="var(--text-1)" font-weight="700" font-family="var(--font-display)">三个优先级</text>
      <!-- 卡片 1：最下层，左上 -->
      <rect x="60" y="200" width="400" height="380" rx="16" fill="var(--surface)" filter="url(#cardShadow)"/>
      <rect x="60" y="200" width="400" height="6" rx="3" fill="var(--accent)"/>
      <circle cx="110" cy="270" r="28" fill="var(--accent)" opacity="0.12"/>
      <text x="110" y="280" text-anchor="middle" font-size="22" fill="var(--accent)" font-weight="700">1</text>
      <text x="140" y="320" font-size="26" fill="var(--text-1)" font-weight="700">基础能力建设</text>
      <text x="100" y="370" font-size="15" fill="var(--text-2)">
        <tspan x="100" dy="0">基础设施升级与稳定性</tspan>
        <tspan x="100" dy="28">保障，2026 Q3 前完成核心</tspan>
        <tspan x="100" dy="28">模块重构。</tspan>
      </text>
      <!-- 卡片 2：中层，偏移到右上方 -->
      <rect x="320" y="160" width="400" height="380" rx="16" fill="var(--surface-2)" filter="url(#cardShadow)"/>
      <rect x="320" y="160" width="400" height="6" rx="3" fill="var(--accent-2)"/>
      <circle cx="370" cy="230" r="28" fill="var(--accent-2)" opacity="0.12"/>
      <text x="370" y="240" text-anchor="middle" font-size="22" fill="var(--accent-2)" font-weight="700">2</text>
      <text x="400" y="280" font-size="26" fill="var(--text-1)" font-weight="700">用户体验优化</text>
      <text x="360" y="330" font-size="15" fill="var(--text-2)">
        <tspan x="360" dy="0">界面焕新与交互流程简化</tspan>
        <tspan x="360" dy="28">，目标用户满意度提升至</tspan>
        <tspan x="360" dy="28">4.5/5 分。</tspan>
      </text>
      <!-- 卡片 3：最上层，右下 -->
      <rect x="580" y="250" width="400" height="380" rx="16" fill="var(--bg)" filter="url(#cardShadow)" stroke="var(--border)"/>
      <rect x="580" y="250" width="400" height="6" rx="3" fill="var(--good)"/>
      <circle cx="630" cy="320" r="28" fill="var(--good)" opacity="0.12"/>
      <text x="630" y="330" text-anchor="middle" font-size="22" fill="var(--good)" font-weight="700">3</text>
      <text x="660" y="370" font-size="26" fill="var(--text-1)" font-weight="700">AI 能力集成</text>
      <text x="620" y="420" font-size="15" fill="var(--text-2)">
        <tspan x="620" dy="0">智能推荐与自动化工作流</tspan>
        <tspan x="620" dy="28">，2026 Q4 推出 Beta 版本</tspan>
        <tspan x="620" dy="28">内测。</tspan>
      </text>
      <!-- 右下角页码 -->
      <text x="1200" y="690" text-anchor="end" font-size="12" fill="var(--text-3)">2 / 10</text>
    </g>
  </g>
</svg>""",

    "full-bleed-split": """<!-- layout: full-bleed-split | 全幅分割 | 对角线/不规则分割 + 两边不同背景 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <g font-family="var(--font-sans)" id="bg-layer">
    <g id="bleed-split-layout">
      <!-- 对角线分割：下方暗色区域 -->
      <path d="M0,720 L1280,280 L1280,720 Z" fill="var(--surface)"/>
      <!-- 上方亮色区域的装饰 -->
      <circle cx="120" cy="80" r="200" fill="var(--accent)" opacity="0.04"/>
      <!-- 上半部分内容：左对齐 -->
      <text x="80" y="100" font-size="16" fill="var(--accent)" font-weight="600">PROBLEM STATEMENT</text>
      <text x="80" y="165" font-size="44" fill="var(--text-1)" font-weight="800" font-family="var(--font-display)">
        <tspan x="80" dy="0">当前面临的核心</tspan>
        <tspan x="80" dy="55">挑战与机遇</tspan>
      </text>
      <text x="80" y="250" font-size="18" fill="var(--text-2)">
        <tspan x="80" dy="0">市场环境快速变化，传统方案难以满足</tspan>
        <tspan x="80" dy="28">新一代用户对体验与效率的双重期待。</tspan>
      </text>
      <!-- 下半部分内容：右对齐 -->
      <text x="1200" y="520" text-anchor="end" font-size="16" fill="var(--accent-2)" font-weight="600">OUR APPROACH</text>
      <text x="1200" y="580" text-anchor="end" font-size="36" fill="var(--text-1)" font-weight="700" font-family="var(--font-display)">三步解决框架</text>
      <rect x="750" y="610" width="450" height="3" rx="1.5" fill="var(--accent)" opacity="0.4"/>
      <text x="1200" y="655" text-anchor="end" font-size="15" fill="var(--text-2)">
        <tspan x="1200" dy="0">Step 1: 诊断分析 → Step 2: 敏捷试点 → Step 3: 规模化推广</tspan>
      </text>
    </g>
  </g>
</svg>""",

    "staggered-grid": """<!-- layout: staggered-grid | 错位网格 | 砖块式不规则排列 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <g font-family="var(--font-sans)" id="bg-layer">
    <g id="staggered-layout">
      <!-- 标题：顶部居中 -->
      <text x="640" y="65" text-anchor="middle" font-size="18" fill="var(--accent)" font-weight="600">FEATURE HIGHLIGHTS</text>
      <text x="640" y="120" text-anchor="middle" font-size="42" fill="var(--text-1)" font-weight="800" font-family="var(--font-display)">产品核心能力矩阵</text>
      <!-- 第1行：2个卡片错位 -->
      <!-- 卡片1：左起，大 -->
      <rect x="40" y="170" width="580" height="180" rx="12" fill="var(--surface)"/>
      <rect x="40" y="170" width="6" height="180" rx="3" fill="var(--accent)"/>
      <text x="80" y="220" font-size="24" fill="var(--text-1)" font-weight="700">智能分析与洞察</text>
      <text x="80" y="260" font-size="15" fill="var(--text-2)">
        <tspan x="80" dy="0">实时数据流处理 + 多维度交叉分析引擎，从海量数据中自动提取</tspan>
        <tspan x="80" dy="26">关键业务洞察，支持自然语言查询与可视化报告一键生成。</tspan>
      </text>
      <rect x="80" y="295" width="100" height="28" rx="14" fill="var(--accent)" opacity="0.1"/>
      <text x="130" y="315" text-anchor="middle" font-size="12" fill="var(--accent)" font-weight="600">核心能力</text>
      <!-- 卡片2：右起，偏向下方跟卡片1有错位 -->
      <rect x="660" y="210" width="580" height="180" rx="12" fill="var(--surface-2)"/>
      <rect x="660" y="210" width="6" height="180" rx="3" fill="var(--accent-2)"/>
      <text x="700" y="260" font-size="24" fill="var(--text-1)" font-weight="700">自动化工作流引擎</text>
      <text x="700" y="300" font-size="15" fill="var(--text-2)">
        <tspan x="700" dy="0">低代码拖拽式流程编排 + 条件触发与定时任务调度，支持跨系统</tspan>
        <tspan x="700" dy="26">集成，减少 60% 重复人工操作。</tspan>
      </text>
      <rect x="700" y="335" width="100" height="28" rx="14" fill="var(--accent-2)" opacity="0.1"/>
      <text x="750" y="355" text-anchor="middle" font-size="12" fill="var(--accent-2)" font-weight="600">效率提升</text>
      <!-- 第2行：3个卡片错位 -->
      <rect x="40" y="400" width="360" height="260" rx="12" fill="var(--bg-soft)"/>
      <text x="80" y="460" font-size="22" fill="var(--text-1)" font-weight="700">安全合规</text>
      <text x="80" y="500" font-size="14" fill="var(--text-2)">
        <tspan x="80" dy="0">SOC 2 Type II 认证</tspan>
        <tspan x="80" dy="24">GDPR / CCPA 合规</tspan>
        <tspan x="80" dy="24">端到端加密传输</tspan>
        <tspan x="80" dy="24">细粒度权限控制</tspan>
      </text>
      <rect x="440" y="430" width="360" height="230" rx="12" fill="var(--surface)"/>
      <text x="480" y="490" font-size="22" fill="var(--text-1)" font-weight="700">开放生态</text>
      <text x="480" y="530" font-size="14" fill="var(--text-2)">
        <tspan x="480" dy="0">RESTful API & GraphQL</tspan>
        <tspan x="480" dy="24">Webhook 事件订阅</tspan>
        <tspan x="480" dy="24">50+ 第三方集成</tspan>
      </text>
      <rect x="840" y="460" width="400" height="200" rx="12" fill="var(--surface-2)"/>
      <text x="880" y="520" font-size="22" fill="var(--text-1)" font-weight="700">全球部署</text>
      <text x="880" y="560" font-size="14" fill="var(--text-2)">
        <tspan x="880" dy="0">8 个可用区 · 99.99% SLA</tspan>
        <tspan x="880" dy="24">自动故障转移 &lt; 30 秒</tspan>
      </text>
    </g>
  </g>
</svg>""",

    "mega-stat": """<!-- layout: mega-stat | 巨型数据 | 突破容器的超大数字 + 环绕说明 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <g font-family="var(--font-sans)" id="bg-layer">
    <g id="mega-stat-layout">
      <!-- 背景装饰：大圆 -->
      <circle cx="640" cy="380" r="280" fill="var(--surface)" opacity="0.5"/>
      <circle cx="640" cy="380" r="200" fill="var(--accent)" opacity="0.05"/>
      <!-- 打破容器的超级数字 -->
      <text x="640" y="420" text-anchor="middle" font-size="180" font-weight="900" fill="var(--accent)" font-family="var(--font-display)" opacity="0.9">42%</text>
      <!-- 主标题压在数字上 -->
      <text x="640" y="200" text-anchor="middle" font-size="20" fill="var(--accent)" font-weight="600">YOY REVENUE GROWTH</text>
      <text x="640" y="260" text-anchor="middle" font-size="44" fill="var(--text-1)" font-weight="800" font-family="var(--font-display)">营收同比增长创历史新高</text>
      <!-- 环绕数据点：左上 -->
      <rect x="80" y="500" width="250" height="90" rx="10" fill="var(--surface-2)"/>
      <text x="205" y="535" text-anchor="middle" font-size="28" font-weight="800" fill="var(--text-1)">$128M</text>
      <text x="205" y="565" text-anchor="middle" font-size="12" fill="var(--text-3)">全年总营收</text>
      <!-- 环绕数据点：左下 -->
      <rect x="80" y="610" width="250" height="90" rx="10" fill="var(--bg-soft)"/>
      <text x="205" y="645" text-anchor="middle" font-size="28" font-weight="800" fill="var(--good)">+18%</text>
      <text x="205" y="675" text-anchor="middle" font-size="12" fill="var(--text-3)">客户留存率提升</text>
      <!-- 环绕数据点：右上 -->
      <rect x="950" y="500" width="250" height="90" rx="10" fill="var(--surface-2)"/>
      <text x="1075" y="535" text-anchor="middle" font-size="28" font-weight="800" fill="var(--text-1)">3.2M</text>
      <text x="1075" y="565" text-anchor="middle" font-size="12" fill="var(--text-3)">月活跃用户数</text>
      <!-- 环绕数据点：右下 -->
      <rect x="950" y="610" width="250" height="90" rx="10" fill="var(--bg-soft)"/>
      <text x="1075" y="645" text-anchor="middle" font-size="28" font-weight="800" fill="var(--accent-2)">#1</text>
      <text x="1075" y="675" text-anchor="middle" font-size="12" fill="var(--text-3)">行业市场份额排名</text>
      <!-- 底部说明 -->
      <rect x="340" y="100" width="600" height="2" fill="var(--border)"/>
    </g>
  </g>
</svg>""",

    "todo-checklist": """<!-- layout: todo-checklist | 待办清单 | 勾选完成列表 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="theme-name">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="80" y="60" font-size="18" fill="var(--accent)" font-weight="600" font-family="var(--font-sans)">执行清单</text>
  <text x="80" y="110" font-size="36" font-weight="700" fill="var(--text-1)" font-family="var(--font-sans)">下一步行动清单</text>
  <g font-family="var(--font-sans)" id="bg-layer">
    <rect x="60" y="160" width="1160" height="460" rx="16" fill="var(--surface)"/>
    <!-- 已完成项 -->
    
    <g id="todo-item-1">
<circle cx="120" cy="220" r="12" fill="var(--good)"/>
    <line x1="112" y1="220" x2="120" y2="228" stroke="var(--bg)" stroke-width="2"/>
    <line x1="119" y1="228" x2="128" y2="214" stroke="var(--bg)" stroke-width="2"/>
    <text x="160" y="226" font-size="18" fill="var(--text-1)" text-decoration="line-through" fill-opacity="0.5">需求文档已签批 ✓</text>
    <!-- 未完成项 -->
    
    </g>

    <g id="todo-item-2">
<circle cx="120" cy="280" r="12" fill="none" stroke="var(--border)" stroke-width="2"/>
    <text x="160" y="286" font-size="18" fill="var(--text-1)">UI 设计初稿评审</text>
    <text x="160" y="310" font-size="13" fill="var(--text-3)">截止日：2025-06-15 · 负责人：张三</text>
    
    </g>

    <g id="todo-item-3">
<circle cx="120" cy="350" r="12" fill="none" stroke="var(--accent)" stroke-width="2"/>
    <rect x="133" y="338" width="10" height="2" fill="var(--accent)" opacity="0.5"/>
    <text x="160" y="356" font-size="18" fill="var(--accent)">后端 API 接口联调</text>
    <text x="160" y="380" font-size="13" fill="var(--text-3)">截止日：2025-06-20 · 负责人：李四</text>
    
    </g>

    <g id="todo-item-4">
<circle cx="120" cy="420" r="12" fill="none" stroke="var(--border)" stroke-width="2"/>
    <text x="160" y="426" font-size="18" fill="var(--text-1)">性能基准测试</text>
    <text x="160" y="450" font-size="13" fill="var(--text-3)">截止日：2025-06-25 · 负责人：王五</text>
    
    </g>

    <g id="todo-item-5">
<circle cx="120" cy="490" r="12" fill="none" stroke="var(--border)" stroke-width="2"/>
    <text x="160" y="496" font-size="18" fill="var(--text-1)">灰度发布方案审批</text>
    <text x="160" y="520" font-size="13" fill="var(--text-3)">截止日：2025-06-28 · 负责人：赵六</text>
    <!-- 底部摘要 -->
    <line x1="80" y1="560" x2="1200" y2="560" stroke="var(--border)"/>
    <text x="100" y="595" font-size="14" fill="var(--text-2)">已完成 1 / 5 项 (20%)</text>
    <rect x="300" y="585" width="200" height="12" rx="6" fill="var(--border)"/>
    <rect x="300" y="585" width="40" height="12" rx="6" fill="var(--good)"/>
  
    </g>
</g>
</svg>""",
}

