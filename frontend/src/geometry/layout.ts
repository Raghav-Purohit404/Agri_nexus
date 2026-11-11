import type { AllocationItem, Layout, PlotDTO, Zone } from '../api/types';
import { mpArea, partitionMP, toMP, unassignedMP } from './geom';

let nextId = 0;
const id = () => `zone-${++nextId}`;

/** Convert explicitly supplied area allocations into disjoint drawable zones. */
export function areasToLayout(plot: PlotDTO, allocations: AllocationItem[], locked: Zone[] = []): Layout {
  const plotMp = toMP(plot.boundaryFt);
  const lockedMp = locked.length ? locked.map((z) => z.geometryFt) : [];
  let available = unassignedMP(plotMp, locked.map((zone) => ({ id: zone.id, mp: zone.geometryFt })) as never);
  const accepted: { item: AllocationItem; area: number }[] = [];
  const freeArea = mpArea(available);
  let requested = allocations.reduce((sum, a) => sum + a.areaSqft, 0);
  const scale = requested > freeArea && requested > 0 ? freeArea / requested : 1;
  for (const item of allocations) {
    const area = item.areaSqft * scale;
    if (area > 1e-4) accepted.push({ item, area });
  }
  const zones: Zone[] = [...locked];
  if (accepted.length) {
    const assignedArea = accepted.reduce((sum, item) => sum + item.area, 0);
    const leftover = Math.max(0, freeArea - assignedArea);
    const allParts = partitionMP(available, [...accepted.map((a) => a.area), ...(leftover > 1e-6 ? [leftover] : [])], 0);
    const parts = allParts.slice(0, accepted.length);
    accepted.forEach(({ item }, index) => zones.push({
      id: id(), kind: item.kind, ...(item.cropId ? { cropId: item.cropId } : {}),
      irrigation: item.irrigation, geometryFt: parts[index]!, ...(item.amendment ? { amendment: item.amendment } : {}),
    }));
    // Any remaining area is intentionally unassigned and stays as the base field.
  }
  return { plotId: plot.id, zones };
}
