"use client";

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Plus } from 'lucide-react';
import { createPortal } from 'react-dom';

interface ColorPickerProps {
  color: string;
  onChange: (color: string) => void;
  theme: 'dark' | 'light';
}

function parseColor(color: string): { hex: string, opacity: number } {
  if (!color || color === 'transparent') return { hex: '#000000', opacity: 0 };
  
  if (color.startsWith('rgba')) {
    const match = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
    if (match) {
      const r = parseInt(match[1], 10).toString(16).padStart(2, '0');
      const g = parseInt(match[2], 10).toString(16).padStart(2, '0');
      const b = parseInt(match[3], 10).toString(16).padStart(2, '0');
      const a = match[4] ? parseFloat(match[4]) : 1;
      return { hex: `#${r}${g}${b}`, opacity: Math.round(a * 100) };
    }
  }
  
  if (color.startsWith('#')) {
    if (color.length === 9) {
      const hex = color.slice(0, 7);
      const a = parseInt(color.slice(7, 9), 16) / 255;
      return { hex, opacity: Math.round(a * 100) };
    } else if (color.length === 5) {
      const r = color[1] + color[1];
      const g = color[2] + color[2];
      const b = color[3] + color[3];
      const a = parseInt(color[4] + color[4], 16) / 255;
      return { hex: `#${r}${g}${b}`, opacity: Math.round(a * 100) };
    }
    if (color.length === 4) {
      const r = color[1] + color[1];
      const g = color[2] + color[2];
      const b = color[3] + color[3];
      return { hex: `#${r}${g}${b}`, opacity: 100 };
    }
    return { hex: color.slice(0, 7), opacity: 100 };
  }
  
  return { hex: '#000000', opacity: 100 };
}

function toRgba(hex: string, opacity: number): string {
  if (!hex.startsWith('#')) return hex;
  let r = 0, g = 0, b = 0;
  if (hex.length === 7) {
    r = parseInt(hex.slice(1, 3), 16);
    g = parseInt(hex.slice(3, 5), 16);
    b = parseInt(hex.slice(5, 7), 16);
  }
  return `rgba(${r}, ${g}, ${b}, ${opacity / 100})`;
}

const PRESET_COLORS = [
  // Grays
  ["#ffffff", "#e0e0e0", "#c2c2c2", "#9e9e9e", "#757575", "#616161", "#424242", "#212121", "#111111", "#000000"],
  // Base Hues
  ["#ff5252", "#ff9800", "#ffeb3b", "#4caf50", "#00bfa5", "#00bcd4", "#2196f3", "#2962ff", "#9c27b0", "#e91e63"],
  // Lightest
  ["#ffebee", "#fff3e0", "#fffde7", "#e8f5e9", "#e0f2f1", "#e0f7fa", "#e3f2fd", "#e8eaf6", "#f3e5f5", "#fce4ec"],
  // Lighter
  ["#ffcdd2", "#ffe082", "#fff59d", "#c8e6c9", "#b2dfdb", "#b2ebf2", "#bbdefb", "#c5cae9", "#e1bee7", "#f8bbd0"],
  // Light
  ["#ef9a9a", "#ffcc80", "#fff176", "#a5d6a7", "#80cbc4", "#80deea", "#90caf9", "#9fa8da", "#ce93d8", "#f48fb1"],
  // Dark
  ["#e53935", "#f57c00", "#fbc02d", "#388e3c", "#00897b", "#0097a7", "#1e88e5", "#3949ab", "#8e24aa", "#d81b60"],
  // Darker
  ["#c62828", "#e65100", "#f9a825", "#2e7d32", "#00695c", "#00838f", "#1565c0", "#283593", "#6a1b9a", "#c2185b"],
  // Darkest
  ["#b71c1c", "#bf360c", "#f57f17", "#1b5e20", "#004d40", "#006064", "#0d47a1", "#1a237e", "#4a148c", "#880e4f"]
];

