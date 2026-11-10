# Licence analysis
| Component | Licence | Plan |
|---|---|---|
| AquaCrop-OSPy | Apache-2.0 | Algorithms re-specified in our own words/code; may be used as test-fixture generator; if code is ever copied, keep NOTICE and headers |
| pvlib | BSD-3 | optional test cross-check dependency; permissive |
| DSSAT-CSM-OS | BSD-3 | external executable via subprocess (Docker); permissive |
| LangGraph | MIT | runtime dependency |
| Pyomo/HiGHS | BSD / MIT | runtime dependencies |
| pyRothC | CC0 | equations re-implemented (public-domain port; underlying model published) |
| farmOS | **GPL-2.0** | NOT vendored; optional integration only through its HTTP API (JSON:API) or file export; keeps our code free of GPL obligations |
| aiana (agrivoltaics) | GPL-3.0 | do not copy |
| NREL InSPIRE | NOASSERTION | read-only reference, no code reuse until licence clarified |
Note: this is an engineering summary, not legal advice; confirm with counsel before distribution.
