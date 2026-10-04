from flask import Flask, jsonify

from backtest.demo_runner import run_demo_comparison
from backtest.readiness_gate import run_real_data_readiness_gate
from operations.dashboard import fetch_runtime_dashboard

app = Flask(__name__)


@app.get("/")
def index():
    return jsonify({"app": "stock-warashibe", "version": "0.3.0", "mode": "research-and-paper-gated"})


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/backtest/demo")
def backtest_demo():
    return jsonify(run_demo_comparison())


@app.get("/readiness/real-data")
def real_data_readiness():
    return jsonify(run_real_data_readiness_gate())


@app.get("/status/runtime")
@app.get("/status")
def runtime_status():
    try:
        return jsonify(fetch_runtime_dashboard())
    except Exception:
        return jsonify({
            "app": "stock-warashibe",
            "endpoint": "050",
            "status": "unavailable",
            "live_trading_allowed": False,
            "broker_connected": False,
        }), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
