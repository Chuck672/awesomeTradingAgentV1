import React from 'react';

export interface Candle {
  open: number;
  close: number;
  high: number;
  low: number;
}

export interface ProfileNode {
  price: number;
  volume: number;
  isVA?: boolean;
  isPOC?: boolean;
}

export interface Highlight {
  type: 'line' | 'zone' | 'arrow';
  y1: number; // Price level 1
  y2?: number; // Price level 2 (for zones)
  x?: number; // Candle index anchor for arrows/lines
  label: string;
  color: string;
}

export interface CandleProfileChartProps {
  candles: Candle[];
  profile: ProfileNode[];
  highlights?: Highlight[];
  title?: string;
  language?: 'zh' | 'en';
}

const zhLabelMap: Record<string, string> = {
  'POC (Point of Control)': 'POC（控制点）',
  'HVN (Upper Balance)': 'HVN（上方平衡区）',
  'HVN (Lower Balance)': 'HVN（下方平衡区）',
  'LVN (Rejection / Vacuum)': 'LVN（拒绝/真空）',
  'Initial Balance (First 60 mins)': '初始平衡区（前60分钟）',
  'Single Prints (Imbalance Gap)': '单次打印（失衡空档）',
  'Poor High (Flat Top)': '弱高点（平顶）',
  'No Wicks Above': '上方无影线',
  'Excess Tail': '过度延伸尾部',
  'Strong Rejection Wick': '强拒绝影线',
  'Balanced Market (Normal Day)': '平衡市场（普通日）',
  'Heavy Volume at Top': '顶部重成交区',
  'Heavy Volume at Bottom': '底部重成交区',
  'Upper Balance': '上方平衡区',
  'Lower Balance': '下方平衡区',
  'LVN (Separating Breakout)': 'LVN（分离突破）',
  'Balance: D-Shape Acceptance': '平衡：D形接受区',
  'Imbalance Expansion': '失衡扩张区',
  'POC / Fair Price Magnet': 'POC / 公允价格磁吸区',
  'LVN Pocket': 'LVN 真空口袋',
  'New Acceptance Zone': '新接受区',
  'Old Acceptance Zone': '旧接受区',
  Open: '开盘价',
  'One-way Initiative': '单边主动推进',
  'Opening Test': '开盘测试区',
  'Drive Phase': '推动阶段',
  'Failed Opening Area': '开盘失败区',
  'Reversal Acceptance': '反转接受区',
  'Opening Rotation': '开盘轮转区',
  'Monthly Value Area': '月度价值区',
  'Weekly Value Area': '周度价值区',
  'Daily POC': '日内 POC',
  'Weekly Acceptance Lift': '周度接受抬升',
  'Monthly POC': '月度 POC',
  'Intraday POC Migration': '日内 POC 迁移',
  'VAH Sell Zone': 'VAH 卖出区',
  'VAL Buy Zone': 'VAL 买入区',
  'Rotation Core': '轮转核心区',
  'POC Magnet': 'POC 磁吸位',
  Overextension: '过度偏离区',
  'LVN Passage': 'LVN 通道',
  'Next HVN Target': '下一个 HVN 目标',
  'Naked POC': '裸 POC',
  'First Touch Reaction Zone': '首次触碰反应区',
  'Prior VAH': '前一日 VAH',
  'Prior VAL': '前一日 VAL',
  'Prior POC': '前一日 POC',
  'P-shape Lift Zone': 'P形抬升区',
  'b-shape Liquidation Zone': 'b形清算区',
  'Execution Pivot': '执行中枢',
  'Upper Risk Boundary': '上方风险边界',
  'Lower Risk Boundary': '下方风险边界',
  'Entry (Long)': '入场位（做多）',
  'Entry (Short)': '入场位（做空）',
  'Stop Loss': '止损位',
  'Take Profit': '止盈位',
  'Take Profit 1': '止盈位 1',
  'Take Profit 2': '止盈位 2',
  'Invalidation': '失效位',
  'Entry Candle': '入场触发K线',
};

const translateLabel = (label: string, language: 'zh' | 'en') => {
  if (language === 'en') return label;
  return zhLabelMap[label] ?? label;
};

