import csv
import io
import json
import logging
import os
import threading
from datetime import datetime, timezone
from train_model import BUSY_THRESHOLD

import paho.mqtt.client as mqtt
from flask import Flask, Response
from flask_restx import Api, Resource, fields, reqparse

logger = logging.getLogger(__name__)

from database import (
    DB_PATH,
    get_connection,
    insert_mqtt_message,
    QUERY_PEAK_HOUR,
    QUERY_LEAST_HOUR,
    QUERY_WEEKLY_HEATMAP,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


app = Flask(__name__)

MQTT_BROKER = os.environ.get("MQTT_BROKER", "mosquitto")
MQTT_PORT   = int(os.environ.get("MQTT_PORT", 1883))

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ML_DIR    = os.path.join(_BASE_DIR, "models_v_s")

# ── DB connection (schema created by consumer; API is read + command-publish only) ──
db_conn = get_connection(DB_PATH)
db_lock = threading.Lock()

# ── MQTT client — publish-only ────────────────────────────────────────────────
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "wastebin-api")


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        logger.info("[MQTT] Connected to broker — publish-only mode.")
    else:
        logger.error("[MQTT] Connection failed rc=%s", reason_code)


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    if reason_code != 0:
        logger.warning("[MQTT] Unexpected disconnect (rc=%s). Will auto-reconnect...", reason_code)


mqtt_client.on_connect    = on_connect
mqtt_client.on_disconnect = on_disconnect

try:
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
    mqtt_client.loop_start()
except Exception as e:
    logger.error("[MQTT] Initial connection error: %s", e)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_dict(row) -> dict:
    return dict(row) if row else {}


def _rows_to_list(rows) -> list:
    return [dict(r) for r in rows]



api = Api(
    app,
    version="2.0",
    title="Smart Wastebin API",
    description="REST API — all data served from SQLite. Full Swagger UI.",
)

ns      = api.namespace("bins",    description="Bin operations")
nsensor = api.namespace("sensors", description="Sensor operations")
nmqtt   = api.namespace("mqtt",    description="MQTT operations")
nsml    = api.namespace("ml",      description="Machine-learning operations")


bin_model = api.model("Bin", {
    "bin_id":     fields.String(required=True),
    "bin_uri":    fields.String(),
    "name":       fields.String(),
    "location":   fields.String(),
    "status":     fields.String(),
    "created_at": fields.String(),
})

sensor_model = api.model("Sensor", {
    "sensor_id":   fields.String(required=True),
    "sensor_uri":  fields.String(),
    "sensor_type": fields.String(),
    "model":       fields.String(),
    "status":      fields.String(),
    "bin_id":      fields.String(description="Bin this sensor is mounted on"),
})

event_model = api.model("PIREvent", {
    "id":                  fields.Integer(),
    "event_id":            fields.String(),
    "sensor_id":           fields.String(),
    "bin_id":              fields.String(),
    "event_time":          fields.String(),
    "ingest_time":         fields.String(),
    "motion_state":        fields.String(),
    "seq":                 fields.Integer(),
    "run_id":              fields.String(),
    "item_count":          fields.Integer(),
    "fill_level":          fields.Integer(),
    "pipeline_latency_ms": fields.Float(),
})

usage_model = api.model("BinUsage", {
    "bin_id":      fields.String(),
    "day_of_week": fields.Integer(description="0=Mon … 6=Sun"),
    "hour":        fields.Integer(description="0-23"),
    "usage_count": fields.Integer(),
})

peak_model = api.model("PeakHour", {
    "bin_id":      fields.String(),
    "day_of_week": fields.Integer(),
    "hour":        fields.Integer(),
    "usage_count": fields.Integer(),
    "label":       fields.String(),
})

emptied_model = api.model("EmptiedRecord", {
    "bin_id":     fields.String(),
    "emptied_at": fields.String(),
    "emptied_by": fields.String(),
})

emptied_input_model = api.model("EmptiedInput", {
    "emptied_by": fields.String(default="operator",
                                description="Who emptied the bin (optional)"),
})

topic_model = api.model("MQTTTopic", {
    "topic":     fields.String(),
    "payload":   fields.String(),
    "qos":       fields.Integer(),
    "retain":    fields.Boolean(),
    "timestamp": fields.String(),
})

topics_list_model = api.model("MQTTTopicList", {
    "topic_count": fields.Integer(),
    "topics":      fields.List(fields.Nested(topic_model)),
})

subscribe_input_model = api.model("MQTTSubscribeInput", {
    "topic": fields.String(required=True),
    "qos":   fields.Integer(default=1),
})

