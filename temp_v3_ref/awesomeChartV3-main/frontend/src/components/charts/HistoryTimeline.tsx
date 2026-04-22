interface HistoryTimelineProps {
  language: 'zh' | 'en';
}

export function HistoryTimeline({ language }: HistoryTimelineProps) {
  const events = [
    {
      year: '1980s',
      title: language === 'zh' ? '芝加哥交易所场内交易' : 'CBOT Floor Trading',
      desc: language === 'zh' ? '彼得·斯泰德迈尔基于时间开发出 Market Profile (市场轮廓)' : 'Peter Steidlmayer developed Market Profile based on time',
    },
    {
      year: '1990s-2000s',
      title: language === 'zh' ? '电子化交易普及' : 'Electronic Trading Boom',
      desc: language === 'zh' ? '获取真实逐笔交易(Tick)成为可能，不再仅仅依赖时间' : 'Real tick data became available, no longer relying solely on time',
    },
    {
      year: 'Present',
      title: language === 'zh' ? '精确的 Volume Profile' : 'Precise Volume Profile',
      desc: language === 'zh' ? '根据真实发生的资金量精准定位机构成本区' : 'Precise targeting of institutional cost basis via actual capital flow',
    },
  ];

  return (
    <div className="w-full h-full p-8 flex flex-col justify-center">
      <div className="relative border-l-2 border-neutral-800 ml-4 flex flex-col gap-12">
        {events.map((evt, idx) => (
          <div key={idx} className="relative pl-8">
            <div className="absolute left-[-9px] top-1 w-4 h-4 rounded-full bg-neutral-900 border-2 border-[#00ff88]" />
            <h4 className="text-xl font-bold text-[#00ff88] font-mono mb-2">{evt.year}</h4>
            <h5 className="text-lg text-white font-medium mb-1">{evt.title}</h5>
            <p className="text-neutral-400 text-sm">{evt.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
