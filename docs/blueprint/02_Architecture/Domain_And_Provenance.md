# Domain model and provenance
Entities: Property, Plot, SoilLayer/State, CropState, WaterState, SolarState, InfraState, FinancialState, FarmState, Intervention, Scenario, Recommendation, Approval, Outcome, ParameterSet.
Provenance values: MEASURED, IMPORTED, ESTIMATED, MODEL_PREDICTED, MISSING. Separate DB tables for observation / estimate / prediction. ESTIMATED requires method + uncertainty + parents. MEASURED can never be overwritten by non-measured; corrections supersede. MISSING renders as a gap, never zero.