export function ColorPicker({ color, onChange, theme }: ColorPickerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const buttonRef = useRef<HTMLDivElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const [coords, setCoords] = useState({ top: 0, left: 0 });
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const updatePosition = useCallback(() => {
    if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      const popoverHeight = 320; // Approximate height of the color picker
      const popoverWidth = 260; // Approximate width

      let top = rect.bottom + 8;
      // If there is not enough space below, show it above the button
      if (top + popoverHeight > window.innerHeight) {
        top = rect.top - popoverHeight - 8;
      }

      setCoords({
        top: top > 0 ? top : 10, // Ensure it doesn't go off the top edge
        left: rect.right - popoverWidth,
      });
    }
  }, []);
  
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        buttonRef.current && !buttonRef.current.contains(event.target as Node) &&
        popoverRef.current && !popoverRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      
      // Update position on scroll or resize
      window.addEventListener('resize', updatePosition);
      window.addEventListener('scroll', updatePosition, true);
      
      // Also update position immediately when opened
      updatePosition();

      return () => {
        document.removeEventListener('mousedown', handleClickOutside);
        window.removeEventListener('resize', updatePosition);
        window.removeEventListener('scroll', updatePosition, true);
      };
    }
  }, [isOpen, updatePosition]);

  const bgColor = theme === 'dark' ? '#1e222d' : '#ffffff';
  const borderColor = theme === 'dark' ? '#2B2B43' : '#e0e3eb';
  const textColor = theme === 'dark' ? '#d1d4dc' : '#131722';

  const { hex, opacity } = parseColor(color);
  const checkerboard = `url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="4" height="4" fill="%23404040"/><rect x="4" y="4" width="4" height="4" fill="%23404040"/><rect x="4" width="4" height="4" fill="%23202020"/><rect y="4" width="4" height="4" fill="%23202020"/></svg>')`;

  const handleOpen = () => {
    updatePosition();
    setIsOpen(!isOpen);
  };

  if (!mounted) return null;

  return (
    <>
      {/* Trigger Button */}
      <div 
        ref={buttonRef}
        className="w-6 h-6 rounded cursor-pointer border"
        style={{ backgroundColor: color || 'transparent', borderColor }}
        onClick={handleOpen}
      />

      {/* Popover Portal */}
      {isOpen && createPortal(
        <div 
          ref={popoverRef}
          className="fixed z-[100] p-3 rounded-lg shadow-xl flex flex-col gap-3"
          style={{ 
            top: coords.top, 
            left: coords.left > 0 ? coords.left : 10,
            backgroundColor: bgColor, 
            border: `1px solid ${borderColor}` 
          }}
        >
          {/* Color Grid */}
          <div className="flex flex-col gap-1">
            {PRESET_COLORS.map((row, rowIndex) => (
              <div key={rowIndex} className="flex gap-1">
                {row.map((c, colIndex) => (
                  <div
                    key={`${rowIndex}-${colIndex}`}
                    className="w-[22px] h-[22px] rounded-[2px] cursor-pointer hover:scale-110 transition-transform relative flex items-center justify-center"
                    style={{ backgroundColor: c }}
                    onClick={() => {
                      onChange(toRgba(c, opacity));
                      // setIsOpen(false); // Do not close immediately so user can adjust opacity
                    }}
                  >
                    {hex.toLowerCase() === c.toLowerCase() && (
                      <div className="absolute inset-0 rounded-[2px] border-2 border-white mix-blend-difference" />
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>

          <div className="h-px w-full" style={{ backgroundColor: borderColor }} />

          {/* Custom Color Input */}
          <div className="flex items-center gap-2">
            <div className="relative w-6 h-6 rounded flex items-center justify-center border border-dashed hover:opacity-80" style={{ borderColor }}>
              <Plus size={14} color={textColor} />
              <input 
                type="color" 
                value={hex} 
                onChange={(e) => onChange(toRgba(e.target.value, opacity))}
                className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
              />
            </div>
            <span className="text-xs" style={{ color: textColor }}>自定义颜色</span>
          </div>

          <div className="h-px w-full" style={{ backgroundColor: borderColor }} />

          {/* Opacity Slider */}
          <div className="flex flex-col gap-2">
            <span className="text-xs" style={{ color: textColor }}>不透明度 (Opacity)</span>
            <div className="flex items-center gap-3">
              <div 
                className="flex-1 h-3 rounded-full relative"
                style={{
                  backgroundImage: checkerboard,
                  border: `1px solid ${borderColor}`,
                }}
              >
                <div 
                  className="absolute inset-0 rounded-full pointer-events-none"
                  style={{ background: `linear-gradient(to right, transparent, ${hex})` }}
                />
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={opacity}
                  onChange={(e) => onChange(toRgba(hex, parseInt(e.target.value, 10)))}
                  className="w-full h-full opacity-0 cursor-pointer absolute inset-0 z-10"
                />
                {/* Thumb Container */}
                <div className="absolute inset-0 px-2 pointer-events-none">
                  <div className="relative w-full h-full">
                    <div 
                      className="absolute top-1/2 -translate-y-1/2 flex items-center justify-center"
                      style={{ 
                        left: `${opacity}%`,
                        transform: 'translate(-50%, -50%)',
                        filter: 'drop-shadow(0px 1px 2px rgba(0,0,0,0.4))'
                      }}
                    >
                      <svg width="12" height="12" viewBox="0 0 12 12" className="overflow-visible">
                        <path 
                          d="M1,2 L11,2 L6,10 Z" 
                          fill={hex} 
                          stroke="white" 
                          strokeWidth="1.5"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </div>
                  </div>
                </div>
              </div>
              <div className="text-xs w-10 text-center rounded border py-0.5" style={{ color: textColor, borderColor }}>
                {opacity}%
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
