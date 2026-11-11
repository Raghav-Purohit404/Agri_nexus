import { useMemo, useRef, useState } from 'react';
import { crops } from '../api/fixtures';
import { usePlanner } from '../state/store';
import { bbox, dripRows, labelPoint, mpArea, toMP, type Point, type Ring } from '../geometry/geom';
import type { Zone } from '../api/types';

const color:Record<string,string>={mustard:'#d5a22c',wheat:'#d7ba72','pearl-millet':'#718d53','cluster-bean':'#41836f',chickpea:'#a68d72',sorghum:'#9b7759',reclaim:'#b7a98e',fallow:'#d7d2c6',pv:'#183f62',agrivoltaic:'#4b7788',water:'#5b98bd'};
const pathFor=(ring:Point[], tx:number, ty:number, s:number, minX=0, maxY=40)=>ring.map(([x,y],i)=>`${i?'L':'M'} ${tx+(x-minX)*s} ${ty+(maxY-y)*s}`).join(' ')+' Z';

export function PlotCanvas(){
 const {plots,selectedPlotId,layouts,selectedZoneId,tool,selectZone,paint,erase,selectPlot}=usePlanner();
 const plot=plots.find(p=>p.id===selectedPlotId)!,layout=layouts[plot.id]!;
 const [drag,setDrag]=useState<{start:Point;end:Point}|null>(null),svg=useRef<SVGSVGElement>(null);
 const minX=Math.min(...plot.boundaryFt.map(p=>p[0])),maxX=Math.max(...plot.boundaryFt.map(p=>p[0])),maxY=Math.max(...plot.boundaryFt.map(p=>p[1]));
 const width=maxX-minX;
 const height=maxY-Math.min(...plot.boundaryFt.map(p=>p[1]));
 const scale=Math.min(560/(width||1),380/(height||1));const tx=40,ty=40;
 const project=(ev:React.PointerEvent<SVGSVGElement>):Point=>{const r=svg.current!.getBoundingClientRect();const x=(ev.clientX-r.left)*760/r.width,y=(ev.clientY-r.top)*480/r.height;return [(x-tx)/scale+minX,maxY-(y-ty)/scale]};
 const pointerDown=(ev:React.PointerEvent<SVGSVGElement>)=>{if(tool==='select')return;svg.current?.setPointerCapture(ev.pointerId);const p=project(ev);setDrag({start:p,end:p});};
 const pointerMove=(ev:React.PointerEvent<SVGSVGElement>)=>{if(drag)setDrag({...drag,end:project(ev)});};
 const pointerUp=()=>{if(!drag)return;const {start,end}=drag;setDrag(null);const ring:Ring=[[start[0],start[1]],[end[0],start[1]],[end[0],end[1]],[start[0],end[1]]];if(tool==='erase'){const z=layout.zones.find(x=>x.geometryFt.some(poly=>poly[0]!.some(pt=>pt[0]>=Math.min(start[0],end[0])&&pt[0]<=Math.max(start[0],end[0])&&pt[1]>=Math.min(start[1],end[1])&&pt[1]<=Math.max(start[1],end[1]))));if(z)erase(z.id);} else paint(ring);};
 const area=layout.zones.reduce((a,z)=>a+mpArea(z.geometryFt),0);
 const focus=layout.zones.find(z=>z.id===selectedZoneId);
 return <section className="canvas-card" aria-label="Interactive plot plan">
  <div className="canvas-head"><div><span className="eyebrow">LAND LAYOUT</span><h2>{plot.name}</h2><p>Draw and arrange growing zones</p></div><div className="select-wrap"><label htmlFor="plot-select">Plot</label><select id="plot-select" value={plot.id} onChange={e=>selectPlot(e.target.value)}>{plots.map(p=><option key={p.id} value={p.id}>{p.name} · {p.areaSqft.toLocaleString()} sq ft</option>)}</select></div></div>
  <div className="canvas-tools">{(['select','paint','erase'] as const).map((t)=><button key={t} className={tool===t?'tool active':'tool'} onClick={()=>usePlanner.getState().setTool(t)} aria-pressed={tool===t}>{t==='select'?'↖ Select':t==='paint'?'＋ Paint zone':'⌫ Erase'}</button>)}<span className="tool-hint">{tool==='paint'?'Drag to paint a rectangular zone':'Click a zone to inspect it'}</span></div>
  <svg ref={svg} className="plot-svg" viewBox="0 0 760 480" role="img" aria-label={`${plot.name} plot map`} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp}>
   <defs><pattern id="unassigned" width="12" height="12" patternUnits="userSpaceOnUse"><rect width="12" height="12" fill="#efeee8"/><path d="M0 12L12 0" stroke="#dfddd4" strokeWidth="1"/></pattern><pattern id="reclaim" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#ded5c3"/><circle cx="2" cy="2" r="1" fill="#9f8e71"/></pattern><pattern id="mustard" width="10" height="10" patternUnits="userSpaceOnUse"><rect width="10" height="10" fill="#e3c35f"/><path d="M0 8L8 0M4 10L10 4" stroke="#b48a29" strokeWidth="1"/></pattern></defs>
   <path d={pathFor(plot.boundaryFt,tx,ty,scale,minX,maxY)} fill="url(#unassigned)" stroke="#203c3a" strokeWidth="3" strokeLinejoin="round"/>
   {layout.zones.map((zone:Zone)=>zone.geometryFt.map((poly,pi)=><path key={`${zone.id}-${pi}`} d={pathFor(poly[0]!.slice(0,-1) as Point[],tx,ty,scale,minX,maxY)} fill={zone.kind==='reclaim'?'url(#reclaim)':zone.cropId==='mustard'?'url(#mustard)':color[zone.cropId??zone.kind]??'#8bb68c'} fillOpacity=".92" stroke={zone.id===selectedZoneId?'#10202c':'#fffdf7'} strokeWidth={zone.id===selectedZoneId?4:2} onClick={e=>{e.stopPropagation();selectZone(zone.id)}}/>))}
   {layout.zones.filter(z=>z.irrigation.kind==='drip').flatMap(zone=>dripRows(zone.geometryFt,zone.irrigation.rowSpacingFt??2,zone.irrigation.rowAngleDeg??0,.5).rows.map(([a,b],i)=><g key={`${zone.id}-drip-${i}`} pointerEvents="none"><path d={`M ${tx+(a[0]-minX)*scale} ${ty+(maxY-a[1])*scale} L ${tx+(b[0]-minX)*scale} ${ty+(maxY-b[1])*scale}`} fill="none" stroke="#fffdf7" strokeWidth="4"/><path d={`M ${tx+(a[0]-minX)*scale} ${ty+(maxY-a[1])*scale} L ${tx+(b[0]-minX)*scale} ${ty+(maxY-b[1])*scale}`} fill="none" stroke="#164d86" strokeWidth="2" strokeDasharray="5 3"/><circle cx={tx+(a[0]-minX)*scale} cy={ty+(maxY-a[1])*scale} r="2" fill="#164d86"/></g>))}
   {layout.zones.map((zone,index)=>{
    const label=labelPoint(zone.geometryFt);
    const crop=crops.find(c=>c.id===zone.cropId)?.name??(zone.kind==='reclaim'?'Soil recovery':zone.kind);
    const areaLabel=`${Math.round(mpArea(zone.geometryFt)).toLocaleString()} sq ft`;
    const bounds=bbox(zone.geometryFt.flat(2) as Point[]),zoneWidth=(bounds[2]-bounds[0])*scale;
    const chipWidth=Math.max(crop.length*6+16,areaLabel.length*5.4+16),outside=chipWidth>zoneWidth-4;
    const ax=tx+(label[0]-minX)*scale,ay=ty+(maxY-label[1])*scale;
    const priorCallouts=layout.zones.slice(0,index).filter(previous=>{
      const previousCrop=crops.find(c=>c.id===previous.cropId)?.name??(previous.kind==='reclaim'?'Soil recovery':previous.kind);
      const previousArea=`${Math.round(mpArea(previous.geometryFt)).toLocaleString()} sq ft`;
      const previousBounds=bbox(previous.geometryFt.flat(2) as Point[]);
      return Math.max(previousCrop.length*6+16,previousArea.length*5.4+16)>(previousBounds[2]-previousBounds[0])*scale-4;
    }).length;
    const x=outside?tx+width*scale+chipWidth/2+18:ax,y=ay+(outside?priorCallouts*42:0);
    return <g key={`${zone.id}-label`} pointerEvents="none">{outside&&<path d={`M ${ax} ${ay} L ${x-chipWidth/2} ${y}`} stroke="#49675d" strokeWidth="1"/>}<rect x={x-chipWidth/2} y={y-19} width={chipWidth} height="36" rx="6" fill="#fffefa" fillOpacity=".95" stroke="#bfd0c2" strokeWidth="1"/><text x={x} y={y-5} className="zone-label">{crop}</text><text x={x} y={y+9} className="zone-area">{areaLabel}{zone.irrigation.kind!=='none'?` · ${zone.irrigation.kind}`:''}{zone.locked?' · locked':''}</text></g>;
   })}
   {drag&&<path d={pathFor([[drag.start[0],drag.start[1]],[drag.end[0],drag.start[1]],drag.end,[drag.start[0],drag.end[1]]],tx,ty,scale,minX,maxY)} fill="#1b7f79" fillOpacity=".25" stroke="#1b7f79" strokeWidth="2" strokeDasharray="6 4"/>}
   <g transform={`translate(${Math.max(650,720-10*scale)} 420)`}><rect x="0" y="-40" width={10*scale+24} height="46" rx="7" fill="#fffdf7"/><text x={10*scale/2+12} y="-10" textAnchor="middle" className="north">N ↑</text><path d={`M12 0H${12+10*scale}`} stroke="#203c3a" strokeWidth="3"/><text x={10*scale/2+12} y="-25" textAnchor="middle" className="north">10 ft</text></g>
  </svg>
  <div className="canvas-foot"><span><b>{Math.round(area).toLocaleString()}</b> / {plot.areaSqft.toLocaleString()} sq ft zoned</span><span>{layout.zones.length} zones {layout.zones.some(z=>z.irrigation.kind==='drip')?'· blue dashed = drip':''}</span></div>
  {focus&&<div className="selected-note"><b>{crops.find(c=>c.id===focus.cropId)?.name??focus.kind}</b> · {Math.round(mpArea(focus.geometryFt)).toLocaleString()} sq ft · {focus.irrigation.kind} irrigation {focus.locked?'· locked':''}</div>}
 </section>;
}

