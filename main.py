import tls_client
import threading
import time
import re
import urllib.parse
from flask import Flask, render_template_string, request, jsonify
from flask_socketio import SocketIO, emit

app = Flask(__name__)
socketio = SocketIO(app, async_mode='eventlet')

class State:
    running = False
    thread_count = 1
    report_url = ""
    report_type = 90013
    success = 0
    failed = 0
    threads = []
    log = []

REPORT_TYPES = {
    90013: "Violence", 90014: "Sexual Abuse", 90016: "Animal Abuse",
    90017: "Criminal Activities", 9020: "Hate", 9007: "Bullying",
    90061: "Suicide Or Self-Harm", 90064: "Dangerous Content",
    90084: "Sexual Content", 90085: "Porn", 90037: "Drugs",
    90038: "Firearms Or Weapons", 9018: "Sharing Personal Info",
    90015: "Human Exploitation", 91015: "Under Age"
}

def report_loop():
    session = tls_client.Session(client_identifier="chrome112", random_tls_extension_order=True)
    while State.running:
        try:
            reason_format = re.search(r'reason=(\d+)', State.report_url)
            nickname_format = re.search(r'nickname=([^&]+)', State.report_url)
            username = urllib.parse.unquote(nickname_format.group(1)) if nickname_format else "Unknown"

            if reason_format:
                report_url = State.report_url.replace(f"reason={reason_format.group(1)}", f"reason={State.report_type}")
                response = session.get(report_url)
                success = ("Thanks for your feedback" in response.text or response.status_code == 200)

                if success:
                    State.success += 1
                else:
                    State.failed += 1

                State.log.append({"user": username, "success": success})
        except Exception:
            State.failed += 1

        time.sleep(1)

@app.route('/')
def index():
    return render_template_string("""
    <html>
    <head>
        <title>Mass Reporter</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script src="https://cdn.socket.io/4.4.1/socket.io.min.js"></script>
        <style>
            body { font-family: sans-serif; padding: 40px; background: #f9f9f9; }
            input, select, button { padding: 10px; margin: 5px; width: 100%; max-width: 400px; }
        </style>
    </head>
    <body>
        <h1>TikTok Mass Reporter</h1>
        <form id="control-form">
            <label>Report URL:</label><br/>
            <input type="text" name="report_url" value="{{url}}" required/><br/>
            <label>Number of Threads:</label><br/>
            <input type="number" name="threads" min="1" max="100" value="{{threads}}" required/><br/>
            <label>Report Type:</label><br/>
            <select name="report_type">
                {% for code, name in report_types.items() %}
                    <option value="{{code}}" {% if code == selected_type %}selected{% endif %}>{{name}}</option>
                {% endfor %}
            </select><br/>
            <button type="submit">{{'Stop' if running else 'Start'}}</button>
        </form>
        <h3>Status</h3>
        <p>Running: <b id="running-status">{{running}}</b></p>
        <canvas id="statsChart" width="400" height="200"></canvas>
        <h3>Reported Users</h3>
        <ul id="user-log"></ul>

        <script>
            const socket = io();
            const form = document.getElementById('control-form');
            const userLog = document.getElementById('user-log');
            let chart;

            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(form);
                const data = Object.fromEntries(formData.entries());
                const response = await fetch('/toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                window.location.reload();
            });

            socket.on('stats', (data) => {
                document.getElementById('running-status').innerText = data.running;
                const ctx = document.getElementById('statsChart').getContext('2d');
                if (!chart) {
                    chart = new Chart(ctx, {
                        type: 'bar',
                        data: {
                            labels: ['Success', 'Failed'],
                            datasets: [{
                                label: 'Reports',
                                data: [data.success, data.failed],
                                backgroundColor: ['#2ecc71', '#e74c3c']
                            }]
                        },
                        options: { scales: { y: { beginAtZero: true } } }
                    });
                } else {
                    chart.data.datasets[0].data = [data.success, data.failed];
                    chart.update();
                }

                userLog.innerHTML = data.log.slice(-10).reverse().map(entry => `<li>${entry.user}: <b style='color:${entry.success ? 'green' : 'red'}'>${entry.success ? 'Success' : 'Failed'}</b></li>`).join('');
            });
        </script>
    </body>
    </html>
    """, url=State.report_url, threads=State.thread_count,
           selected_type=State.report_type, report_types=REPORT_TYPES,
           running=State.running)

@app.route('/toggle', methods=['POST'])
def toggle():
    data = request.get_json()
    State.report_url = data['report_url']
    State.thread_count = int(data['threads'])
    State.report_type = int(data['report_type'])

    if not State.running:
        State.running = True
        State.success = 0
        State.failed = 0
        State.log = []
        State.threads = []
        for _ in range(State.thread_count):
            t = threading.Thread(target=report_loop)
            t.start()
            State.threads.append(t)
    else:
        State.running = False
    return jsonify({"status": "toggled", "running": State.running})

@socketio.on('connect')
def on_connect():
    def emit_stats():
        while True:
            socketio.emit('stats', {
                'success': State.success,
                'failed': State.failed,
                'log': State.log[-10:],
                'running': State.running
            })
            socketio.sleep(1)

    socketio.start_background_task(emit_stats)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=3000)
