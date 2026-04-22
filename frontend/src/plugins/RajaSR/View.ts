import {
  CustomSeriesPricePlotValues,
  ICustomSeriesPaneView,
  PaneRendererCustomData,
  Time,
  CustomSeriesWhitespaceData,
  IChartApi,
  ICustomSeriesPaneRenderer,
} from "lightweight-charts";
import { RajaSRData, RajaSROptions, defaultRajaSROptions } from "./types";
import { RajaSRRenderer } from "./Renderer";

export class RajaSRSeries implements ICustomSeriesPaneView<Time, any, RajaSROptions> {
  private _renderer: RajaSRRenderer;
  private _chartApi: IChartApi | null = null;

  constructor(chartApi?: IChartApi) {
    this._renderer = new RajaSRRenderer();
    if (chartApi) {
      this._chartApi = chartApi;
    }
  }

  priceValueBuilder(plotRow: RajaSRData): CustomSeriesPricePlotValues {
    return [plotRow.high, plotRow.low, plotRow.close];
  }

  isWhitespace(data: RajaSRData | CustomSeriesWhitespaceData<Time>): data is CustomSeriesWhitespaceData<Time> {
    return (data as Partial<RajaSRData>).close === undefined;
  }

  renderer(): ICustomSeriesPaneRenderer {
    if (this._chartApi) {
      this._renderer.timeToCoordinate = (time: Time) => {
        return this._chartApi!.timeScale().timeToCoordinate(time);
      };
    }
    return this._renderer;
  }

  update(data: PaneRendererCustomData<Time, any>, seriesOptions: RajaSROptions): void {
    // console.log("RajaSR update called", {
    //   dataLength: data.bars.length,
    //   visible: seriesOptions.visible
    // });
    this._renderer._data = data;
    this._renderer._options = seriesOptions;
  }

  setFullData(data: RajaSRData[]) {
    this._renderer.fullData = data;
    this._renderer.clearCache();
  }

  defaultOptions(): RajaSROptions {
    return defaultRajaSROptions;
  }
}