import { CustomSeriesOptions, customSeriesDefaultOptions, CustomData, Time } from 'lightweight-charts';

export interface VolumeProfileData extends CustomData<Time> {
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface VolumeProfileOptions extends CustomSeriesOptions {
  placement: 'left' | 'right';
  width: number; // percentage of chart width
  bins: number;
  upColor: string;
  downColor: string;
  valueAreaUpColor: string;
  valueAreaDownColor: string;
  pocColor: string;
  valueAreaPercentage: number;
}

export const defaultVolumeProfileOptions: VolumeProfileOptions = {
  ...customSeriesDefaultOptions,
  placement: 'right',
  width: 25,
  bins: 70,
  upColor: 'rgba(0, 191, 165, 0.2)',
  downColor: 'rgba(255, 68, 68, 0.2)',
  valueAreaUpColor: 'rgba(0, 191, 165, 0.6)',
  valueAreaDownColor: 'rgba(255, 68, 68, 0.6)',
  pocColor: '#FFD700',
  valueAreaPercentage: 70,
};

export interface ProfileBin {
  yStart: number;
  yEnd: number;
  volumeUp: number;
  volumeDown: number;
  totalVolume: number;
  inValueArea: boolean;
}

export interface ProfileResult {
  bins: ProfileBin[];
  pocPrice: number;
  pocVolume: number;
  maxVolume: number;
  valueAreaLow: number;
  valueAreaHigh: number;
}
