import streamlit as st
import pandas as pd
from datetime import date, timedelta

st.set_page_config(
    page_title="Electroplating Dashboard",
    page_icon="⚗️",
    layout="wide"
)

conn = st.connection("neon", type="sql")

# ------------------------------------------------------------------
# DATA LAYER
# All timestamps stored UTC in DB; converted to IST for display.
# Cache for 5 minutes — keeps Neon compute idle between refreshes.
# ------------------------------------------------------------------

@st.cache_data(ttl=300)
def get_runs(start_date: date, end_date: date) -> pd.DataFrame:
    return conn.query(
        f"""
        SELECT
            pr.batch_id,
            pr.run_date,
            pr.load_id,
            b.bath_name,
            sol.name                                                    AS solution_type,
            c.component_name,
            cl.client_name,
            o.name                                                      AS operator_name,
            s.name                                                      AS shift_name,
            (pr.start_time AT TIME ZONE 'Asia/Kolkata')::time          AS start_ist,
            (pr.end_time   AT TIME ZONE 'Asia/Kolkata')::time          AS end_ist,
            pr.quantity,
            pr.ok_quantity,
            (pr.quantity - pr.ok_quantity)                             AS rejected_qty,
            ROUND(pr.ok_quantity::numeric / NULLIF(pr.quantity,0)*100, 1) AS yield_pct,
            pr.status,
            pr.remarks,
            pr.bath_temp_celsius,
            pr.current_amperes,
            pr.voltage,
            pr.ph_level,
            CASE WHEN pr.parent_run_id IS NOT NULL THEN 'Yes' ELSE '' END AS is_rework
        FROM  production_runs pr
        JOIN  baths          b   ON b.bath_id          = pr.bath_id
        JOIN  solution_types sol ON sol.solution_type_id= pr.solution_type_id
        JOIN  components     c   ON c.component_id     = pr.component_id
        JOIN  clients        cl  ON cl.client_id       = c.client_id
        JOIN  operators      o   ON o.operator_id      = pr.operator_id
        JOIN  shifts         s   ON s.shift_id         = pr.shift_id
        WHERE pr.run_date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY pr.run_date DESC, pr.start_time DESC
        """,
        ttl=300,
    )


# ------------------------------------------------------------------
# SHARED HELPERS
# ------------------------------------------------------------------

COLUMN_CONFIG = {
    "batch_id":        "Batch ID",
    "run_date":        "Date",
    "load_id":         "Load",
    "bath_name":       "Bath",
    "solution_type":   "Solution",
    "component_name":  "Component",
    "client_name":     "Client",
    "operator_name":   "Operator",
    "shift_name":      "Shift",
    "start_ist":       "Start (IST)",
    "end_ist":         "End (IST)",
    "quantity":        st.column_config.NumberColumn("Qty"),
    "ok_quantity":     st.column_config.NumberColumn("OK"),
    "rejected_qty":    st.column_config.NumberColumn("Rejected"),
    "yield_pct":       st.column_config.NumberColumn("Yield %", format="%.1f%%"),
    "status":          "Status",
    "remarks":         "Remarks",
    "is_rework":       "Rework",
    "bath_temp_celsius": st.column_config.NumberColumn("Temp °C", format="%.1f"),
    "current_amperes":   st.column_config.NumberColumn("Current (A)", format="%.1f"),
    "voltage":           st.column_config.NumberColumn("Voltage (V)", format="%.1f"),
    "ph_level":          st.column_config.NumberColumn("pH", format="%.2f"),
}

OPERATOR_COLS = [
    "batch_id", "bath_name", "solution_type", "component_name", "client_name",
    "operator_name", "shift_name", "start_ist", "end_ist",
    "quantity", "ok_quantity", "rejected_qty", "yield_pct",
    "status", "is_rework", "remarks",
]

MANAGER_COLS = [
    "run_date", "batch_id", "load_id", "bath_name", "solution_type",
    "component_name", "client_name", "operator_name", "shift_name",
    "quantity", "ok_quantity", "rejected_qty", "yield_pct",
    "bath_temp_celsius", "current_amperes", "voltage", "ph_level",
    "status", "is_rework", "remarks",
]


def kpi_row(df: pd.DataFrame):
    total_qty = int(df["quantity"].sum())
    total_ok  = int(df["ok_quantity"].sum())
    yield_pct = round(total_ok / total_qty * 100, 1) if total_qty else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Runs",          len(df))
    c2.metric("Total Pieces",  f"{total_qty:,}")
    c3.metric("OK Pieces",     f"{total_ok:,}")
    c4.metric("Yield",         f"{yield_pct}%")


# ------------------------------------------------------------------
# NAVIGATION
# ------------------------------------------------------------------

st.sidebar.title("⚗️ Electroplating")
view = st.sidebar.radio("View", ["Operator — Today", "Manager — History"])
st.sidebar.markdown("---")
st.sidebar.caption("Data refreshes every 5 min. Click ⟳ to force refresh.")

if st.sidebar.button("🔄 Refresh now"):
    st.cache_data.clear()
    st.rerun()


# ------------------------------------------------------------------
# OPERATOR VIEW — Today's runs only
# ------------------------------------------------------------------

if view == "Operator — Today":
    today = date.today()
    st.title("Today's Production")
    st.caption(today.strftime("%A, %d %B %Y"))

    with st.spinner("Loading data..."):
        df = get_runs(today, today)

    if df.empty:
        st.info("No production runs recorded for today yet.")
        st.stop()

    kpi_row(df)
    st.divider()

    # Status filter
    statuses = ["All"] + sorted(df["status"].unique().tolist())
    sel_status = st.selectbox("Filter by status", statuses)
    if sel_status != "All":
        df = df[df["status"] == sel_status]

    st.dataframe(
        df[OPERATOR_COLS],
        use_container_width=True,
        hide_index=True,
        column_config=COLUMN_CONFIG,
    )


# ------------------------------------------------------------------
# MANAGER VIEW — Date range + filters
# ------------------------------------------------------------------

else:
    st.title("Production History")

    # Date range
    c1, c2 = st.columns(2)
    with c1:
        start_date = st.date_input("From", value=date.today() - timedelta(days=30))
    with c2:
        end_date = st.date_input("To", value=date.today())

    if start_date > end_date:
        st.error("'From' date must be before 'To' date.")
        st.stop()

    with st.spinner("Loading data..."):
        df = get_runs(start_date, end_date)

    if df.empty:
        st.info("No data for the selected date range.")
        st.stop()

    kpi_row(df)
    st.divider()

    # Filters
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        baths = ["All"] + sorted(df["bath_name"].unique().tolist())
        sel_bath = st.selectbox("Bath", baths)
    with c2:
        clients = ["All"] + sorted(df["client_name"].unique().tolist())
        sel_client = st.selectbox("Client", clients)
    with c3:
        operators = ["All"] + sorted(df["operator_name"].unique().tolist())
        sel_op = st.selectbox("Operator", operators)
    with c4:
        statuses = ["All"] + sorted(df["status"].unique().tolist())
        sel_status = st.selectbox("Status", statuses)

    if sel_bath   != "All": df = df[df["bath_name"]    == sel_bath]
    if sel_client != "All": df = df[df["client_name"]  == sel_client]
    if sel_op     != "All": df = df[df["operator_name"]== sel_op]
    if sel_status != "All": df = df[df["status"]       == sel_status]

    st.caption(f"{len(df)} run(s) shown")

    st.dataframe(
        df[MANAGER_COLS],
        use_container_width=True,
        hide_index=True,
        column_config=COLUMN_CONFIG,
    )