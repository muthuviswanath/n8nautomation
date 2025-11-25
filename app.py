from flask import Flask, request, jsonify
from scheduler import SchedulerEngine

app = Flask(__name__)
engine = SchedulerEngine()

@app.route("/optimize", methods=["POST"])
def optimize():
    data = request.get_json()
    result = engine.optimize_day(data)
    return jsonify(result)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(port=5000)
