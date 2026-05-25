import os
import uuid
from datetime import datetime, timezone
from flask import Flask, request, render_template_string, make_response
from flask_restx import Api, Resource

app = Flask(__name__)
api = Api(app, title="Training Data Upload")

UPLOAD_DIR = "/app/data/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

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

ns = api.namespace("upload", description="Upload endpoints")

@ns.route("/")
class UploadPage(Resource):
    def get(self):
        return make_response(render_template_string(UPLOAD_HTML), 200)

@ns.route("/training-data")
class TrainingUpload(Resource):
    def post(self):
        if "file" not in request.files:
            api.abort(400, "No file — field name must be 'file'")
        f = request.files["file"]
        if not f.filename.endswith(".csv"):
            api.abort(400, "Only .csv files accepted")
        filename = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}.csv"
        f.save(os.path.join(UPLOAD_DIR, filename))
        return {"status": "saved", "filename": filename}, 200

    def get(self):
        files = sorted(os.listdir(UPLOAD_DIR))
        return {"files": files, "count": len(files)}, 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
