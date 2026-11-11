import polygonClipping from 'polygon-clipping';

export type Point = [number, number];
export type Ring = Point[];
export type Polygon = Ring[];
export type MultiPolygon = Polygon[];
export const SQFT_PER_SQM = 10.763910416709722;

const clip = polygonClipping as unknown as {
  intersection: (...geometries: MultiPolygon[]) => MultiPolygon;
  union: (...geometries: MultiPolygon[]) => MultiPolygon;
  difference: (subject: MultiPolygon, ...clips: MultiPolygon[]) => MultiPolygon;
};

export function ringArea(ring: Ring): number {
  let sum = 0;
  for (let i = 0; i < ring.length; i += 1) {
    const [x1, y1] = ring[i]!;
    const [x2, y2] = ring[(i + 1) % ring.length]!;
    sum += x1 * y2 - x2 * y1;
  }
  return sum / 2;
}

export function ensureCCW(ring: Ring): Ring {
  return ringArea(ring) < 0 ? [...ring].reverse() : [...ring];
}

export function mpArea(mp: MultiPolygon): number {
  let area = 0;
  for (const polygon of mp) {
    polygon.forEach((ring, index) => {
      area += (index === 0 ? 1 : -1) * Math.abs(ringArea(ring.slice(0, -1)));
    });
  }
  return area;
}

export function toMP(ring: Ring): MultiPolygon {
  if (ring.length < 3) return [];
  const points = ensureCCW(ring);
  return [[[...points, [...points[0]!] as Point]]];
}

export function bbox(points: Point[]): [number, number, number, number] {
  if (!points.length) return [0, 0, 0, 0];
  return points.reduce<[number, number, number, number]>(
    ([minX, minY, maxX, maxY], [x, y]) => [Math.min(minX, x), Math.min(minY, y), Math.max(maxX, x), Math.max(maxY, y)],
    [Infinity, Infinity, -Infinity, -Infinity],
  );
}

export function rotate(point: Point, angle: number): Point {
  const cos = Math.cos(angle), sin = Math.sin(angle);
  return [point[0] * cos - point[1] * sin, point[0] * sin + point[1] * cos];
}

export function rotMP(mp: MultiPolygon, angle: number): MultiPolygon {
  return mp.map((polygon) => polygon.map((ring) => ring.map((point) => rotate(point as Point, angle))));
}

export function longestEdgeAngle(ring: Ring): number {
  let best = -1, angle = 0;
  for (let i = 0; i < ring.length; i += 1) {
    const a = ring[i]!, b = ring[(i + 1) % ring.length]!;
    const distance = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (distance > best) { best = distance; angle = Math.atan2(b[1] - a[1], b[0] - a[0]); }
  }
  return angle;
}

function halfPlane(mp: MultiPolygon, angle: number, t: number, keepLess: boolean): MultiPolygon {
  if (!mp.length) return [];
  const rotated = rotMP(mp, -angle);
  const [x0, y0, x1, y1] = bbox(rotated.flat(2) as Point[]);
  const pad = Math.max(10, x1 - x0, y1 - y0);
  const box: Ring = keepLess
    ? [[x0 - pad, y0 - pad], [t, y0 - pad], [t, y1 + pad], [x0 - pad, y1 + pad], [x0 - pad, y0 - pad]]
    : [[t, y0 - pad], [x1 + pad, y0 - pad], [x1 + pad, y1 + pad], [t, y1 + pad], [t, y0 - pad]];
  const clipped = clip.intersection(rotated, [[box]]);
  return rotMP(clipped, angle);
}

export function splitAt(mp: MultiPolygon, angle: number, offset: number): [MultiPolygon, MultiPolygon] {
  return [halfPlane(mp, angle, offset, true), halfPlane(mp, angle, offset, false)];
}

export function splitByLine(mp: MultiPolygon, p: Point, q: Point): [MultiPolygon, MultiPolygon] {
  const dx = q[0] - p[0], dy = q[1] - p[1];
  if (Math.hypot(dx, dy) < 1e-9) return [mp, []];
  const normalAngle = Math.atan2(dy, dx) + Math.PI / 2;
  const offset = p[0] * Math.cos(normalAngle) + p[1] * Math.sin(normalAngle);
  return splitAt(mp, normalAngle, offset);
}

export function partitionMP(mpIn: MultiPolygon, areas: number[], angle: number): MultiPolygon[] {
  const total = mpArea(mpIn), sum = areas.reduce((acc, value) => acc + value, 0);
  if (!Number.isFinite(total) || total <= 0 || areas.length === 0 || areas.some((value) => value <= 0) || sum <= 0) {
    throw new Error('Partition requires a positive plot and positive requested areas.');
  }
  let remaining = mpIn;
  const scale = total / sum;
  const parts: MultiPolygon[] = [];
  for (const area of areas.slice(0, -1)) {
    const target = area * scale;
    const rotated = rotMP(remaining, -angle);
    const [x0, , x1] = bbox(rotated.flat(2) as Point[]);
    let low = x0, high = x1;
    for (let i = 0; i < 60; i += 1) {
      const middle = (low + high) / 2;
      if (mpArea(halfPlane(remaining, angle, middle, true)) < target) low = middle;
      else high = middle;
    }
    const threshold = (low + high) / 2;
    parts.push(halfPlane(remaining, angle, threshold, true));
    remaining = halfPlane(remaining, angle, threshold, false);
  }
  parts.push(remaining);
  return parts;
}