publish_model = api.model("MQTTPublish", {
    "topic":   fields.String(required=True),
    "payload": fields.String(required=True),
    "qos":     fields.Integer(default=1),
    "retain":  fields.Boolean(default=False),
})

mqtt_msg_model = api.model("MQTTMessage", {
    "id":          fields.Integer(),
    "bin_id":      fields.String(),
    "topic":       fields.String(),
    "payload":     fields.String(),
    "qos":         fields.Integer(),
    "retained":    fields.Boolean(),
    "received_at": fields.String(),
})

predict_model = api.model("MLPrediction", {
    "prediction":     fields.String(),
    "confidence":     fields.Float(),
    "predicted_hour": fields.Integer(),
    "day_of_week":    fields.Integer(),
    "is_weekend":     fields.Boolean(),
    "timestamp":      fields.String(),
})

retrain_model = api.model("MLRetrain", {
    "status":                fields.String(),
    "samples_used":          fields.Integer(),
    "model_path":            fields.String(),
    "classification_report": fields.String(),
})


limit_parser = reqparse.RequestParser()
limit_parser.add_argument("limit", type=int, default=50, help="Max rows to return")

day_parser = reqparse.RequestParser()
day_parser.add_argument("day", type=int, default=0, help="Day of week: 0=Mon … 6=Sun")

mqtt_parser = reqparse.RequestParser()
mqtt_parser.add_argument("limit", type=int, default=100, help="Max messages to return")



@ns.route("/")
class BinList(Resource):
    @ns.marshal_list_with(bin_model)
    def get(self):
        """List all bins."""
        with db_lock:
            rows = db_conn.execute("SELECT * FROM Bins ORDER BY bin_id").fetchall()
        return _rows_to_list(rows), 200


@ns.route("/<string:bin_id>")
class BinDetail(Resource):
    @ns.marshal_with(bin_model)
    @ns.response(404, "Bin not found")
    def get(self, bin_id):
        with db_lock:
            row = db_conn.execute(
                "SELECT * FROM Bins WHERE bin_id=?", (bin_id,)
            ).fetchone()
        if not row:
            api.abort(404, f"Bin '{bin_id}' not found")
        return _row_to_dict(row), 200


@ns.route("/<string:bin_id>/events")
class BinEvents(Resource):
    @ns.expect(limit_parser)
    @ns.marshal_list_with(event_model)
    @ns.response(404, "Bin not found")
    def get(self, bin_id):
        args = limit_parser.parse_args()
        with db_lock:
            if not db_conn.execute(
                "SELECT 1 FROM Bins WHERE bin_id=?", (bin_id,)
            ).fetchone():
                api.abort(404, f"Bin '{bin_id}' not found")
            rows = db_conn.execute(
                "SELECT * FROM PIR_Events WHERE bin_id=? ORDER BY event_time DESC LIMIT ?",
                (bin_id, args["limit"])
            ).fetchall()
        return _rows_to_list(rows), 200


@ns.route("/<string:bin_id>/usage")
class BinUsage(Resource):
    @ns.marshal_list_with(usage_model)
    @ns.response(404, "Bin not found")
    def get(self, bin_id):
        with db_lock:
            if not db_conn.execute(
                "SELECT 1 FROM Bins WHERE bin_id=?", (bin_id,)
            ).fetchone():
                api.abort(404, f"Bin '{bin_id}' not found")
            rows = db_conn.execute(QUERY_WEEKLY_HEATMAP, {"bin_id": bin_id}).fetchall()
        return _rows_to_list(rows), 200


@ns.route("/<string:bin_id>/usage/peak")
class BinPeakHour(Resource):
    @ns.expect(day_parser)
    @ns.marshal_with(peak_model)
    @ns.response(404, "No usage data found")
    def get(self, bin_id):
        args = day_parser.parse_args()
        dow  = args["day"]
        with db_lock:
            row = db_conn.execute(
                QUERY_PEAK_HOUR, {"bin_id": bin_id, "day_of_week": dow}
            ).fetchone()
        if not row:
            api.abort(404, "No usage data for this bin/day")
        result = dict(row)
        result.update({"bin_id": bin_id, "day_of_week": dow, "label": "peak"})
        return result, 200


@ns.route("/<string:bin_id>/usage/least")
class BinLeastHour(Resource):
    @ns.expect(day_parser)
    @ns.marshal_with(peak_model)
    @ns.response(404, "No usage data found")
    def get(self, bin_id):
        """Least-active hour for a bin on a specific day (0=Mon … 6=Sun)."""
        args = day_parser.parse_args()
        dow  = args["day"]
        with db_lock:
            row = db_conn.execute(
                QUERY_LEAST_HOUR, {"bin_id": bin_id, "day_of_week": dow}
            ).fetchone()
        if not row:
            api.abort(404, "No usage data for this bin/day")
        result = dict(row)
        result.update({"bin_id": bin_id, "day_of_week": dow, "label": "least"})
        return result, 200


