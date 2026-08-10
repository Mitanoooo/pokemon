import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scraper import db

conn = st.session_state.get("conn")
if conn is None:
    st.error("No database connection.")
    st.stop()

st.title("Site Health")

rows = db.get_site_health(conn)

if not rows:
    st.info("No sites in the database yet.")
    st.stop()

df = pd.DataFrame(rows)
df.columns = ["Site", "Last Scraped", "Consecutive Failures", "Last Error"]

broken = df[df["Consecutive Failures"] >= 2]
healthy = df[df["Consecutive Failures"] < 2]

if not broken.empty:
    st.subheader("Broken Sites")
    st.dataframe(
        broken.style.map(lambda _: "background-color: #ffcccc"),
        use_container_width=True,
        hide_index=True,
    )

st.subheader("Healthy Sites")
if healthy.empty:
    st.info("No healthy sites.")
else:
    st.dataframe(healthy, use_container_width=True, hide_index=True)
