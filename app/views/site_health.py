import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from app import ui
from scraper import db

conn = ui.connection()

st.title("Site Health")

rows = db.get_site_health(conn)

if not rows:
    st.info("No sites in the database yet.")
    st.stop()

df = pd.DataFrame(rows)
df.columns = ["Site", "Last Scraped", "Consecutive Failures", "Skipped (no price)", "Last Error"]

broken = df[df["Consecutive Failures"] >= 2]
healthy = df[df["Consecutive Failures"] < 2]

if not broken.empty:
    st.subheader("Broken Sites")
    st.dataframe(
        broken.style.map(lambda _: "background-color: #ffcccc"),
        width="stretch",
        hide_index=True,
    )

st.subheader("Healthy Sites")
if healthy.empty:
    st.info("No healthy sites.")
else:
    st.dataframe(healthy, width="stretch", hide_index=True)
