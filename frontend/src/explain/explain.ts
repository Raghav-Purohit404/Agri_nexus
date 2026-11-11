import type { CropOption, Layout, PlotDTO, Zone } from '../api/types';
import { mpArea, toMP, unassignedMP } from '../geometry/geom';

export const fmtSqft = (n:number) => `${Math.round(n).toLocaleString('en-IN')} sq ft`;
export const fmtINR = (n:number) => {const a=Math.abs(Math.round(n));const s=a>=1e5?`${(a/1e5).toFixed(a>=1e6?1:2).replace(/\.?0+$/,'')} lakh`:a.toLocaleString('en-IN');return `${n<0?'−':''}₹${s}`;};
export function fractionWords(f:number):string {const t:[[number,string],... [number,string][]]=[[.95,'almost all'],[.8,'most'],[.7,'about three-quarters'],[.58,'more than half'],[.45,'about half'],[.38,'about two-fifths'],[.29,'about a third'],[.23,'about a quarter'],[.17,'about a fifth'],[.135,'about a sixth'],[.08,'about a tenth'],[.04,'a small part'],[0,'a tiny part']];return t.find(([min])=>f>=min)![1];}
const irrigationText:Record<string,string>={drip:'with drip irrigation',flood:'with surface (flood) irrigation',sprinkler:'with sprinkler irrigation',none:'on rain only (no irrigation)'};
const action=(z:Zone,crops:CropOption[])=>{const crop=crops.find(c=>c.id===z.cropId)?.name??z.cropId??'a crop';switch(z.kind){case 'crop':return `grow ${crop}`;case 'agrivoltaic':return `grow ${crop} underneath solar panels`;case 'reclaim':return 'treat the soil first (gypsum and flushing the salts out) so it can be farmed later';case 'fallow':return 'leave it empty this season';case 'pv':return 'put solar panels there';case 'water':return 'reserve it for water storage';}};
export function explainZone(zone:Zone,crops:CropOption[],plotAreaSqft=mpArea(zone.geometryFt)):string {const area=mpArea(zone.geometryFt);const frac=area/plotAreaSqft;const irr=zone.kind==='crop'||zone.kind==='agrivoltaic'?` ${irrigationText[zone.irrigation.kind]??irrigationText.none}`:'';return `• ${fmtSqft(area)} (${fractionWords(frac)} of the plot): ${action(zone,crops)}${irr}.`;}
export function explainPlot(plot:PlotDTO,layout:Layout,crops:CropOption[]):string[] {
 const lines=[`${plot.name} is ${fmtSqft(plot.areaSqft)}. The best plan we found splits it like this:`,...layout.zones.slice().sort((a,b)=>mpArea(b.geometryFt)-mpArea(a.geometryFt)).map(z=>explainZone(z,crops,plot.areaSqft))];
 const total=layout.zones.reduce((n,z)=>n+mpArea(z.geometryFt),0);if(Math.abs(total-plot.areaSqft)>1)lines.push(`(Note: the zones add up to ${fmtSqft(total)}, ${fmtSqft(Math.abs(plot.areaSqft-total))} ${total<plot.areaSqft?'left unassigned':'over the plot size'}.)`);
 const unknown=layout.zones.some(z=>z.kind==='crop'&&crops.find(c=>c.id===z.cropId)?.status==='placeholder');if(unknown)lines.push('Some selected crops use placeholder parameters; performance has not been scientifically validated.');
 return lines;
}
export function explainRisk(r:{typicalProfit:number;worst20Profit:number}):string{return `In a typical year this plan earns about ${fmtINR(r.typicalProfit)}. In the worst 2 years out of 10, it still averages about ${fmtINR(r.worst20Profit)}.`;}
export function plotAreaRemaining(plot:PlotDTO,layout:Layout):number{return mpArea(unassignedMP(toMP(plot.boundaryFt),layout.zones.map(z=>({id:z.id,mp:z.geometryFt})) as never));}
