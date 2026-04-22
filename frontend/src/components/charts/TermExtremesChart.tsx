interface TermExtremesChartProps {
  language: 'zh' | 'en';
}

export function TermExtremesChart({ language }: TermExtremesChartProps) {
  const t = {
    poorHigh: language === 'zh' ? '弱高点' : 'Poor High',
    poorHighDesc: language === 'zh' ? '缺乏明确拒绝，顶部平整，价格极可能再次回测' : 'Lack of clear rejection, flat top, high probability of revisit',
    excess: language === 'zh' ? '过度延伸（长尾）' : 'Excess (Tail)',
    excessDesc: language === 'zh' ? '强烈的价格拒绝，形成单排TPO长尾，确认了边界' : 'Strong price rejection, single print tail, confirms boundary',
    singlePrints: language === 'zh' ? '单次打印' : 'Single Prints',
    singlePrintsDesc: language === 'zh' ? '情绪化买盘导致价格真空，通常会被回填 (Gap fill)' : 'Emotional buying creates vacuum, often gets filled back',
  };

  return (
    <div className="w-full h-full flex flex-col gap-6 p-4 justify-center">
      
      {/* Poor High Example */}
      <div className="flex items-center gap-6 bg-neutral-900/50 p-4 rounded-lg border border-neutral-800">
        <div className="flex flex-col-reverse gap-[2px] w-[100px] h-[80px]">
          {[80, 80, 80].map((w, i) => ( // Flat top
            <div key={i} className="h-full bg-red-500/80 rounded-r-sm" style={{ width: `${w}%` }} />
          ))}
          {[60, 40, 20].map((w, i) => (
            <div key={i} className="h-full bg-neutral-600 rounded-r-sm" style={{ width: `${w}%` }} />
          ))}
        </div>
        <div>
          <h3 className="text-red-400 font-bold mb-1">{t.poorHigh}</h3>
          <p className="text-sm text-neutral-400">{t.poorHighDesc}</p>
        </div>
      </div>

      {/* Single Prints Example */}
      <div className="flex items-center gap-6 bg-neutral-900/50 p-4 rounded-lg border border-neutral-800">
        <div className="flex flex-col-reverse gap-[2px] w-[100px] h-[100px] relative">
          {[80, 90].map((w, i) => (
            <div key={`b-${i}`} className="h-[12px] bg-neutral-600 rounded-r-sm" style={{ width: `${w}%` }} />
          ))}
          
          {/* Single Prints Area */}
          {[10, 10, 10].map((w, i) => (
            <div key={`s-${i}`} className="h-[12px] bg-yellow-500/80 rounded-r-sm" style={{ width: `${w}%` }} />
          ))}

          {[70, 80].map((w, i) => (
            <div key={`t-${i}`} className="h-[12px] bg-neutral-600 rounded-r-sm" style={{ width: `${w}%` }} />
          ))}

          {/* Bracket for Single Prints */}
          <div className="absolute right-[-10px] top-[26px] h-[36px] w-2 border-r border-t border-b border-yellow-500/50" />
        </div>
        <div>
          <h3 className="text-yellow-400 font-bold mb-1">{t.singlePrints}</h3>
          <p className="text-sm text-neutral-400">{t.singlePrintsDesc}</p>
        </div>
      </div>

      {/* Excess Example */}
      <div className="flex items-center gap-6 bg-neutral-900/50 p-4 rounded-lg border border-neutral-800">
        <div className="flex flex-col-reverse gap-[2px] w-[100px] h-[80px]">
          {[60, 80, 100, 70].map((w, i) => (
            <div key={`m-${i}`} className="h-[12px] bg-neutral-600 rounded-r-sm" style={{ width: `${w}%` }} />
          ))}
          
          {/* Tail / Excess */}
          {[10, 8, 5, 2].map((w, i) => (
            <div key={`e-${i}`} className="h-[12px] bg-[#00ff88]/80 rounded-r-sm" style={{ width: `${w}%` }} />
          ))}
        </div>
        <div>
          <h3 className="text-[#00ff88] font-bold mb-1">{t.excess}</h3>
          <p className="text-sm text-neutral-400">{t.excessDesc}</p>
        </div>
      </div>

    </div>
  );
}
