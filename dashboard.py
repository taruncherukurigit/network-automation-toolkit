from flask import Flask, send_file
from inventory import devices

app = Flask(__name__)

LOG_FILE = "/root/automation-toolkit/backups/drift_check.log"
TOPOLOGY_SVG = "/root/automation-toolkit/topology.svg"

NAV = """
<div style="font-family: sans-serif; padding: 10px; background:#111; color:#eee;">
    <a href="/" style="color:#3ddad7; margin-right:20px; text-decoration:none;">Device Status</a>
    <a href="/topology" style="color:#3ddad7; text-decoration:none;">Network Topology</a>
</div>
"""

def get_latest_status():
    statuses = {}
    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return statuses
    for device in devices:
        device_name = device["device_name"]
        for line in lines:
            if f"OK: {device_name}" in line or f"ALERT: {device_name}" in line:
                statuses[device_name] = line.strip()
    return statuses

@app.route("/")
def status():
    statuses = get_latest_status()
    rows = ""
    for device in devices:
        device_name = device["device_name"]
        line = statuses.get(device_name, "No data yet")
        if "ALERT" in line:
            color, label = "red", "ALERT"
        elif "OK" in line:
            color, label = "green", "OK"
        else:
            color, label = "gray", "UNKNOWN"
        rows += f"""
        <tr>
            <td>{device_name}</td>
            <td style="color:{color}; font-weight:bold;">{label}</td>
            <td>{line}</td>
        </tr>
        """
    html = f"""
    <html>
    <head><title>Cherwood Network Solutions - Status</title></head>
    <body style="font-family: sans-serif; margin:0;">
        {NAV}
        <div style="padding: 20px;">
            <h1>Device Status</h1>
            <table border="1" cellpadding="8" style="border-collapse: collapse;">
                <tr><th>Device</th><th>Status</th><th>Last Check</th></tr>
                {rows}
            </table>
        </div>
    </body>
    </html>
    """
    return html

@app.route("/topology")
def topology():
    html = f"""
    <html>
    <head><title>Cherwood Network Solutions - Topology</title></head>
    <body style="background:#0a0e14; margin:0;">
        {NAV}
        <div style="display:flex; justify-content:center; align-items:center; padding: 30px;">
            <img src="/topology.svg" style="max-width:95%; height:auto;">
        </div>
    </body>
    </html>
    """
    return html

@app.route("/topology.svg")
def topology_svg():
    return send_file(TOPOLOGY_SVG, mimetype="image/svg+xml")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)