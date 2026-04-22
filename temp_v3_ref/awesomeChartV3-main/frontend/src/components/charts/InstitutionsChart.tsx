import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell } from 'recharts';

interface InstitutionsChartProps {
  language: 'zh' | 'en';
}

export function InstitutionsChart({ language }: InstitutionsChartProps) {
  const data = [
    { price: language === 'zh' ? '高位' : 'High', volume: 10, type: 'retail_top' },
    { price: '..', volume: 20, type: 'tail' },
    { price: '...', volume: 30, type: 'tail' },
    { price: '....', volume: 80, type: 'hvn' },
    { price: '.....', volume: 100, type: 'hvn' },
    { price: '......', volume: 85, type: 'hvn' },
    { price: '.......', volume: 30, type: 'tail' },
    { price: '........', volume: 15, type: 'tail' },
    { price: language === 'zh' ? '低位' : 'Low', volume: 5, type: 'retail_bottom' },
  ];

  return (
    <div className="w-full h-full p-4 flex flex-col items-center justify-center relative">
      <div className="absolute top-2 right-4 flex flex-col items-end gap-2 z-10 text-xs font-mono text-red-400">
        <span>{language === 'zh' ? '↑ 散户试图猜顶做空' : '↑ Retail guesses top to short'}</span>
      </div>
      
      <div className="absolute bottom-6 right-4 flex flex-col items-end gap-2 z-10 text-xs font-mono text-red-400">
        <span>{language === 'zh' ? '↓ 散户试图猜底做多' : '↓ Retail guesses bottom to long'}</span>
      </div>
      
      <div className="absolute top-1/2 left-10 translate-y-[-50%] flex flex-col items-start gap-2 z-10 text-sm font-bold text-[#00ff88]">
        <div className="bg-[#00ff88]/20 px-4 py-2 rounded-lg border border-[#00ff88]/50 shadow-[0_0_20px_rgba(0,255,136,0.2)]">
          {language === 'zh' ? '机构缓慢吸筹区间 (HVN)' : 'Institutional Accumulation Zone (HVN)'}
          <br />
          <span className="text-xs text-neutral-300 font-normal">
            {language === 'zh' ? '巨大凸起部位' : 'Huge bulging area'}
          </span>
        </div>
      </div>
      
      <ResponsiveContainer width="100%" height="90%">
        <BarChart layout="vertical" data={data} margin={{ top: 20, right: 120, left: 180, bottom: 20 }}>
          <XAxis type="number" hide />
          <YAxis dataKey="price" type="category" stroke="#525252" axisLine={false} tickLine={false} width={40} />
          
          <Tooltip 
            cursor={{ fill: '#333', opacity: 0.5 }}
            contentStyle={{ backgroundColor: '#171717', border: '1px solid #333' }}
          />

          <Bar dataKey="volume" fill="#525252" barSize={25}>
            {data.map((entry, index) => {
              let fill = '#525252';
              if (entry.type === 'hvn') fill = '#00ff88';
              if (entry.type === 'retail_top' || entry.type === 'retail_bottom') fill = '#ef4444';
              return <Cell key={`cell-${index}`} fill={fill} fillOpacity={0.8} />;
            })}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
