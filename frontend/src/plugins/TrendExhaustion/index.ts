import {
  CustomSeriesOptions,
  IChartApi,
  ISeriesApi,
} from "lightweight-charts";
import { View } from "./View";
import { TrendExhaustionOptions, TrendExhaustionData, defaultTrendExhaustionOptions } from "./types";

export type TrendExhaustionSeriesOptions = TrendExhaustionOptions & CustomSeriesOptions;

export class TrendExhaustionSeries {
  private _view: View;
  private _series: ISeriesApi<"Custom"> | null = null;
  private _chart: IChartApi;

  constructor(chart: IChartApi) {
    this._chart = chart;
    this._view = new View();
  }

  // MUST expose this so chart.addCustomSeries can find it on the instance!
  defaultOptions() {
    return defaultTrendExhaustionOptions;
  }

  // The rest of the custom series requirements:
  priceValueBuilder(plotRow: any) {
    return this._view.priceValueBuilder(plotRow);
  }

  isWhitespace(data: any) {
    return this._view.isWhitespace(data);
  }

  update(data: any, options: any) {
    this._view.update(data, options);
    if (this._view && this._view._renderer) {
      this._view._renderer.timeToCoordinate = (time: any) => {
        try {
          return this._chart.timeScale().timeToCoordinate(time);
        } catch {
          return null;
        }
      };
    }
  }

  renderer() {
    return this._view.renderer();
  }

  destroy() {
    this._view.destroy();
  }

  setFullData(data: TrendExhaustionData[]) {
    if (this._view && this._view._renderer) {
      this._view._renderer.setFullData(data);
    }
  }

  applyOptions(options: Partial<TrendExhaustionSeriesOptions>) {
    if (this._series) {
      this._series.applyOptions(options as any);
    }
  }
}

export * from "./types";
