import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell, ReferenceArea, ReferenceLine } from 'recharts';

interface PriceValueChartProps {
  language: 'zh' | 'en';
}

const data = [
  { price: '3800', volume: 5, type: 'tail' },
  { price: '3810', volume: 15, type: 'tail' },
  { price: '3820', volume: 40, type: 'va' },   // VA Low
  { price: '3830', volume: 85, type: 'va' },
  { price: '3840', volume: 100, type: 'poc' }, // POC
  { price: '3850', volume: 90, type: 'va' },
  { price: '3860', volume: 60, type: 'va' },   // VA High
  { price: '3870', volume: 25, type: 'tail' },
  { price: '3880', volume: 10, type: 'tail' },
];

export function PriceValueChart({ language }: PriceValueChartProps) {
  return (
    <div className="w-full h-full p-4 flex flex-col items-center justify-center relative">
      <div className="absolute top-4 left-4 right-4 flex justify-between z-10 text-xs font-mono">
        <span className="bg-red-500/20 text-red-400 px-2 py-1 rounded border border-red-500/50">
          {language === 'zh' ? '价格偏离 (弹簧拉伸)' : 'Price Deviation (Spring stretched)'}
        </span>
        <span className="bg-[#00ff88]/20 text-[#00ff88] px-2 py-1 rounded border border-[#00ff88]/50">
          {language === 'zh' ? '价值区域 (共识)' : 'Value Area (Consensus)'}
        </span>
      </div>
      
      <ResponsiveContainer width="90%" height="90%">
        <BarChart layout="vertical" data={data} margin={{ top: 40, right: 30, left: 20, bottom: 20 }}>
          <XAxis type="number" hide />
          <YAxis dataKey="price" type="category" stroke="#a3a3a3" axisLine={false} tickLine={false} />
          
          <Tooltip 
            cursor={{ fill: '#333', opacity: 0.5 }}
            contentStyle={{ backgroundColor: '#171717', border: '1px solid #333' }}
          />

          {/* Value Area High and Low shaded area representation (using ReferenceArea) */}
          <ReferenceArea y1="3820" y2="3860" fill="#00ff88" fillOpacity={0.05} />
          
          <ReferenceLine y="3840" stroke="#fff" strokeDasharray="3 3" />
          <ReferenceLine y="3860" stroke="#00ff88" strokeOpacity={0.5} />
          <ReferenceLine y="3820" stroke="#00ff88" strokeOpacity={0.5} />
          
          <Bar dataKey="volume" fill="#525252" barSize={20}>
            {data.map((entry, index) => {
              let fill = '#525252';
              if (entry.type === 'va') fill = '#00ff88';
              if (entry.type === 'poc') fill = '#ffffff';
              return <Cell key={`cell-${index}`} fill={fill} fillOpacity={entry.type === 'poc' ? 1 : 0.8} />;
            })}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      
      <div className="absolute right-10 bottom-1/2 translate-y-[-50%] flex flex-col items-start gap-4">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 bg-white rounded-full"></div>
          <span className="text-sm font-mono text-white">
            {language === 'zh' ? 'POC（控制点）' : 'POC (Point of Control)'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 bg-[#00ff88] rounded-full"></div>
          <span className="text-sm font-mono text-[#00ff88]">
            {language === 'zh' ? 'VA（价值区 - 70%）' : 'VA (Value Area - 70%)'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 bg-[#525252] rounded-full"></div>
          <span className="text-sm font-mono text-[#525252]">
            {language === 'zh' ? '价值区外' : 'Out of Value Area'}
          </span>
        </div>
      </div>
    </div>
  );
}
