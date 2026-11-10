"""
FILE: farm_twin/ui/app_spec.py
PURPOSE: UI specification (build with Streamlit first for speed; React later if needed). Mobile-first (farmers use phones), English + Hindi, low-bandwidth friendly.
PAGES: 1 Onboarding wizard (property, plots by map/dimensions/GeoJSON upload, water sources, capital, goals) ; 2 Data room (uploads, extracted-field confirmation table, quality issues, completeness meters per model, 'collect next' VOI ranking) ; 3 Plot dashboard (state, soil card with provenance badges: MEASURED/IMPORTED/ESTIMATED/PREDICTED/MISSING, canopy vs satellite, water balance) ; 4 Scenarios (build plan, run, compare with fan charts) ; 5 Decision board (Pareto frontier, allocation maps, decision stability, trade-offs in plain language) ; 6 Agent chat with inline approval cards ; 7 Learning (outcomes vs predictions, calibration decisions, 'is the twin improving?') ; 8 Reports export (PDF/Docx).
UX RULES: every number shows unit + uncertainty band + provenance badge; MISSING shows a gap, never zero; model-validation banner ('unvalidated agrivoltaic model') cannot be dismissed on recommendation pages; approval is a distinct, confirm-twice action; offline-tolerant data entry (queue observations); units switchable (sq ft/m2, INR/lakh).
"""

from __future__ import annotations

PAGES = (
    "Onboarding",
    "Data room",
    "Plot dashboard",
    "Scenarios",
    "Decision board",
    "Agent chat",
    "Learning",
    "Reports",
)


