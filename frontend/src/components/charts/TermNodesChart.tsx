import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, ReferenceArea } from 'recharts';

interface TermNodesChartProps {
  language: 'zh' | 'en';
}

// Generate smooth profile data representing multiple nodes
const data = Array.from({ length: 100 }, (_, i) => {
  const price = 4000 - i * 2; // 4000 to 3802
  
  // Create multi-modal distribution
  // Node 1: High volume around 3950
  const v1 = 1000 * Math.exp(-Math.pow(price - 3950, 2) / 200);
  // Node 2: High volume around 3880
  const v2 = 800 * Math.exp(-Math.pow(price - 3880, 2) / 150);
  // Base volume
  const base = 50 + Math.random() * 20;
  
  return {
    price,
    volume: v1 + v2 + base
  };
});

export function TermNodesChart({ language }: TermNodesChartProps) {
  const t = {
    hvn: language === 'zh' ? 'HVN (高成交量节点) - 机构建仓区 / 强阻力支撑' : 'HVN (High Volume Node) - Accumulation / Strong S/R',
    lvn: language === 'zh' ? 'LVN (低成交量节点) - 价格真空区 / 快速穿透' : 'LVN (Low Volume Node) - Vacuum / Fast Rejection',
  };

  return (
    <div className="w-full h-[400px] relative">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={data}
          layout="vertical"
          margin={{ top: 20, right: 20, left: 60, bottom: 20 }}
        >
          <XAxis type="number" hide />
          <YAxis 
            dataKey="price" 
            type="number" 
            domain={['dataMin', 'dataMax']}
            axisLine={false} 
            tickLine={false} 
            tick={{ fill: '#888', fontSize: 12 }} 
          />
          <Tooltip 
            cursor={false}
            contentStyle={{ backgroundColor: '#111', border: '1px solid #333' }}
          />
          
          {/* Highlight LVN region */}
          <ReferenceArea y1={3900} y2={3930} fill="rgba(255, 0, 0, 0.1)" />
          
          {/* Highlight HVN regions */}
          <ReferenceArea y1={3940} y2={3960} fill="rgba(0, 255, 136, 0.1)" />
          <ReferenceArea y1={3870} y2={3890} fill="rgba(0, 255, 136, 0.1)" />

          <Area 
            type="monotone" 
            dataKey="volume" 
            stroke="#00ff88" 
            fill="rgba(0, 255, 136, 0.2)"
            strokeWidth={2}
          />
        </AreaChart>
      </ResponsiveContainer>
      
      {/* Labels */}
      <div className="absolute top-[20%] right-[10%] bg-neutral-900 border border-[#00ff88] text-[#00ff88] px-3 py-1 rounded text-sm font-bold">
        {t.hvn}
      </div>
      <div className="absolute top-[45%] right-[10%] bg-neutral-900 border border-red-500 text-red-500 px-3 py-1 rounded text-sm font-bold">
        {t.lvn}
      </div>
      <div className="absolute top-[75%] right-[10%] bg-neutral-900 border border-[#00ff88] text-[#00ff88] px-3 py-1 rounded text-sm font-bold">
        {t.hvn}
      </div>
    </div>
  );
}
