import {
  ICustomSeriesPaneView,
  PaneRendererCustomData,
  Time,
  CustomData,
} from "lightweight-charts";
import { Renderer } from "./Renderer";
import { defaultTrendExhaustionOptions, TrendExhaustionOptions, TrendExhaustionData } from "./types";

export class View implements ICustomSeriesPaneView<Time, TrendExhaustionData, TrendExhaustionOptions> {
  _renderer: Renderer;

  constructor() {
    this._renderer = new Renderer();
  }

  priceValueBuilder(plotRow: TrendExhaustionData): number[] {
    return [plotRow.close];
  }

  isWhitespace(data: TrendExhaustionData | CustomData<Time>): data is CustomData<Time> {
    return (data as TrendExhaustionData).close === undefined;
  }

  update(data: PaneRendererCustomData<Time, any>, seriesOptions: TrendExhaustionOptions): void {
    this._renderer._data = data;
    this._renderer._options = { ...defaultTrendExhaustionOptions, ...seriesOptions };
  }

  renderer(): Renderer {
    return this._renderer;
  }

  destroy(): void {}
  defaultOptions() { return defaultTrendExhaustionOptions; }
}
