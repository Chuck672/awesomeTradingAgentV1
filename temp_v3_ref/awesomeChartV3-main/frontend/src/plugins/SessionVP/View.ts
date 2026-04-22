import { CustomSeriesPricePlotValues, CustomSeriesWhitespaceData, ICustomSeriesPaneRenderer, ICustomSeriesPaneView, PaneRendererCustomData, Time, IChartApi } from 'lightweight-charts';
import { SessionVPData, SessionVPOptions, defaultSessionVPOptions } from './types';
import { SessionVPRenderer } from './Renderer';

export class SessionVPSeries implements ICustomSeriesPaneView<Time, SessionVPData, SessionVPOptions> {
    private _renderer = new SessionVPRenderer();
    private _chartApi: IChartApi | null = null;

    constructor(chartApi?: IChartApi) {
        if (chartApi) {
            this._chartApi = chartApi;
        }
    }

    renderer(): ICustomSeriesPaneRenderer {
        if (this._chartApi) {
            this._renderer.timeToCoordinate = (time: Time) => {
                return this._chartApi!.timeScale().timeToCoordinate(time);
            };
        }
        return this._renderer;
    }

    update(data: PaneRendererCustomData<Time, SessionVPData>, seriesOptions: SessionVPOptions): void {
        this._renderer._data = data;
        this._renderer._options = seriesOptions;
    }

    setFullData(data: SessionVPData[]) {
        this._renderer.fullData = data;
        this._renderer.clearCache();
    }

    priceValueBuilder(plotRow: SessionVPData): CustomSeriesPricePlotValues {
        return [plotRow.high, plotRow.low, plotRow.close];
    }

    isWhitespace(data: SessionVPData | CustomSeriesWhitespaceData<Time>): data is CustomSeriesWhitespaceData<Time> {
        return (data as Partial<SessionVPData>).close === undefined;
    }

    defaultOptions(): SessionVPOptions {
        return defaultSessionVPOptions;
    }
}
