import {
    CustomSeriesPricePlotValues,
    ICustomSeriesPaneRenderer,
    ICustomSeriesPaneView,
    PaneRendererCustomData,
    Time,
    CustomData,
    CustomSeriesOptions,
    CustomSeriesWhitespaceData,
    customSeriesDefaultOptions,
} from 'lightweight-charts';
import { CanvasRenderingTarget2D } from 'fancy-canvas';

export interface BubbleData extends CustomData<Time> {
    high: number;
    low: number;
    delta: number;
}

export interface BubbleSeriesOptions extends CustomSeriesOptions {
    minRadius: number;
    maxRadius: number;
}

export const defaultBubbleSeriesOptions: BubbleSeriesOptions = {
    ...customSeriesDefaultOptions,
    minRadius: 8,
    maxRadius: 30,
};

class BubbleSeriesRenderer implements ICustomSeriesPaneRenderer {
    _data: PaneRendererCustomData<Time, BubbleData> | null = null;
    _options: BubbleSeriesOptions | null = null;

    draw(target: CanvasRenderingTarget2D, priceConverter: (price: number) => number | null, isHovered: boolean, hitTestData?: unknown): void {
        if (!this._data || !this._options || !this._data.visibleRange) return;

        target.useMediaCoordinateSpace((scope) => {
            const ctx = scope.context;
            const { bars, visibleRange } = this._data!;
            const { minRadius, maxRadius } = this._options!;
            
            if (!visibleRange) return;

            // Calculate max absolute delta for scaling
            let maxDelta = 0;
            for (let i = visibleRange.from; i < visibleRange.to; i++) {
                const bar = bars[i];
                if (bar && bar.originalData && bar.originalData.delta !== undefined) {
                    maxDelta = Math.max(maxDelta, Math.abs(bar.originalData.delta));
                }
            }

            if (maxDelta === 0) maxDelta = 1; // Avoid division by zero

            ctx.save();
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.font = 'bold 10px Arial';

            for (let i = visibleRange.from; i < visibleRange.to; i++) {
                const bar = bars[i];
                if (!bar || !bar.originalData || bar.originalData.delta === undefined) continue;

                const data = bar.originalData as BubbleData;
                const x = bar.x;
                const price = (data.high + data.low) / 2;
                const y = priceConverter(price);

                if (y === null) continue;

                const delta = data.delta;
                const absDelta = Math.abs(delta);
                const radius = minRadius + (absDelta / maxDelta) * (maxRadius - minRadius);

                // Draw bubble
                ctx.beginPath();
                ctx.arc(x, y, radius, 0, 2 * Math.PI);
                ctx.fillStyle = delta >= 0 ? 'rgba(0, 255, 136, 0.4)' : 'rgba(255, 68, 68, 0.4)';
                ctx.fill();

                // Draw text
                ctx.fillStyle = '#ffffff';
                ctx.fillText(delta.toString(), x, y);
            }

            ctx.restore();
        });
    }
}

export class BubbleSeries implements ICustomSeriesPaneView<Time, BubbleData, BubbleSeriesOptions> {
    private _renderer = new BubbleSeriesRenderer();

    renderer(): ICustomSeriesPaneRenderer {
        return this._renderer;
    }

    update(data: PaneRendererCustomData<Time, BubbleData>, seriesOptions: BubbleSeriesOptions): void {
        this._renderer._data = data;
        this._renderer._options = seriesOptions;
    }

    priceValueBuilder(plotRow: BubbleData): CustomSeriesPricePlotValues {
        return [plotRow.high, plotRow.low, (plotRow.high + plotRow.low) / 2];
    }

    isWhitespace(data: BubbleData | CustomSeriesWhitespaceData<Time>): data is CustomSeriesWhitespaceData<Time> {
        return (data as Partial<BubbleData>).delta === undefined;
    }

    defaultOptions(): BubbleSeriesOptions {
        return defaultBubbleSeriesOptions;
    }
}