@ns.route("/<string:bin_id>/empty")
class BinEmpty(Resource):
    @ns.expect(emptied_input_model)
    @ns.marshal_with(emptied_model)
    @ns.response(404, "Bin not found")
    @ns.response(503, "MQTT publish failed")
    def post(self, bin_id):
        with db_lock:
            if not db_conn.execute(
                "SELECT 1 FROM Bins WHERE bin_id=?", (bin_id,)
            ).fetchone():
                api.abort(404, f"Bin '{bin_id}' not found")

        payload_data = api.payload or {}
        emptied_by   = payload_data.get("emptied_by", "operator")
        emptied_at   = utc_now_iso()

        cmd_topic   = f"smartbin/{bin_id}/command"
        cmd_payload = json.dumps({
            "action":     "emptied",
            "emptied_at": emptied_at,
            "emptied_by": emptied_by,
        })

        result = mqtt_client.publish(cmd_topic, cmd_payload, qos=1)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            api.abort(503, f"Failed to publish MQTT command (rc={result.rc})")

        with db_lock:
            insert_mqtt_message(db_conn, cmd_topic, cmd_payload, 1, False, bin_id)

        mqtt_client.publish(
            f"smartbin/{bin_id}/status",
            json.dumps({"state": "emptied", "emptied_at": emptied_at}),
            qos=1, retain=True,
        )

        return {"bin_id": bin_id, "emptied_at": emptied_at, "emptied_by": emptied_by}, 200


@ns.route("/<string:bin_id>/emptied-history")
class BinEmptiedHistory(Resource):
    @ns.expect(limit_parser)
    def get(self, bin_id):
        args = limit_parser.parse_args()
        with db_lock:
            rows = db_conn.execute(
                """SELECT id, bin_id, topic, payload, received_at AS emptied_at
                   FROM MQTT_Messages
                   WHERE bin_id=? AND topic LIKE '%/command'
                   ORDER BY received_at DESC LIMIT ?""",
                (bin_id, args["limit"])
            ).fetchall()
        return _rows_to_list(rows), 200


@ns.route("/<string:bin_id>/usage_data")
class BinUsageCSV(Resource):
    @ns.produces(["text/csv"])
    @ns.response(200, "CSV file download")
    @ns.response(404, "Bin not found")
    def get(self, bin_id):
        with db_lock:
            if not db_conn.execute(
                "SELECT 1 FROM Bins WHERE bin_id=?", (bin_id,)
            ).fetchone():
                api.abort(404, f"Bin '{bin_id}' not found")
            rows = db_conn.execute(QUERY_WEEKLY_HEATMAP, {"bin_id": bin_id}).fetchall()

        usage_lookup: dict[tuple[int, int], int] = {
            (r["day_of_week"], r["hour"]): r["usage_count"] for r in rows
        }

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["day_of_week", "hour", "is_weekend", "event_count", "label"])
        for dow in range(7):
            is_weekend = 1 if dow in (5, 6) else 0
            for hour in range(24):
                count = usage_lookup.get((dow, hour), 0)
                label = "busy" if count >= BUSY_THRESHOLD else "quiet"
                writer.writerow([dow, hour, is_weekend, count, label])

        return Response(
            output.getvalue().encode("utf-8"),
            status=200,
            mimetype="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="usage_data_{bin_id}.csv"',
                "Content-Type": "text/csv; charset=utf-8",
            },
        )



@nsensor.route("/")
class SensorList(Resource):
    @nsensor.marshal_list_with(sensor_model)
    def get(self):
        """List all sensors with their mounted bin."""
        with db_lock:
            rows = db_conn.execute("""
                SELECT s.*, m.bin_id
                FROM   Sensors s
                LEFT   JOIN Mounted_On m ON s.sensor_id = m.sensor_id
                ORDER  BY s.sensor_id
            """).fetchall()
        return _rows_to_list(rows), 200


@nsensor.route("/<string:sensor_id>")
class SensorDetail(Resource):
    @nsensor.marshal_with(sensor_model)
    @nsensor.response(404, "Sensor not found")
    def get(self, sensor_id):
        with db_lock:
            row = db_conn.execute("""
                SELECT s.*, m.bin_id
                FROM   Sensors s
                LEFT   JOIN Mounted_On m ON s.sensor_id = m.sensor_id
                WHERE  s.sensor_id = ?
            """, (sensor_id,)).fetchone()
        if not row:
            api.abort(404, f"Sensor '{sensor_id}' not found")
        return _row_to_dict(row), 200


