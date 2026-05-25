import os, json, uuid
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from flask_restx import Api, Resource
from flask import Flask, request, jsonify, render_template_string

UPLOAD_HTML = """
<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:500px;margin:60px auto;padding:20px">
  <h2>Upload Training CSV</h2>
  <form method="POST" action="/upload/training-data" enctype="multipart/form-data">
    <input type="file" name="file" accept=".csv" required>
    <br><br>
    <button type="submit">Upload</button>
  </form>
</body>
</html>
"""

@ns.route("/")
class UploadPage(Resource):
    def get(self):
        """Simple upload form."""
        from flask import make_response
        return make_response(render_template_string(UPLOAD_HTML), 200)

app = Flask(__name__)
api = Api(app, title="Training Data Upload",
          description="Drop new CSV training data for virtual_sensor_ml retraining")

UPLOAD_DIR = "/app/data/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ns = api.namespace("upload", description="Upload endpoints")

@ns.route("/training-data")
class TrainingUpload(Resource):
    def post(self):
        """Upload a CSV file to retrain the ML virtual sensor."""
        if "file" not in request.files:
            api.abort(400, "No file provided — field name must be 'file'")
        f = request.files["file"]
        if not f.filename.endswith(".csv"):
            api.abort(400, "Only .csv files accepted")
        filename = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}.csv"
        path = os.path.join(UPLOAD_DIR, filename)
        f.save(path)

        return {"status": "saved", "filename": filename}, 200

    def get(self):
        """List uploaded training files."""
        files = sorted(os.listdir(UPLOAD_DIR))
        return {"files": files, "count": len(files)}, 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)