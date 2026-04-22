"use client";

import React, { useState, useEffect } from 'react';
import { X, Trash2 } from 'lucide-react';
import { BaseDrawing } from '../plugins/drawing-tools/core/base-drawing';
import { BaseDrawingStyle } from '../plugins/drawing-tools/core/types';
import { ColorPicker } from './color-picker';

interface DrawingSettingsModalProps {
  drawing: BaseDrawing;
  theme: 'dark' | 'light';
  onClose: () => void;
  onDelete: () => void;
  onChange: () => void;
}

export function DrawingSettingsModal({ drawing, theme, onClose, onDelete, onChange }: DrawingSettingsModalProps) {
  const [style, setStyle] = useState<BaseDrawingStyle>(drawing.getStyle());

  useEffect(() => {
    setStyle(drawing.getStyle());
  }, [drawing]);

  const handleChange = (newStyle: Partial<BaseDrawingStyle>) => {
    const updated = { ...style, ...newStyle };
    setStyle(updated);
    drawing.updateStyle(updated);
    onChange();
  };

  const isDark = theme === 'dark';
  const bgColor = isDark ? 'bg-[#1e222d]' : 'bg-white';
  const borderColor = isDark ? 'border-[#2b2b43]' : 'border-gray-200';
  const textColor = isDark ? 'text-white' : 'text-gray-900';
  const labelColor = isDark ? 'text-[#787b86]' : 'text-gray-500';
  const inputBg = isDark ? 'bg-[#2b2b43]' : 'bg-gray-100';

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center pointer-events-none">
      <div className={`${bgColor} border ${borderColor} rounded-lg shadow-2xl p-4 w-72 pointer-events-auto`}>
        <div className="flex justify-between items-center mb-4">
          <h3 className={`${textColor} font-medium capitalize`}>{drawing.toolType} Settings</h3>
          <div className="flex gap-2">
            <button onClick={onDelete} className={`${labelColor} hover:text-red-500 transition-colors`}>
              <Trash2 size={18} />
            </button>
            <button onClick={onClose} className={`${labelColor} hover:${textColor} transition-colors`}>
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="space-y-4">
          <div className="flex items-center gap-4">
             <div className="flex-1">
               <label className={`text-xs ${labelColor} mb-1 block`}>Line Color</label>
               <ColorPicker
                  color={style.lineColor}
                  onChange={(color) => handleChange({ lineColor: color })}
                  theme={theme}
               />
             </div>
             <div className="flex-1">
               <label className={`text-xs ${labelColor} mb-1 block`}>Line Width</label>
               <select
                  value={style.lineWidth}
                  onChange={(e) => handleChange({ lineWidth: Number(e.target.value) })}
                  className={`w-full ${inputBg} ${textColor} text-sm rounded px-2 py-1.5 outline-none border-none`}
               >
                  <option value={1}>1px</option>
                  <option value={2}>2px</option>
                  <option value={3}>3px</option>
                  <option value={4}>4px</option>
               </select>
             </div>
          </div>

          <div className="flex items-center gap-4">
             <div className="flex-1">
               <label className={`text-xs ${labelColor} mb-1 block`}>Line Style</label>
               <select
                  value={style.lineStyle}
                  onChange={(e) => handleChange({ lineStyle: e.target.value as any })}
                  className={`w-full ${inputBg} ${textColor} text-sm rounded px-2 py-1.5 outline-none border-none`}
               >
                  <option value="solid">Solid</option>
                  <option value="dashed">Dashed</option>
                  <option value="dotted">Dotted</option>
               </select>
             </div>
          </div>
          
          {drawing.toolType === 'trendline' && (
            <div className="flex items-center gap-4 pt-2 border-t border-[#2b2b43]">
              <label className={`flex items-center gap-2 text-sm ${textColor} cursor-pointer`}>
                <input
                  type="checkbox"
                  checked={(style as any).extendLeft || false}
                  onChange={(e) => handleChange({ extendLeft: e.target.checked } as any)}
                  className={`rounded ${borderColor} bg-transparent`}
                />
                Extend Left
              </label>
              <label className={`flex items-center gap-2 text-sm ${textColor} cursor-pointer`}>
                <input
                  type="checkbox"
                  checked={(style as any).extendRight || false}
                  onChange={(e) => handleChange({ extendRight: e.target.checked } as any)}
                  className={`rounded ${borderColor} bg-transparent`}
                />
                Extend Right
              </label>
            </div>
          )}

          {drawing.toolType === 'horizontal_ray' && (
            <div className="flex items-center gap-4 pt-2 border-t border-[#2b2b43]">
               <div className="flex-1">
                 <label className={`text-xs ${labelColor} mb-1 block`}>Direction</label>
                 <select
                    value={(style as any).direction || 'right'}
                    onChange={(e) => handleChange({ direction: e.target.value as any } as any)}
                    className={`w-full ${inputBg} ${textColor} text-sm rounded px-2 py-1.5 outline-none border-none`}
                 >
                    <option value="right">Right</option>
                    <option value="left">Left</option>
                 </select>
               </div>
            </div>
          )}

          {drawing.toolType === 'arrow' && (
             <div className="flex items-center gap-4 pt-2 border-t border-[#2b2b43]">
               <div className="flex-1">
                 <label className={`text-xs ${labelColor} mb-1 block`}>Arrow Size</label>
                 <input
                    type="range"
                    min="5"
                    max="30"
                    value={(style as any).arrowSize || 12}
                    onChange={(e) => handleChange({ arrowSize: Number(e.target.value) } as any)}
                    className="w-full accent-blue-500"
                 />
               </div>
             </div>
          )}

          {drawing.toolType === 'rectangle' && (
             <div className="flex flex-col gap-4 pt-2 border-t border-[#2b2b43]">
               <div className="flex items-center gap-4">
                 <div className="flex-1">
                   <label className={`text-xs ${labelColor} mb-1 block`}>Fill Color</label>
                   <ColorPicker
                      color={(style as any).fillColor || '#2962FF'}
                      onChange={(color) => handleChange({ fillColor: color } as any)}
                      theme={theme}
                   />
                 </div>
                 <div className="flex-1">
                   <label className={`text-xs ${labelColor} mb-1 block`}>Fill Opacity</label>
                   <input
                      type="range"
                      min="0"
                      max="100"
                      value={((style as any).fillOpacity ?? 0.2) * 100}
                      onChange={(e) => handleChange({ fillOpacity: Number(e.target.value) / 100 } as any)}
                      className="w-full accent-blue-500"
                   />
                 </div>
               </div>
             </div>
          )}

          {(drawing.toolType === 'measure' || drawing.toolType === 'long_position' || drawing.toolType === 'short_position') && (
             <div className="flex flex-col gap-4 pt-2 border-t border-[#2b2b43]">
               <div className="flex items-center gap-4">
                 <div className="flex-1">
                   <label className={`text-xs ${labelColor} mb-1 block`}>{drawing.toolType === 'measure' ? 'Up Color' : 'Target Color'}</label>
                   <ColorPicker
                      color={(style as any).fillColorUp || (style as any).targetColor || '#00BCD4'}
                      onChange={(color) => handleChange(drawing.toolType === 'measure' ? { fillColorUp: color } as any : { targetColor: color } as any)}
                      theme={theme}
                   />
                 </div>
                 <div className="flex-1">
                   <label className={`text-xs ${labelColor} mb-1 block`}>{drawing.toolType === 'measure' ? 'Down Color' : 'Stop Color'}</label>
                   <ColorPicker
                      color={(style as any).fillColorDown || (style as any).stopColor || '#FF5252'}
                      onChange={(color) => handleChange(drawing.toolType === 'measure' ? { fillColorDown: color } as any : { stopColor: color } as any)}
                      theme={theme}
                   />
                 </div>
               </div>
               <div className="flex-1">
                   <label className={`text-xs ${labelColor} mb-1 block`}>Background Opacity</label>
                   <input
                      type="range"
                      min="0"
                      max="100"
                      value={((style as any).fillOpacity ?? 0.2) * 100}
                      onChange={(e) => handleChange({ fillOpacity: Number(e.target.value) / 100 } as any)}
                      className="w-full accent-blue-500"
                   />
               </div>
             </div>
          )}

        </div>
      </div>
    </div>
  );
}
