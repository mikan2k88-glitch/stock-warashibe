from flask import Flask, jsonify

from backtest.demo_runner import run_demo_comparison
from backtest.readiness_gate import run_real_data_readiness_gate

app = Flask(__name__)


@app.get("/")
def index():
    return jsonify({"app": "stock-warashibe", "version": "0.2.0", "mode": "backtest-only"})


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/backtest/demo")
def backtest_demo():
    return jsonify(run_demo_comparison())


@app.get("/readiness/real-data")
def real_data_readiness():
    return jsonify(run_real_data_readiness_gate())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