export function partitionByAreas(ring: Ring, areas: number[], angle = longestEdgeAngle(ring)): MultiPolygon[] {
  return partitionMP(toMP(ring), areas, angle);
}

export function dripRows(mp: MultiPolygon, spacing: number, angle = 0, inset = 0.5): { rows: [Point, Point][]; totalLength: number } {
  if (spacing <= 0 || inset < 0) throw new Error('Drip spacing must be positive and inset non-negative.');
  if (!mp.length) return { rows: [], totalLength: 0 };
  const rotated = rotMP(mp, -angle);
  const [x0, y0, x1, y1] = bbox(rotated.flat(2) as Point[]);
  const rows: [Point, Point][] = [];
  let totalLength = 0;
  for (let y = y0 + inset; y < y1 - 1e-9; y += spacing) {
    const xs: number[] = [];
    for (const polygon of rotated) for (const ring of polygon) {
      for (let i = 0; i < ring.length - 1; i += 1) {
        const [ax, ay] = ring[i]! as Point, [bx, by] = ring[i + 1]! as Point;
        if ((ay <= y) === (by <= y)) continue;
        xs.push(ax + ((y - ay) * (bx - ax)) / (by - ay));
      }
    }
    xs.sort((a, b) => a - b);
    for (let i = 0; i + 1 < xs.length; i += 2) {
      const start = xs[i]! + inset, end = xs[i + 1]! - inset;
      if (end - start > 0.25) {
        rows.push([rotate([start, y], angle), rotate([end, y], angle)]);
        totalLength += end - start;
      }
    }
  }
  return { rows, totalLength };
}

export function emittersFor(totalLengthFt: number, emitterSpacingFt: number): number {
  if (emitterSpacingFt <= 0) throw new Error('Emitter spacing must be positive.');
  return Math.floor(totalLengthFt / emitterSpacingFt);
}

export function pointInRing(point: Point, ring: Ring): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const [xi, yi] = ring[i]!, [xj, yj] = ring[j]!;
    if ((yi > point[1]) !== (yj > point[1]) && point[0] < ((xj - xi) * (point[1] - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

export function pointInMP(point: Point, mp: MultiPolygon): boolean {
  return mp.some((polygon) => pointInRing(point, polygon[0]!.slice(0, -1) as Point[]) &&
    !polygon.slice(1).some((hole) => pointInRing(point, hole.slice(0, -1) as Point[])));
}

export const snap = (value: number, grid: number): number => grid ? Math.round(value / grid) * grid : value;

export interface PaintZone { id: string; kind: string; cropId?: string; irrigation?: { kind: string; rowSpacingFt?: number; emitterSpacingFt?: number; rowAngleDeg?: number }; mp: MultiPolygon; locked?: boolean }

export function paintRegion(plotMP: MultiPolygon, zones: PaintZone[], drawnRing: Ring, target: PaintZone): PaintZone[] {
  if (drawnRing.length < 3) return zones;
  let drawn = clip.intersection(plotMP, toMP(drawnRing));
  const locked = zones.filter((zone) => zone.locked).map((zone) => zone.mp);
  if (locked.length && drawn.length) drawn = clip.difference(drawn, ...locked);
  if (!drawn.length) return zones;
  const next = zones.map((zone) => ({
    ...zone, mp: zone.locked ? zone.mp : clip.difference(zone.mp, drawn),
  })).filter((zone) => mpArea(zone.mp) > 0.01);
  const existing = zones.find((zone) => zone.id === target.id);
  const mergeTarget = next.findIndex((zone) => zone.id === target.id);
  if (mergeTarget >= 0) next[mergeTarget] = { ...next[mergeTarget]!, ...target, mp: clip.union(next[mergeTarget]!.mp, drawn) };
  else next.push({ ...target, ...(existing ? { locked: existing.locked } : {}), mp: drawn });
  return next;
}

export function unassignedMP(plotMP: MultiPolygon, zones: PaintZone[]): MultiPolygon {
  return zones.length ? clip.difference(plotMP, ...zones.map((zone) => zone.mp)) : plotMP;
}

export function summarize(plotMP: MultiPolygon, zones: PaintZone[]) {
  const plotSqft = mpArea(plotMP);
  return { plotSqft, rows: zones.map((zone) => ({ ...zone, areaSqft: mpArea(zone.mp) })), unassignedSqft: mpArea(unassignedMP(plotMP, zones)) };
}

function orient(a: Point, b: Point, c: Point): number { return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]); }
function onSegment(a: Point, b: Point, p: Point): boolean {
  return Math.min(a[0], b[0]) - 1e-9 <= p[0] && p[0] <= Math.max(a[0], b[0]) + 1e-9 &&
    Math.min(a[1], b[1]) - 1e-9 <= p[1] && p[1] <= Math.max(a[1], b[1]) + 1e-9;
}
function segmentsIntersect(a: Point, b: Point, c: Point, d: Point): boolean {
  const o1 = orient(a, b, c), o2 = orient(a, b, d), o3 = orient(c, d, a), o4 = orient(c, d, b);
  return (o1 * o2 < 0 && o3 * o4 < 0) ||
    (Math.abs(o1) < 1e-9 && onSegment(a, b, c)) || (Math.abs(o2) < 1e-9 && onSegment(a, b, d)) ||
    (Math.abs(o3) < 1e-9 && onSegment(c, d, a)) || (Math.abs(o4) < 1e-9 && onSegment(c, d, b));
}

export function validateRing(ring: Ring, minAreaSqft = 1): string[] {
  const errors: string[] = [];
  if (ring.length < 3) return ['A plot needs at least three corners.'];
  if (new Set(ring.map(([x, y]) => `${x.toFixed(8)},${y.toFixed(8)}`)).size < 3) errors.push('A plot needs three distinct corners.');
  if (Math.abs(ringArea(ring)) < minAreaSqft) errors.push(`The plot must be at least ${minAreaSqft} sq ft.`);
  for (let i = 0; i < ring.length; i += 1) {
    const a = ring[i]!, b = ring[(i + 1) % ring.length]!;
    for (let j = i + 1; j < ring.length; j += 1) {
      if (j === i || j === (i + 1) % ring.length || i === (j + 1) % ring.length) continue;
      const c = ring[j]!, d = ring[(j + 1) % ring.length]!;
      if (segmentsIntersect(a, b, c, d)) { errors.push('These corners cross over each other. Adjust the outline.'); return errors; }
    }
  }
  return errors;
}

function distanceToSegment(p: Point, a: Point, b: Point): number {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy || 1)));
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}

