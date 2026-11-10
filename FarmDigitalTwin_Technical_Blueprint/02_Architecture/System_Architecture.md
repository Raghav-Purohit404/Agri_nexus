# System Architecture

Layers (top to bottom): UI -> API -> Agents (LangGraph) -> Tool layer -> FarmState Engine -> Models (ET0, soil water, salinity, nutrients, carbon, crop, solar, agrivoltaic, finance) -> Uncertainty/Calibration/Optimisation -> Data layer (PostGIS, providers, files).

Key principles
1. **Agents orchestrate, kernels compute.** LLMs never produce numbers; deterministic tools do.
2. **One state, many models.** FarmState is the single contract; models are replaceable behind Protocols (`models/base.py`).
3. **Fidelity levels.** L1 native/simple (always available), L2 enhanced (needs data), L3 external detailed process model for cross-validation. Engine reports the level used.
4. **Explicit coupling with one-day lag** to break water-salinity-crop cycles.
5. **Uncertainty is first-class**: weather (aleatory), parameter (epistemic), economic; kept separable.
6. **Learning is gated**: candidate parameters must beat parent on blocked held-out data.
7. **Human approval** for any change to actual plans.

See diagrams in `Diagrams/*.mmd` (render with Mermaid).
