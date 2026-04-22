interface TermShapesChartProps {
  language: 'zh' | 'en';
}

export function TermShapesChart({ language }: TermShapesChartProps) {
  const shapes = [
    {
      id: 'p',
      name: language === 'zh' ? 'P形分布（空头回补/偏多）' : 'P-Shape (Short Covering/Bullish)',
      bars: [10, 15, 20, 30, 80, 100, 90, 70, 20, 15, 10], // Bottom to top
      color: '#00ff88'
    },
    {
      id: 'b',
      name: language === 'zh' ? 'b形分布（多头清仓/偏空）' : 'b-Shape (Long Liquidation/Bearish)',
      bars: [10, 15, 20, 80, 100, 90, 70, 30, 20, 15, 10], // Bottom to top
      color: '#ff4444'
    },
    {
      id: 'D',
      name: language === 'zh' ? 'D形分布（平衡市/震荡）' : 'D-Shape (Balanced/Ranging)',
      bars: [10, 20, 40, 60, 80, 100, 80, 60, 40, 20, 10],
      color: '#a855f7'
    },
    {
      id: 'B',
      name: language === 'zh' ? '双峰/B形（趋势中继）' : 'Double/B-Shape (Trend Continuation)',
      bars: [10, 30, 80, 90, 40, 20, 30, 90, 100, 40, 10],
      color: '#3b82f6'
    }
  ];

  return (
    <div className="w-full h-full grid grid-cols-2 gap-4 p-4">
      {shapes.map((shape) => (
        <div key={shape.id} className="bg-neutral-900/80 rounded-lg border border-neutral-800 p-4 flex flex-col items-center justify-center relative">
          <div className="text-sm font-bold text-neutral-300 mb-4">{shape.name}</div>
          <div className="flex flex-col-reverse items-start justify-center gap-[2px] w-[150px] h-[150px]">
            {shape.bars.map((w, i) => (
              <div 
                key={i} 
                className="h-full rounded-r-sm" 
                style={{ 
                  width: `${w}%`, 
                  backgroundColor: shape.color,
                  opacity: w === 100 ? 1 : 0.4 + (w/100)*0.4 
                }} 
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
