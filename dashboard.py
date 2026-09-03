from flask import Flask
from inventory import devices

app = Flask(__name__)

LOG_FILE = "/root/automation-toolkit/backups/drift_check.log"


def get_latest_status():
    """
    Reads drift_check.log and returns the most recent status line
    for each device. The log is append-only, so later lines in the
    file are more recent -- we read top to bottom and let later
    matches overwrite earlier ones, leaving only the latest per device.
    """
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
            color = "red"
            label = "ALERT"
        elif "OK" in line:
            color = "green"
            label = "OK"
        else:
            color = "gray"
            label = "UNKNOWN"

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
    <body style="font-family: sans-serif;">
        <h1>Device Status</h1>
        <table border="1" cellpadding="8" style="border-collapse: collapse;">
            <tr>
                <th>Device</th>
                <th>Status</th>
                <th>Last Check</th>
            </tr>
            {rows}
        </table>
    </body>
    </html>
    """
    return html


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
