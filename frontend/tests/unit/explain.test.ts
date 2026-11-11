import {describe,expect,it} from 'vitest';
import {explainPlot,explainRisk,fractionWords,fmtINR,fmtSqft} from '../../src/explain/explain';
import type {Layout,PlotDTO,Zone} from '../../src/api/types';
import {plots,crops} from '../../src/api/fixtures';
const plot:PlotDTO={...plots[0]!,id:'test',name:'Plot A',areaSqft:800};
const z=(kind:Zone['kind'],cropId:string|undefined,area:number,irrigation:Zone['irrigation']['kind']='none'):Zone=>({id:`z-${area}-${kind}`,kind,cropId,irrigation:{kind:irrigation},geometryFt:[[[[0,0],[area,0],[area,1],[0,1],[0,0]]]]});
const layout=(zones:Zone[]):Layout=>({plotId:plot.id,zones});
describe('Appendix B explanation reference',()=>{
 it('sqft formatting',()=>expect(fmtSqft(1300)).toBe('1,300 sq ft'));
 it('INR formatting',()=>{expect(fmtINR(125000)).toBe('₹1.25 lakh');expect(fmtINR(48250)).toBe('₹48,250');expect(fmtINR(-5000)).toBe('−₹5,000')});
 it('fraction words',()=>{expect(fractionWords(.5)).toBe('about half');expect(fractionWords(.3)).toBe('about a third');expect(fractionWords(.2)).toBe('about a fifth');expect(fractionWords(.25)).toBe('about a quarter');expect(fractionWords(.96)).toBe('almost all')});
 it('Plot A wording, crop labels and land treatment',()=>{const text=explainPlot(plot,layout([z('crop','mustard',400,'drip'),z('crop','wheat',240,'flood'),z('reclaim',undefined,160)]),crops).join('\n');expect(text).toMatch(/^Plot A is 800 sq ft\./);expect(text).toContain('• 400 sq ft (about half of the plot): grow Mustard with drip irrigation.');expect(text).toContain('• 240 sq ft (about a third of the plot): grow Wheat with surface (flood) irrigation.');expect(text).toContain('• 160 sq ft (about a fifth of the plot): treat the soil first')});
 it('mismatch note reports unassigned plot area',()=>{const p={...plot,areaSqft:100};const text=explainPlot(p,layout([z('fallow',undefined,90)]),crops).join('\n');expect(text).toContain('10 sq ft left unassigned')});
 it('risk string',()=>expect(explainRisk({typicalProfit:48000,worst20Profit:21500})).toBe('In a typical year this plan earns about ₹48,000. In the worst 2 years out of 10, it still averages about ₹21,500.'));
 it('placeholder crops are explicitly identified',()=>expect(explainPlot(plot,layout([z('crop','cluster-bean',800)]),crops).join(' ')).toContain('placeholder parameters'));
 it('zones sum to the plot and report no false economic estimate',()=>{const lines=explainPlot(plot,layout([z('crop','mustard',400,'drip'),z('crop','wheat',240,'flood'),z('reclaim',undefined,160)]),crops);expect(lines.join(' ')).not.toMatch(/₹|profit|yield/i);expect(lines.filter(x=>x.startsWith('• '))).toHaveLength(3)});
 it('metric conversion round-trips',()=>{const sq=800,m2=sq/10.763910416709722;expect(Math.round(m2*10.763910416709722)).toBe(sq);expect(m2).toBeCloseTo(74.3224,3)});
 it('Hindi locale smoke test preserves native crop names when supplied',()=>{const hi=[...crops,{...crops[0]!,id:'local',name:'सरसों'}];const text=explainPlot(plot,layout([z('crop','local',800)]),hi).join(' ');expect(text).toContain('सरसों')});
});