export function labelPoint(mp: MultiPolygon): Point {
  if (!mp.length) return [0, 0];
  const all = mp.flat(2) as Point[];
  let [x0, y0, x1, y1] = bbox(all);
  const initial = centroid(mp[0]![0]!.slice(0, -1) as Point[]);
  let initialDistance = -Infinity;
  if (pointInMP(initial, mp)) {
    initialDistance = Infinity;
    for (const polygon of mp) for (const ring of polygon) for (let i = 0; i < ring.length - 1; i += 1) {
      initialDistance = Math.min(initialDistance, distanceToSegment(initial, ring[i]! as Point, ring[i + 1]! as Point));
    }
  }
  const best = { point: initial, distance: initialDistance };
  let step = Math.max(x1 - x0, y1 - y0) / 16;
  for (let iteration = 0; iteration < 5 && step > 1e-5; iteration += 1) {
    const startX = iteration === 0 ? x0 : best.point[0] - step * 2;
    const endX = iteration === 0 ? x1 : best.point[0] + step * 2;
    const startY = iteration === 0 ? y0 : best.point[1] - step * 2;
    const endY = iteration === 0 ? y1 : best.point[1] + step * 2;
    for (let x = startX; x <= endX; x += step) for (let y = startY; y <= endY; y += step) {
      const point: Point = [x, y];
      if (!pointInMP(point, mp)) continue;
      let distance = Infinity;
      for (const polygon of mp) for (const ring of polygon) for (let i = 0; i < ring.length - 1; i += 1) {
        distance = Math.min(distance, distanceToSegment(point, ring[i]! as Point, ring[i + 1]! as Point));
      }
      if (distance > best.distance + 1e-9) { best.point = point; best.distance = distance; }
    }
    step /= 4;
  }
  return best.point;
}

export function centroid(ring: Ring): Point {
  const area = ringArea(ring);
  if (Math.abs(area) < 1e-9) return ring[0] ?? [0, 0];
  let x = 0, y = 0;
  for (let i = 0; i < ring.length; i += 1) {
    const a = ring[i]!, b = ring[(i + 1) % ring.length]!, cross = a[0] * b[1] - b[0] * a[1];
    x += (a[0] + b[0]) * cross; y += (a[1] + b[1]) * cross;
  }
  return [x / (6 * area), y / (6 * area)];
}

export function perimeter(ring: Ring): number {
  return ring.reduce((sum, point, index) => {
    const next = ring[(index + 1) % ring.length]!;
    return sum + Math.hypot(next[0] - point[0], next[1] - point[1]);
  }, 0);
}
