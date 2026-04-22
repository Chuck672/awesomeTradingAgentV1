"use client";

import React from 'react';
import { MousePointer2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { DrawingToolType } from '../plugins/drawing-tools/core/types';

const IconTrendline = (props: React.SVGProps<SVGSVGElement>) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <circle cx="5" cy="19" r="2.5" />
    <circle cx="19" cy="5" r="2.5" />
    <line x1="6.8" y1="17.2" x2="17.2" y2="6.8" />
  </svg>
);

const IconHorizontalRay = (props: React.SVGProps<SVGSVGElement>) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <circle cx="4" cy="12" r="2.5" />
    <line x1="6.5" y1="12" x2="22" y2="12" />
  </svg>
);

const IconArrow = (props: React.SVGProps<SVGSVGElement>) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <circle cx="5" cy="19" r="2.5" />
    <circle cx="19" cy="5" r="2.5" />
    <line x1="6.8" y1="17.2" x2="15" y2="9" />
    <polygon points="19,5 12,7 17,12" fill="currentColor" stroke="currentColor" strokeWidth="1" strokeLinejoin="round" />
  </svg>
);

const IconHorizontalLine = (props: React.SVGProps<SVGSVGElement>) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <line x1="2" y1="12" x2="22" y2="12" />
  </svg>
);

const IconRectangle = (props: React.SVGProps<SVGSVGElement>) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <rect x="5" y="5" width="14" height="14" rx="1" />
    <circle cx="5" cy="5" r="2" fill="currentColor" />
    <circle cx="19" cy="5" r="2" fill="currentColor" />
    <circle cx="5" cy="19" r="2" fill="currentColor" />
    <circle cx="19" cy="19" r="2" fill="currentColor" />
  </svg>
);

const IconMeasure = (props: React.SVGProps<SVGSVGElement>) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <rect x="2" y="6" width="20" height="12" rx="2" transform="rotate(-45 12 12)" />
    <path d="M8.5 15.5l1.5-1.5" />
    <path d="M12 12l1.5-1.5" />
    <path d="M15.5 8.5l1.5-1.5" />
  </svg>
);

const IconLongPosition = (props: React.SVGProps<SVGSVGElement>) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <rect x="4" y="4" width="16" height="16" rx="2" fill="currentColor" fillOpacity="0.2" stroke="none" />
    <path d="M4 14.67h16v5.33H4z" fill="currentColor" fillOpacity="0.1" stroke="none" />
    <rect x="4" y="4" width="16" height="16" rx="2" />
    <line x1="4" y1="14.67" x2="20" y2="14.67" />
  </svg>
);

const IconShortPosition = (props: React.SVGProps<SVGSVGElement>) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M4 4h16v5.33H4z" fill="currentColor" fillOpacity="0.1" stroke="none" />
    <rect x="4" y="4" width="16" height="16" rx="2" fill="currentColor" fillOpacity="0.2" stroke="none" />
    <rect x="4" y="4" width="16" height="16" rx="2" />
    <line x1="4" y1="9.33" x2="20" y2="9.33" />
  </svg>
);

interface DrawingToolbarProps {
  activeTool: DrawingToolType;
  onToolChange: (tool: DrawingToolType) => void;
  theme?: 'dark' | 'light';
}

export function DrawingToolbar({ activeTool, onToolChange, theme = 'dark' }: DrawingToolbarProps) {
  const tools: { id: DrawingToolType; icon: React.ElementType; label: string }[] = [
    { id: 'cursor', icon: MousePointer2, label: 'Cursor' },
    { id: 'trendline', icon: IconTrendline, label: 'Trendline' },
    { id: 'arrow', icon: IconArrow, label: 'Arrow' },
    { id: 'horizontal_line', icon: IconHorizontalLine, label: 'Horizontal Line' },
    { id: 'horizontal_ray', icon: IconHorizontalRay, label: 'Horizontal Ray' },
    { id: 'rectangle', icon: IconRectangle, label: 'Rectangle' },
    { id: 'measure', icon: IconMeasure, label: 'Measure' },
    { id: 'long_position', icon: IconLongPosition, label: 'Long Position' },
    { id: 'short_position', icon: IconShortPosition, label: 'Short Position' },
  ];

  return (
    <div className={`absolute left-2 top-1/2 -translate-y-1/2 rounded-lg p-1 flex flex-col gap-1 z-50 shadow-lg ${theme === 'dark' ? 'bg-[#0b0f14] border border-[#2b2b43]' : 'bg-white border border-[#e0e3eb]'}`}>
      {tools.map(tool => {
        const Icon = tool.icon;
        const isActive = activeTool === tool.id;
        return (
          <button
            key={tool.id}
            className={cn(
              "w-8 h-8 rounded flex items-center justify-center transition-colors",
              isActive 
                ? (theme === 'dark' ? "bg-blue-600/20 text-blue-500" : "bg-blue-100 text-blue-600")
                : (theme === 'dark' ? "text-gray-400 hover:bg-[#2b2b43] hover:text-gray-200" : "text-gray-500 hover:bg-[#e0e3eb] hover:text-gray-900")
            )}
            onClick={() => onToolChange(tool.id)}
            title={tool.label}
          >
            <Icon size={20} />
          </button>
        );
      })}
    </div>
  );
}
