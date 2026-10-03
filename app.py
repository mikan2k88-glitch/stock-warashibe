from flask import Flask, jsonify

from backtest.demo_runner import run_demo_comparison

app = Flask(__name__)


@app.get("/")
def index():
    return jsonify({"app": "stock-warashibe", "version": "0.1.0", "mode": "backtest-only"})


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/backtest/demo")
def backtest_demo():
    return jsonify(run_demo_comparison())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
