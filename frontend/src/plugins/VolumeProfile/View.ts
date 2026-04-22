import { CustomSeriesPricePlotValues, CustomSeriesWhitespaceData, ICustomSeriesPaneRenderer, ICustomSeriesPaneView, PaneRendererCustomData, Time } from 'lightweight-charts';
import { VolumeProfileData, VolumeProfileOptions, defaultVolumeProfileOptions } from './types';
import { VolumeProfileRenderer } from './Renderer';

export class VolumeProfileSeries implements ICustomSeriesPaneView<Time, VolumeProfileData, VolumeProfileOptions> {
    private _renderer = new VolumeProfileRenderer();

    renderer(): ICustomSeriesPaneRenderer {
        return this._renderer;
    }

    update(data: PaneRendererCustomData<Time, VolumeProfileData>, seriesOptions: VolumeProfileOptions): void {
        this._renderer._data = data;
        this._renderer._options = seriesOptions;
    }

    priceValueBuilder(plotRow: VolumeProfileData): CustomSeriesPricePlotValues {
        return [plotRow.high, plotRow.low, plotRow.close];
    }

    isWhitespace(data: VolumeProfileData | CustomSeriesWhitespaceData<Time>): data is CustomSeriesWhitespaceData<Time> {
        return (data as Partial<VolumeProfileData>).close === undefined;
    }

    defaultOptions(): VolumeProfileOptions {
        return defaultVolumeProfileOptions;
    }
}
