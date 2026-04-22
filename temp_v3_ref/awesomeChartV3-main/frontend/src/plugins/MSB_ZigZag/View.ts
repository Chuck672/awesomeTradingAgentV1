import {
  CustomSeriesPricePlotValues,
  ICustomSeriesPaneView,
  PaneRendererCustomData,
  Time,
  CustomSeriesWhitespaceData,
  IChartApi,
  ICustomSeriesPaneRenderer,
} from "lightweight-charts";
import { MSBZZData, MSBZZOptions, defaultMSBZZOptions } from "./types";
import { MSBZZRenderer } from "./Renderer";

export class MSBZZSeries implements ICustomSeriesPaneView<Time, any, MSBZZOptions> {
  private _renderer: MSBZZRenderer;
  private _chartApi: IChartApi | null = null;

  constructor(chartApi?: IChartApi) {
    this._renderer = new MSBZZRenderer();
    if (chartApi) {
      this._chartApi = chartApi;
    }
  }

  priceValueBuilder(plotRow: MSBZZData): CustomSeriesPricePlotValues {
    return [plotRow.close];
  }

  isWhitespace(data: MSBZZData | CustomSeriesWhitespaceData<Time>): data is CustomSeriesWhitespaceData<Time> {
    return (data as Partial<MSBZZData>).close === undefined;
  }

  renderer(): ICustomSeriesPaneRenderer {
    if (this._chartApi) {
      this._renderer.timeToCoordinate = (time: Time) => {
        return this._chartApi!.timeScale().timeToCoordinate(time);
      };
    }
    return this._renderer;
  }

  update(data: PaneRendererCustomData<Time, any>, seriesOptions: MSBZZOptions): void {
    this._renderer._data = data;
    this._renderer._options = { ...defaultMSBZZOptions, ...seriesOptions };
  }

  setFullData(data: MSBZZData[]) {
    this._renderer.fullData = data;
    this._renderer.clearCache();
  }

  defaultOptions(): MSBZZOptions {
    return defaultMSBZZOptions;
  }
}