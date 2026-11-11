import { create } from 'zustand';
import { plots as seedPlots, crops, demoResult, demoAllocations } from '../api/fixtures';
import type { Layout, PlotDTO, Zone, LandUse, IrrigationKind } from '../api/types';
import { paintRegion, toMP, type PaintZone, type Ring } from '../geometry/geom';
import { areasToLayout } from '../geometry/layout';

type Tool = 'select'|'paint'|'erase'|'split';
interface PlannerState {
  plots: PlotDTO[]; layouts: Record<string,Layout>; selectedPlotId: string; selectedZoneId?: string;
  tool: Tool; cropId: string; landUse: LandUse; irrigation: IrrigationKind;
  history: Record<string,Layout[]>; future: Record<string,Layout[]>; tab: string; result: typeof demoResult;
  selectPlot: (id:string)=>void; setTool:(tool:Tool)=>void; setCrop:(id:string)=>void; setUse:(use:LandUse)=>void; setIrrigation:(kind:IrrigationKind)=>void;
  selectZone:(id?:string)=>void; paint:(ring:Ring)=>void; erase:(id:string)=>void; toggleLock:(id:string)=>void; split:(id:string,ring:Ring)=>void;
  undo:()=>void; redo:()=>void; setTab:(tab:string)=>void; reset:()=>void;
  applySample:(allocationsByPlot?:Record<string,import('../api/types').AllocationItem[]>)=>void;
}
const empty = ():Record<string,Layout> => Object.fromEntries(seedPlots.map((p)=>[p.id,{plotId:p.id,zones:[]} ]));
const paintable = (z:Zone):PaintZone => ({id:z.id,kind:z.kind,cropId:z.cropId,irrigation:z.irrigation,mp:z.geometryFt,locked:z.locked});
export const usePlanner = create<PlannerState>((set,get)=>({
  plots:seedPlots, layouts:empty(), selectedPlotId:seedPlots[0]!.id, tool:'select', cropId:crops[0]!.id, landUse:'crop', irrigation:'drip', history:{}, future:{}, tab:'picture', result:demoResult,
  selectPlot:(id)=>set({selectedPlotId:id,selectedZoneId:undefined}), setTool:(tool)=>set({tool}), setCrop:(cropId)=>set({cropId,landUse:'crop'}), setUse:(landUse)=>set({landUse}),setIrrigation:(irrigation)=>set({irrigation}),selectZone:(selectedZoneId)=>set({selectedZoneId}),setTab:(tab)=>set({tab}),
  paint:(ring)=>{const s=get(),p=s.plots.find(x=>x.id===s.selectedPlotId)!,layout=s.layouts[p.id]!,before=layout;
    const z:Zone={id:`zone-${Date.now()}`,kind:s.landUse,...(s.landUse==='crop'?{cropId:s.cropId}:{}),irrigation:{kind:s.irrigation},geometryFt:[]};
    const zones=paintRegion(toMP(p.boundaryFt),layout.zones.map(paintable),ring,{...paintable(z),mp:[]} as PaintZone) as unknown as Zone[];
    const clean=zones.map((zone)=>({...zone,geometryFt:(zone as unknown as PaintZone).mp}));
    set({layouts:{...s.layouts,[p.id]:{plotId:p.id,zones:clean}},history:{...s.history,[p.id]:[...(s.history[p.id]??[]),before].slice(-100)},future:{...s.future,[p.id]:[]}});
  },
  erase:(id)=>{const s=get(),p=s.selectedPlotId,layout=s.layouts[p]!;set({layouts:{...s.layouts,[p]:{...layout,zones:layout.zones.filter(z=>z.id!==id)}},history:{...s.history,[p]:[...(s.history[p]??[]),layout].slice(-100)},future:{...s.future,[p]:[]},selectedZoneId:undefined});},
  toggleLock:(id)=>{const s=get(),p=s.selectedPlotId,l=s.layouts[p]!,old=l.zones.find(z=>z.id===id);if(!old)return;set({layouts:{...s.layouts,[p]:{...l,zones:l.zones.map(z=>z.id===id?{...z,locked:!z.locked}:z)}},history:{...s.history,[p]:[...(s.history[p]??[]),l].slice(-100)}});},
  split:(_id,_ring)=>{},
  undo:()=>{const s=get(),p=s.selectedPlotId,h=s.history[p]??[];if(!h.length)return;const prior=h[h.length-1]!;set({layouts:{...s.layouts,[p]:prior},history:{...s.history,[p]:h.slice(0,-1)},future:{...s.future,[p]:[...(s.future[p]??[]),s.layouts[p]! ]}});},
  redo:()=>{const s=get(),p=s.selectedPlotId,f=s.future[p]??[];if(!f.length)return;set({layouts:{...s.layouts,[p]:f[f.length-1]!},future:{...s.future,[p]:f.slice(0,-1)},history:{...s.history,[p]:[...(s.history[p]??[]),s.layouts[p]! ]}});},
  reset:()=>set({layouts:empty(),history:{},future:{},selectedZoneId:undefined}),
  applySample:(allocationsByPlot=demoAllocations)=>{const s=get(),next={...s.layouts};for(const p of s.plots){const allocations=allocationsByPlot[p.id as keyof typeof allocationsByPlot];if(allocations)next[p.id]=areasToLayout(p,allocations);}set({layouts:next,selectedPlotId:'plot-a',selectedZoneId:undefined,history:{...s.history,'plot-a':[...(s.history['plot-a']??[]),s.layouts['plot-a']!].slice(-100)}});},
}));

