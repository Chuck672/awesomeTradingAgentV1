import { ResponsiveContainer, BarChart, Bar, YAxis, XAxis, Tooltip, ReferenceLine, Cell } from 'recharts';

interface TermPOCVAChartProps {
  language: 'zh' | 'en';
}

const data = [
  { price: 4000, volume: 120 },
  { price: 3990, volume: 150 },
  { price: 3980, volume: 300 }, // VAH
  { price: 3970, volume: 550 },
  { price: 3960, volume: 800 },
  { price: 3950, volume: 1200 }, // POC
  { price: 3940, volume: 900 },
  { price: 3930, volume: 600 },
  { price: 3920, volume: 350 }, // VAL
  { price: 3910, volume: 200 },
  { price: 3900, volume: 100 },
];

export function TermPOCVAChart({ language }: TermPOCVAChartProps) {
  const t = {
    poc: language === 'zh' ? 'POC (控制点)' : 'POC (Point of Control)',
    vah: language === 'zh' ? 'VAH (价值区间高点)' : 'VAH',
    val: language === 'zh' ? 'VAL (价值区间低点)' : 'VAL',
    va: language === 'zh' ? '70% 价值区间 (Value Area)' : '70% Value Area',
  };

  return (
    <div className="w-full h-[400px] flex flex-col relative">
      <div className="absolute top-4 left-4 z-10 text-neutral-400 text-sm">
        <div className="flex items-center gap-2 mb-1">
          <div className="w-3 h-3 bg-[#00ff88]" />
          <span>{t.va}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 bg-neutral-600" />
          <span>{language === 'zh' ? '价值区外' : 'Out of Value'}</span>
        </div>
      </div>
      
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 20, right: 120, left: 60, bottom: 20 }}
        >
          <XAxis type="number" hide />
          <YAxis 
            dataKey="price" 
            type="category" 
            axisLine={false} 
            tickLine={false} 
            tick={{ fill: '#888', fontSize: 12 }} 
          />
          <Tooltip 
            cursor={{ fill: 'rgba(255,255,255,0.05)' }}
            contentStyle={{ backgroundColor: '#111', border: '1px solid #333' }}
          />
          <Bar dataKey="volume" radius={[0, 4, 4, 0]}>
            {data.map((entry, index) => {
              const isVA = entry.price <= 3980 && entry.price >= 3920;
              const isPOC = entry.price === 3950;
              return (
                <Cell 
                  key={`cell-${index}`} 
                  fill={isPOC ? '#00ff88' : isVA ? 'rgba(0, 255, 136, 0.4)' : '#333'} 
                />
              );
            })}
          </Bar>
          
          <ReferenceLine y={3950} stroke="#00ff88" strokeWidth={2} strokeDasharray="3 3">
            <text x="100%" y="0" dy={4} dx={10} fill="#00ff88" fontSize={14} fontWeight="bold">{t.poc}</text>
          </ReferenceLine>
          <ReferenceLine y={3980} stroke="rgba(0,255,136,0.6)" strokeWidth={1} strokeDasharray="3 3">
            <text x="100%" y="0" dy={4} dx={10} fill="rgba(0,255,136,0.8)" fontSize={12}>{t.vah}</text>
          </ReferenceLine>
          <ReferenceLine y={3920} stroke="rgba(0,255,136,0.6)" strokeWidth={1} strokeDasharray="3 3">
            <text x="100%" y="0" dy={4} dx={10} fill="rgba(0,255,136,0.8)" fontSize={12}>{t.val}</text>
          </ReferenceLine>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
