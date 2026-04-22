interface TermTPOChartProps {
  language: 'zh' | 'en';
}

export function TermTPOChart({ language }: TermTPOChartProps) {
  const rows = [
    { price: '4005', letters: 'A' },
    { price: '4004', letters: 'A B' },
    { price: '4003', letters: 'A B C' },
    { price: '4002', letters: 'A B C D', isIB: true },
    { price: '4001', letters: 'A B C D E', isIB: true },
    { price: '4000', letters: 'A B C D E F', isIB: true, isPOC: true },
    { price: '3999', letters: 'B C D E F G', isIB: true },
    { price: '3998', letters: 'C D E F G', isIB: true },
    { price: '3997', letters: 'E F G H' },
    { price: '3996', letters: 'F G H' },
    { price: '3995', letters: 'H I' },
    { price: '3994', letters: 'I' },
  ];

  return (
    <div className="w-full h-full flex items-center justify-center p-8">
      <div className="flex bg-neutral-900 border border-neutral-800 rounded-lg p-6 w-full max-w-lg shadow-2xl relative">
        
        {/* Y Axis Prices */}
        <div className="flex flex-col border-r border-neutral-700 pr-4 mr-4 text-neutral-400 font-mono text-sm gap-1">
          {rows.map((r, i) => (
            <div key={i} className={`h-6 flex items-center ${r.isPOC ? 'text-[#00ff88] font-bold' : ''}`}>
              {r.price}
            </div>
          ))}
        </div>

        {/* TPO Letters */}
        <div className="flex flex-col font-mono text-sm gap-1 relative flex-1">
          {rows.map((r, i) => (
            <div key={i} className={`h-6 flex items-center tracking-[0.2em] ${r.isPOC ? 'text-[#00ff88] font-bold bg-[#00ff88]/10 px-2 -mx-2 rounded' : 'text-neutral-300'}`}>
              {r.letters}
            </div>
          ))}
          
          {/* Initial Balance Bracket */}
          <div className="absolute left-[150px] top-[72px] bottom-[96px] w-4 border-r-2 border-t-2 border-b-2 border-[#00ff88]/50 rounded-r-md" />
          <div className="absolute left-[160px] top-[108px] text-[#00ff88] text-xs font-bold whitespace-nowrap">
            {language === 'zh' ? '初始平衡区（IB）- 开盘首小时范围' : 'Initial Balance (IB) - First Hour Range'}
          </div>
        </div>

        {/* Explanation Floating */}
        <div className="absolute top-4 right-4 bg-neutral-800 text-neutral-300 text-xs p-3 rounded border border-neutral-700 max-w-[200px]">
          {language === 'zh' ? (
            <>
              <p className="mb-2"><span className="text-white font-bold">TPO</span> = 时间-价格机会</p>
              <p>每个字母代表一个 30 分钟时段（A=09:30，B=10:00...）</p>
            </>
          ) : (
            <>
              <p className="mb-2"><span className="text-white font-bold">TPO</span> = Time Price Opportunity</p>
              <p>Each letter represents a 30-minute period (A=09:30, B=10:00...)</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
