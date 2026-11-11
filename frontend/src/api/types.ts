import type { MultiPolygon, Point } from '../geometry/geom';

export type LandUse = 'crop' | 'fallow' | 'reclaim' | 'pv' | 'agrivoltaic' | 'water';
export type IrrigationKind = 'none' | 'flood' | 'drip' | 'sprinkler';
export interface Irrigation {
  kind: IrrigationKind;
  rowSpacingFt?: number;
  emitterSpacingFt?: number;
  rowAngleDeg?: number;
}
export interface PlotDTO {
  id: string;
  name: string;
  boundaryFt: Point[];
  areaSqft: number;
  position?: { xFt: number; yFt: number; rotationDeg?: number };
  eligibleUses: LandUse[];
  soilSummary?: Record<string, string | number>;
}
export interface CropOption {
  id: string;
  name: string;
  nameHi?: string;
  status: 'validated' | 'placeholder';
  irrigationOptions: IrrigationKind[];
  minZoneSqft?: number;
  note?: string;
  pattern: string;
}
export interface Zone {
  id: string;
  kind: LandUse;
  cropId?: string;
  irrigation: Irrigation;
  geometryFt: MultiPolygon;
  locked?: boolean;
  amendment?: string;
}
export interface Layout {
  plotId: string;
  zones: Zone[];
}
export interface AllocationItem {
  kind: LandUse;
  cropId?: string;
  areaSqft: number;
  irrigation: Irrigation;
  amendment?: string;
}
export interface Dist { mean: number; p05: number; p50: number; p95: number }
export interface PlotResult {
  plotId: string;
  name: string;
  areaSqft: number;
  allocation: AllocationItem[];
  kpis: { expectedProfitInr: Dist; worst20ProfitInr: number; waterUseM3: number };
}
export interface Driver {
  code: 'WATER_LIMIT' | 'DRIP_SAVES' | 'SALINITY' | 'PRICE' | 'RISK' | 'PLACEHOLDER_CROP' | 'DATA_GAP' | 'CAPEX';
  plotId?: string;
  params: Record<string, string | number>;
}
export interface OptimizationResult {
  jobId: string;
  status: 'queued' | 'running' | 'done' | 'failed';
  plots: PlotResult[];
  property: {
    expectedProfitInr: Dist;
    worst20ProfitInr: number;
    waterUseM3: number;
    waterSupplyM3?: number;
    capexInr?: number;
  };
  drivers: Driver[];
  stability: { topAllocationFrequency: number; resamples: number };
  alternatives?: { label: 'safest' | 'balanced' | 'highest_profit'; riskLambda: number; plots?: PlotResult[] }[];
  warnings: { level: 'info' | 'warn' | 'error'; code: string; text: string }[];
  fidelityFlags: string[];
  fixture?: boolean;
}

export interface ScenarioPayload {
  layouts: Layout[];
  horizonYears: number;
}