@nsensor.route("/<string:sensor_id>/events")
class SensorEvents(Resource):
    @nsensor.expect(limit_parser)
    @nsensor.marshal_list_with(event_model)
    @nsensor.response(404, "Sensor not found")
    def get(self, sensor_id):
        args = limit_parser.parse_args()
        with db_lock:
            if not db_conn.execute(
                "SELECT 1 FROM Sensors WHERE sensor_id=?", (sensor_id,)
            ).fetchone():
                api.abort(404, f"Sensor '{sensor_id}' not found")
            rows = db_conn.execute(
                "SELECT * FROM PIR_Events WHERE sensor_id=? ORDER BY event_time DESC LIMIT ?",
                (sensor_id, args["limit"])
            ).fetchall()
        return _rows_to_list(rows), 200



@nmqtt.route("/publish")
class MQTTPublish(Resource):
    @nmqtt.expect(publish_model)
    @nmqtt.response(200, "Message published")
    @nmqtt.response(400, "Invalid request")
    def post(self):
        """Publish a raw message to any MQTT topic."""
        data    = api.payload or {}
        topic   = data.get("topic")
        payload = data.get("payload")
        qos     = data.get("qos", 1)
        retain  = data.get("retain", False)

        if not topic or not payload:
            api.abort(400, "Both 'topic' and 'payload' are required")
        if qos not in (0, 1, 2):
            api.abort(400, "QoS must be 0, 1, or 2")

        result = mqtt_client.publish(topic, payload, qos=qos, retain=retain)
        return {
            "status":  "published",
            "topic":   topic,
            "payload": payload,
            "qos":     qos,
            "retain":  retain,
            "mqtt_rc": result.rc,
        }, 200


@nmqtt.route("/messages")
class MQTTMessageList(Resource):
    @nmqtt.expect(mqtt_parser)
    @nmqtt.marshal_list_with(mqtt_msg_model)
    def get(self):
        args = mqtt_parser.parse_args()
        with db_lock:
            rows = db_conn.execute(
                "SELECT * FROM MQTT_Messages ORDER BY received_at DESC LIMIT ?",
                (args["limit"],)
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["retained"] = bool(d.get("retained", 0))
            result.append(d)
        return result, 200


@nmqtt.route("/messages/<string:bin_id>")
class MQTTMessagesByBin(Resource):
    @nmqtt.expect(mqtt_parser)
    @nmqtt.marshal_list_with(mqtt_msg_model)
    def get(self, bin_id):
        args = mqtt_parser.parse_args()
        with db_lock:
            rows = db_conn.execute(
                """SELECT * FROM MQTT_Messages WHERE bin_id=?
                   ORDER BY received_at DESC LIMIT ?""",
                (bin_id, args["limit"])
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["retained"] = bool(d.get("retained", 0))
            result.append(d)
        return result, 200



@nsml.route("/retrain")
class MLRetrain(Resource):
    @nsml.marshal_with(retrain_model)
    def post(self):
        try:
            from train_model import train_from_db
            clf, report, n_samples, model_path = train_from_db(DB_PATH, ML_DIR)
            return {
                "status":                "ok",
                "samples_used":          n_samples,
                "model_path":            model_path,
                "classification_report": report,
            }, 200
        except ValueError as exc:
            from train_model import train_from_pseudo
            clf, report, n_samples, model_path = train_from_pseudo(ML_DIR)
            return {
                "status":                f"fallback_pseudo ({exc})",
                "samples_used":          n_samples,
                "model_path":            model_path,
                "classification_report": report,
            }, 200
        except Exception as exc:
            api.abort(500, str(exc))


@nsml.route("/predict")
class MLPredict(Resource):
    @nsml.marshal_with(predict_model)
    def get(self):
        import joblib
        import pandas as pd

        model_path = os.path.join(ML_DIR, "busy_predictor.joblib")
        if not os.path.exists(model_path):
            api.abort(503, "Model not trained yet — POST /ml/retrain first.")

        clf       = joblib.load(model_path)
        now       = datetime.now()
        next_hour = (now.hour + 1) % 24
        dow       = now.weekday()
        is_wknd   = 1 if dow in (5, 6) else 0

        X          = pd.DataFrame([[dow, next_hour, is_wknd]],
                                  columns=["day_of_week", "hour", "is_weekend"])
        prediction = clf.predict(X)[0]
        proba      = clf.predict_proba(X)[0]
        confidence = float(proba[list(clf.classes_).index(prediction)])

        return {
            "prediction":     prediction,
            "confidence":     round(confidence, 3),
            "predicted_hour": next_hour,
            "day_of_week":    dow,
            "is_weekend":     bool(is_wknd),
            "timestamp":      utc_now_iso(),
        }, 200


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
