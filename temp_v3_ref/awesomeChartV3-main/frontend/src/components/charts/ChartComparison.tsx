import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell, ReferenceLine, ComposedChart, Line } from 'recharts';

interface ChartComparisonProps {
  language: 'zh' | 'en';
}

const data = [
  { price: '100', volPrice: 10, time: '10:00', volTime: 50 },
  { price: '101', volPrice: 15, time: '10:15', volTime: 30 },
  { price: '102', volPrice: 40, time: '10:30', volTime: 80 },
  { price: '103', volPrice: 65, time: '10:45', volTime: 40 },
  { price: '104', volPrice: 100, time: '11:00', volTime: 90 }, // POC
  { price: '105', volPrice: 80, time: '11:15', volTime: 20 },
  { price: '106', volPrice: 50, time: '11:30', volTime: 60 },
  { price: '107', volPrice: 20, time: '11:45', volTime: 10 },
  { price: '108', volPrice: 5, time: '12:00', volTime: 35 },
];

export function ChartComparison({ language }: ChartComparisonProps) {
  return (
    <div className="w-full h-full flex flex-col gap-6">
      {/* Top half: Price vs Time (Traditional) */}
      <div className="flex-1 flex flex-col relative bg-neutral-900/40 rounded-lg p-2 border border-neutral-800/50">
        <h4 className="text-sm text-neutral-400 absolute top-2 left-2 z-10 font-mono bg-neutral-950/80 px-2 py-1 rounded">
          {language === 'zh' ? '传统成交量：基于时间' : 'Traditional: Time-based'}
        </h4>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 40, right: 10, left: 0, bottom: 0 }}>
            <XAxis dataKey="time" stroke="#525252" fontSize={10} tickMargin={5} />
            <YAxis yAxisId="price" orientation="right" domain={['dataMin - 1', 'dataMax + 1']} stroke="#525252" fontSize={10} />
            <YAxis yAxisId="volume" orientation="left" domain={[0, 'dataMax * 3']} hide />
            <Tooltip contentStyle={{ backgroundColor: '#171717', border: '1px solid #262626' }} />
            
            {/* Mock Price Line */}
            <Line yAxisId="price" type="monotone" dataKey="price" stroke="#ffffff" strokeWidth={2} dot={{ r: 3, fill: '#00ff88' }} />
            {/* Volume Bars at bottom */}
            <Bar yAxisId="volume" dataKey="volTime" fill="#525252" opacity={0.5} barSize={20} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Bottom half: Volume Profile (Price-based) */}
      <div className="flex-1 flex flex-col relative bg-neutral-900/40 rounded-lg p-2 border border-[#00ff88]/20">
        <h4 className="text-sm text-[#00ff88] absolute top-2 left-2 z-10 font-mono bg-[#00ff88]/10 px-2 py-1 rounded">
          {language === 'zh' ? '成交量分布：基于价格' : 'Volume Profile: Price-based'}
        </h4>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart layout="vertical" data={data} margin={{ top: 40, right: 10, left: -20, bottom: 0 }}>
            <XAxis type="number" hide />
            <YAxis dataKey="price" type="category" stroke="#525252" fontSize={10} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={{ backgroundColor: '#171717', border: '1px solid #00ff88' }} cursor={{ fill: '#00ff88', opacity: 0.1 }} />
            
            <Bar dataKey="volPrice" fill="#00ff88" opacity={0.8} barSize={15}>
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.volPrice === 100 ? '#ffffff' : '#00ff88'} />
              ))}
            </Bar>
            <ReferenceLine
              y="104"
              stroke="#ffffff"
              strokeDasharray="3 3"
              label={{ position: 'right', value: language === 'zh' ? 'POC（控制点）' : 'POC', fill: '#fff', fontSize: 10 }}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
