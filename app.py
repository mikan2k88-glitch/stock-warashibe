from flask import Flask, jsonify

app = Flask(__name__)


@app.get("/")
def index():
    return jsonify({"app": "stock-warashibe", "version": "0.1.0", "mode": "backtest-only"})


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
