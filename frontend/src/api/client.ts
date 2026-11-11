import type { OptimizationResult } from './types';
const base=(import.meta.env.VITE_API_BASE as string|undefined)??'/api/v1';
export async function loadDemoOptimization():Promise<OptimizationResult>{const response=await fetch(`${base}/optimize`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fixture:'plot-planner-demo',horizonYears:1})});if(!response.ok)throw new Error(`Planner API returned ${response.status}`);return response.json() as Promise<OptimizationResult>;}
