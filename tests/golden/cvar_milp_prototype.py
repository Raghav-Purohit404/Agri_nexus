import pyomo.environ as pyo, numpy as np
rng=np.random.default_rng(7)
P=3; O=3; S=50
# payoff[p,o,s] = NPV (lakh INR) of option o on plot p in weather scenario s ; water[p,o,s] in m3 ; capex[p,o]
area=[800,600,1300]
base=np.array([[3.0,1.0,2.5],[2.5,0.8,2.0],[2.0,3.0,2.8]])    # crop, PV, agrivoltaic
vol=np.array([[1.5,0.2,0.9],[1.5,0.2,0.9],[1.5,0.2,0.9]])
pay=base[:,:,None]*(1+vol[:,:,None]*rng.standard_normal((1,1,S))*np.array([1,0.1,0.5])[None,:,None])
capex=np.array([[0.1,2.0,3.0]]*3)
m=pyo.ConcreteModel()
m.P=pyo.RangeSet(P);m.O=pyo.RangeSet(O);m.S=pyo.RangeSet(S)
m.x=pyo.Var(m.P,m.O,within=pyo.Binary)
m.eta=pyo.Var(within=pyo.Reals); m.z=pyo.Var(m.S,within=pyo.NonNegativeReals)
alpha=0.8; lam=0.5; budget=5.0
m.one=pyo.Constraint(m.P,rule=lambda m,p:sum(m.x[p,o] for o in m.O)==1)
m.bud=pyo.Constraint(expr=sum(capex[p-1,o-1]*m.x[p,o] for p in m.P for o in m.O)<=budget)
npv=lambda m,s:sum(pay[p-1,o-1,s-1]*m.x[p,o] for p in m.P for o in m.O)
m.cv=pyo.Constraint(m.S,rule=lambda m,s:m.z[s]>=m.eta-npv(m,s))   # Rockafellar-Uryasev shortfall
cvar=m.eta-(1/((1-alpha)*S))*sum(m.z[s] for s in m.S)
mean=(1/S)*sum(npv(m,s) for s in m.S)
m.obj=pyo.Objective(expr=(1-lam)*mean+lam*cvar,sense=pyo.maximize)
r=pyo.SolverFactory('appsi_highs').solve(m)
print(r.solver.termination_condition, round(pyo.value(m.obj),4))
print([[int(round(pyo.value(m.x[p,o]))) for o in m.O] for p in m.P], 'mean',round(pyo.value(mean),3),'cvar',round(pyo.value(cvar),3))
