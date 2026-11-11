import { createServer } from 'node:http';
import { crops, plots, demoAllocations, demoResult } from '../src/api/fixtures';

const server=createServer((req,res)=>{
 res.setHeader('Access-Control-Allow-Origin','*');res.setHeader('Access-Control-Allow-Headers','Content-Type');res.setHeader('Access-Control-Allow-Methods','GET,POST,OPTIONS');res.setHeader('Content-Type','application/json');
 if(req.method==='OPTIONS'){res.writeHead(204).end();return;}
 if(req.url==='/api/v1/plots'&&req.method==='GET'){res.end(JSON.stringify({source:'synthetic_demo_fixture',plots}));return;}
 if(req.url==='/api/v1/crops'&&req.method==='GET'){res.end(JSON.stringify({source:'configuration_fixture',crops}));return;}
 if(req.url==='/api/v1/optimize'&&req.method==='POST'){let body='';req.on('data',chunk=>body+=chunk);req.on('end',()=>{res.end(JSON.stringify({...demoResult,plots:Object.entries(demoAllocations).map(([plotId,allocation])=>({plotId,name:plots.find(p=>p.id===plotId)?.name??plotId,areaSqft:plots.find(p=>p.id===plotId)?.areaSqft??0,allocation,kpis:{expectedProfitInr:{mean:0,p05:0,p50:0,p95:0},worst20ProfitInr:0,waterUseM3:0}})),requestReceived:body.length>0}));});return;}
 res.writeHead(404).end(JSON.stringify({detail:'Mock route not found'}));
});
const port=Number(process.env.MOCK_API_PORT??8787);server.listen(port,'127.0.0.1',()=>console.log(`Synthetic demo API listening at http://127.0.0.1:${port}/api/v1`));