export const CandleProfileChart: React.FC<CandleProfileChartProps> = ({ candles, profile, highlights, title, language = 'zh' }) => {
  // Chart dimensions
  const width = 800;
  const height = 400;
  const margin = { top: 30, right: 20, bottom: 20, left: 20 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;

  // Split view: 60% Candles, 40% Profile
  const candleAreaWidth = innerWidth * 0.6;
  const profileAreaWidth = innerWidth * 0.4;
  const profileStartX = margin.left + candleAreaWidth + 10;

  // Find min/max price for Y-axis scaling
  const allPrices = [
    ...candles.map(c => c.high),
    ...candles.map(c => c.low),
    ...profile.map(p => p.price)
  ];
  const minPrice = Math.min(...allPrices);
  const maxPrice = Math.max(...allPrices);
  const priceRange = maxPrice - minPrice || 1; // Prevent division by zero

  // Find max volume for X-axis scaling in Profile
  const maxVolume = Math.max(...profile.map(p => p.volume));

  // Y-coordinate mapping function (Price to SVG Y)
  const getY = (price: number) => {
    return margin.top + innerHeight - ((price - minPrice) / priceRange) * innerHeight;
  };

  // Candle X-coordinate mapping
  const candleSpacing = candleAreaWidth / Math.max(candles.length, 1);
  const candleWidth = candleSpacing * 0.6;

  return (
    <div className="w-full h-full flex flex-col items-center justify-center bg-[#0a0a0c] border border-gray-800 rounded-lg p-4 shadow-2xl relative overflow-hidden">
      {title && <h3 className="absolute top-4 left-6 text-gray-300 font-bold text-lg">{title}</h3>}
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full text-xs font-mono">
        {/* Background Grid Lines (Horizontal) */}
        {[0, 0.25, 0.5, 0.75, 1].map((tick) => {
          const y = margin.top + tick * innerHeight;
          return (
            <line key={tick} x1={margin.left} y1={y} x2={width - margin.right} y2={y} stroke="#1f2937" strokeDasharray="4 4" />
          );
        })}

        {/* Highlights - Zones (Drawn behind candles) */}
        {highlights?.filter(h => h.type === 'zone').map((h, i) => {
          const yTop = getY(Math.max(h.y1, h.y2!));
          const yBottom = getY(Math.min(h.y1, h.y2!));
          return (
            <g key={`zone-${i}`}>
              <rect
                x={margin.left}
                y={yTop}
                width={innerWidth}
                height={Math.max(yBottom - yTop, 2)}
                fill={h.color}
                opacity={0.15}
              />
              <text x={margin.left + 5} y={yTop + 14} fill={h.color} opacity={0.8} fontWeight="bold">{translateLabel(h.label, language)}</text>
            </g>
          );
        })}

        {/* Candlesticks */}
        {candles.map((candle, i) => {
          const x = margin.left + i * candleSpacing + candleSpacing / 2;
          const isBull = candle.close >= candle.open;
          const color = isBull ? '#22c55e' : '#ef4444'; // Tailwind green-500 : red-500
          
          return (
            <g key={`candle-${i}`}>
              {/* Wick */}
              <line
                x1={x} y1={getY(candle.high)}
                x2={x} y2={getY(candle.low)}
                stroke={color} strokeWidth={2}
              />
              {/* Body */}
              <rect
                x={x - candleWidth / 2}
                y={getY(Math.max(candle.open, candle.close))}
                width={candleWidth}
                height={Math.max(Math.abs(getY(candle.open) - getY(candle.close)), 2)}
                fill={isBull ? '#0a0a0c' : color} // Hollow green, solid red
                stroke={color}
                strokeWidth={1.5}
              />
            </g>
          );
        })}

        {/* Volume Profile */}
        {profile.map((p, i) => {
          const barWidth = (p.volume / maxVolume) * profileAreaWidth;
          const yCenter = getY(p.price);
          // Calculate height of each profile bar (approximate based on price step)
          const step = profile.length > 1 ? Math.abs(getY(profile[0].price) - getY(profile[1].price)) : 10;
          
          let fill = '#374151'; // default gray
          if (p.isPOC) fill = '#22c55e'; // POC Green
          else if (p.isVA) fill = '#60a5fa'; // VA Blue

          return (
            <rect
              key={`profile-${i}`}
              x={profileStartX}
              y={yCenter - step / 2}
              width={barWidth}
              height={Math.max(step * 0.9, 1)}
              fill={fill}
              opacity={p.isPOC ? 1 : (p.isVA ? 0.6 : 0.3)}
            />
          );
        })}

        {/* Highlights - Lines (Drawn in front) */}
        {highlights?.filter(h => h.type === 'line').map((h, i) => {
          const y = getY(h.y1);
          const lineStartX =
            typeof h.x === 'number'
              ? margin.left + h.x * candleSpacing + candleSpacing / 2
              : margin.left;
          return (
            <g key={`line-${i}`}>
              <line x1={lineStartX} y1={y} x2={width - margin.right} y2={y} stroke={h.color} strokeWidth={2} strokeDasharray="6 4" />
              <rect x={width - margin.right - 60} y={y - 10} width={60} height={20} fill="#111" stroke={h.color} rx={4} />
               <text x={width - margin.right - 30} y={y + 4} fill={h.color} textAnchor="middle" fontWeight="bold">{translateLabel(h.label, language)}</text>
            </g>
          );
        })}

        {/* Highlights - Arrows/Text */}
        {highlights?.filter(h => h.type === 'arrow').map((h, i) => {
          const y = getY(h.y1);
          const x =
            typeof h.x === 'number'
              ? margin.left + h.x * candleSpacing + candleSpacing / 2
              : margin.left + candleAreaWidth / 2;
          return (
            <g key={`arrow-${i}`}>
              <path d={`M ${x} ${y-20} L ${x} ${y-5} L ${x-5} ${y-10} M ${x} ${y-5} L ${x+5} ${y-10}`} stroke={h.color} strokeWidth={2} fill="none" />
               <text x={x} y={y-25} fill={h.color} textAnchor="middle" fontWeight="bold">{translateLabel(h.label, language)}</text>
            </g>
          );
        })}

        {/* Divider Line */}
        <line x1={profileStartX - 5} y1={margin.top} x2={profileStartX - 5} y2={height - margin.bottom} stroke="#374151" strokeWidth={1} />
        <text x={profileStartX + 10} y={margin.top - 10} fill="#9ca3af" fontSize="10">
          {language === 'zh' ? '成交量分布' : 'VOLUME PROFILE'}
        </text>
      </svg>
    </div>
  );
};