def run_ui(api_base_url: str = "http://localhost:8000/api/v1") -> None:
    """Streamlit UI backed by the versioned API; failed saves remain visible as local queued data."""
    try:
        import streamlit as st
        import os
        import json
        import uuid
        import httpx
    except ImportError as exc:
        raise RuntimeError("Streamlit must be installed to launch the UI") from exc
    from farm_twin.ui.client import APIClient

    st.set_page_config(page_title="Farm Digital Twin", layout="wide", initial_sidebar_state="collapsed")
    language = st.sidebar.selectbox("Language", ["English", "हिन्दी"])
    page = st.sidebar.radio("Navigate", PAGES)
    units = st.sidebar.selectbox("Area units", ["m²", "sq ft"])
    client = APIClient(api_base_url, os.environ.get("FARM_TWIN_API_TOKEN"))
    st.title("Farm Digital Twin" if language == "English" else "फार्म डिजिटल ट्विन")

    def request(method: str, path: str, *, payload=None, files=None, idempotency_key=None):
        try:
            if method == "GET":
                return client.get(path)
            if files is not None:
                response = httpx.post(api_base_url.rstrip("/") + path, files=files, headers=client.headers, timeout=60.)
                response.raise_for_status()
                return response.json()
            return client.post(path, payload or {}, idempotency_key=idempotency_key or str(uuid.uuid4()))
        except (httpx.HTTPError, OSError) as exc:
            st.error(f"API request unavailable: {exc}")
            return None

    def show_quantified(item):
        if item is None or item.get("value") is None:
            st.warning("MISSING — data gap; no numeric value is assumed.")
            return
        provenance = item.get("prov", {})
        value = item.get("value")
        uncertainty = provenance.get("uncertainty") or {}
        band = f" · ±{uncertainty['sd']}" if uncertainty.get("sd") is not None else ""
        st.metric(str(item.get("variable", "Value")), f"{value} {item.get('unit', '')}{band}")
        st.caption(f"Provenance: {provenance.get('source', 'UNSPECIFIED')} · {provenance.get('method') or 'method not recorded'}")

    if page == "Onboarding":
        st.header("Create a property" if language == "English" else "संपत्ति बनाएँ")
        with st.form("property_create"):
            name = st.text_input("Property name")
            region = st.text_input("State / region code", "IN-RJ")
            longitude = st.number_input("Longitude (WGS84)", min_value=-180., max_value=180., value=73.02)
            latitude = st.number_input("Latitude (WGS84)", min_value=-90., max_value=90., value=26.24)
            submitted = st.form_submit_button("Save property")
        if submitted:
            result = request("POST", "/properties", payload={"name": name, "country_iso": "IN", "region_code": region,
                              "reference_point": [longitude, latitude], "currency": "INR", "tz": "Asia/Kolkata"})
            if result is not None:
                st.success("Property saved")
                st.json(result)
        st.caption("Plot geometry can be added through GeoJSON or the API; geometry area is calculated in a local projected CRS.")

    elif page == "Data room":
        st.header("Data room")
        upload = st.file_uploader("Soil report (PDF, CSV, or text; up to 25 MB)", type=["pdf", "csv", "txt"])
        if upload and st.button("Upload for extraction review"):
            result = request("POST", "/uploads/soil-report", files={"file": (upload.name, upload.getvalue(), upload.type)})
            if result is not None:
                st.success("Extracted fields require confirmation before entering FarmState.")
                st.json(result)
        property_id = st.text_input("Property ID for quality and collection review")
        if property_id and st.button("Check data completeness"):
            st.json(request("GET", f"/quality/{property_id}"))
            st.json(request("POST", "/voi/rank", payload={"property_id": property_id}))

    elif page == "Plot dashboard":
        st.header("Plot dashboard")
        plot_id = st.text_input("Plot ID")
        if plot_id:
            state = request("GET", f"/plots/{plot_id}/state")
            if state:
                st.json(state)
                soil = state.get("soil", {})
                for variable, item in soil.items():
                    if isinstance(item, dict) and ("value" in item or item.get("prov")):
                        st.write(variable)
                        show_quantified({**item, "variable": variable})
                st.caption(f"Area display preference: {units}. Stored canonical area remains m².")
            with st.form("offline_observation"):
                variable = st.text_input("Observation variable")
                value = st.number_input("Measured value", value=0.)
                unit = st.text_input("Unit")
                if st.form_submit_button("Save observation"):
                    observation = {"plot_id": plot_id, "variable": variable, "value": value, "unit": unit,
                                   "source": "MEASURED", "method": "user_entry"}
                    result = request("POST", f"/plots/{plot_id}/observations", payload=observation)
                    if result is None:
                        st.session_state.setdefault("offline_observations", []).append(observation)
                        st.warning("Queued in this browser session; download the queue before leaving this page.")
                    else:
                        st.success("Observation saved with MEASURED provenance")
            queue = st.session_state.get("offline_observations", [])
            if queue:
                st.download_button("Download offline observation queue", json.dumps(queue, ensure_ascii=False, indent=2),
                                   file_name="farm_twin_observation_queue.json", mime="application/json")

    elif page == "Scenarios":
        st.header("Scenarios")
        with st.form("scenario_run"):
            st.text_input("Plot ID", key="scenario_plot")
            st.text_input("Crop ID", key="scenario_crop")
            st.number_input("Weather ensemble members", min_value=1, max_value=1000, value=50, key="scenario_n")
            if st.form_submit_button("Queue season simulation"):
                result = request("POST", "/simulate/season", payload={"plot_id": st.session_state.scenario_plot,
                                  "crop": st.session_state.scenario_crop, "n_weather": st.session_state.scenario_n})
                if result is not None:
                    st.success("Simulation submitted")
                    st.json(result)

    elif page == "Decision board":
        st.header("Decision board")
        st.error("Model validation status and limitations must remain visible. Agrivoltaic crop response is experimental.")
        recommendation_id = st.text_input("Recommendation ID")
        if recommendation_id:
            result = request("GET", f"/recommendations/{recommendation_id}")
            if result:
                st.json(result)
                st.warning("Approval is a separate human action. Review assumptions, gaps, and downside risk before approving.")
                phrase = st.text_input("Type APPROVE to confirm")
                if phrase == "APPROVE" and st.button("Approve recommendation"):
                    st.session_state.confirm_approval = True
                if st.session_state.get("confirm_approval") and st.button("Confirm approval — execute only the reviewed plan"):
                    st.json(request("POST", f"/recommendations/{recommendation_id}/approve", payload={"decision": "APPROVED"}))
                    st.session_state.confirm_approval = False

    elif page == "Agent chat":
        st.header("Agent chat")
        st.caption("Agents can propose plans; only a human approval can authorize gated state changes.")
        prompt = st.chat_input("Ask about a plot, soil, water, crops, or a scenario")
        if prompt:
            st.chat_message("user").write(prompt)
            try:
                with httpx.stream("POST", api_base_url.rstrip("/") + "/agent/chat", json={"message": prompt},
                                  headers=client.headers, timeout=60.) as response:
                    response.raise_for_status()
                    with st.chat_message("assistant"):
                        for line in response.iter_lines():
                            if line.startswith("data: "):
                                st.write(line[6:])
            except httpx.HTTPError as exc:
                st.error(f"Agent service unavailable: {exc}")

    elif page == "Learning":
        st.header("Learning")
        st.json(request("GET", "/calibration/status"))
        st.json(request("GET", "/calibration/history"))
        st.caption("Prediction and observation records are separate; calibration candidates require the promotion gate.")

    elif page == "Reports":
        st.header("Reports")
        scenario_ids = st.text_input("Scenario IDs (comma-separated)")
        audience = st.selectbox("Audience", ["farmer", "technical", "investor"])
        if st.button("Build report"):
            st.json(request("POST", "/reports/build", payload={"scenario_ids": [x.strip() for x in scenario_ids.split(",") if x.strip()], "audience": audience}))

    st.caption(f"API: {api_base_url} · {page}")


if __name__ == "__main__":
    import os
    run_ui(os.environ.get("FARM_TWIN_API_URL", "http://localhost:8000/api/v1"))
