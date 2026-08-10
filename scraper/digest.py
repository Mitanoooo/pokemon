"""Digest emailer — build and send a price-alert HTML email."""
import smtplib
import sqlite3
import sys
from collections import defaultdict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from scraper import db


def build_digest(conn: sqlite3.Connection) -> "Optional[tuple[str, int]]":
    rows = db.get_products_below_threshold(conn)
    if not rows:
        return None

    by_product: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_product[row["canonical_name"]].append(row)

    n_products = len(by_product)

    table_rows = []
    for product_name, entries in sorted(by_product.items()):
        for i, e in enumerate(entries):
            name_cell = (
                f'<td rowspan="{len(entries)}">{product_name}</td>'
                f'<td rowspan="{len(entries)}">{e["threshold"]:.2f}</td>'
                if i == 0
                else ""
            )
            table_rows.append(
                f"<tr>"
                f"{name_cell}"
                f'<td><a href="{e["site_url"]}">{e["site_name"]}</a></td>'
                f'<td>{e["price"]:.2f}</td>'
                f'<td>{e["currency"]}</td>'
                f"</tr>"
            )

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: sans-serif; font-size: 14px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; }}
  th {{ background: #f0f0f0; }}
  a {{ color: #1a73e8; }}
</style>
</head>
<body>
<h2>Pokemon price alert</h2>
<table>
  <thead>
    <tr>
      <th>Product</th><th>Threshold</th><th>Site</th><th>Price</th><th>Currency</th>
    </tr>
  </thead>
  <tbody>
    {"".join(table_rows)}
  </tbody>
</table>
</body>
</html>"""
    return html, n_products


def send_digest(
    html_body: str,
    n_products: int,
    smtp_cfg: Optional[dict],
    file_transport: Optional[str] = None,
) -> None:
    """Send the digest HTML.

    When file_transport is set, writes the HTML to that path instead of
    sending via SMTP — used for local testing before email is configured.
    """
    if file_transport is not None:
        with open(file_transport, "w", encoding="utf-8") as f:
            f.write(html_body)
        return

    if smtp_cfg is None:
        raise ValueError("smtp_cfg required when file_transport is not set")

    subject = f"Pokemon price alert — {n_products} product(s) below threshold"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_cfg["user"]
    msg["To"] = smtp_cfg["to"]
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.login(smtp_cfg["user"], smtp_cfg["app_password"])
        server.sendmail(smtp_cfg["user"], smtp_cfg["to"], msg.as_string())


def _main() -> None:
    import os
    from dotenv import load_dotenv

    load_dotenv()

    db_path = os.getenv("DB_PATH", "pokemon.db")
    file_out = os.getenv("DIGEST_FILE_TRANSPORT")  # set this to skip SMTP during dev

    conn = db.get_connection(db_path)
    result = build_digest(conn)

    if result is None:
        print("Nothing below threshold — no email sent")
        return

    html, n_products = result

    if file_out:
        send_digest(html, n_products, smtp_cfg=None, file_transport=file_out)
        print(f"Digest written to {file_out} (file transport — SMTP not configured)")
        return

    smtp_cfg = {
        "user": os.environ["GMAIL_USER"],
        "app_password": os.environ["GMAIL_APP_PASSWORD"],
        "to": os.environ["DIGEST_TO"],
    }
    send_digest(html, n_products, smtp_cfg=smtp_cfg)
    print(f"Digest sent — {n_products} product(s)")


if __name__ == "__main__":
    _main()
