from flask import Blueprint, render_template, Response, stream_with_context
import subprocess, sys, os
from app.auth import login_required
from app.data import add_alert

pipeline_bp = Blueprint("pipeline", __name__)


@pipeline_bp.route("/pipeline")
@login_required
def pipeline():
    return render_template("pipeline.html")


@pipeline_bp.route("/api/pipeline/run")
@login_required
def run_pipeline():
    def generate():
        yield f"data: {{\"type\": \"start\", \"message\": \"SITREP pipeline initiated...\"}}\n\n"

        script = "scripts/run_v2_5.py"
        if not os.path.exists(script):
            yield f"data: {{\"type\": \"error\", \"message\": \"Pipeline script not found\"}}\n\n"
            return

        process = subprocess.Popen(
            [sys.executable, script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )

        for line in iter(process.stdout.readline, ""):
            line = line.rstrip()
            if not line:
                continue
            msg_type = "log"
            if any(x in line for x in ["ERROR","error","failed","Failed"]):
                msg_type = "error"
            elif any(x in line for x in ["Done","complete","Complete","written","found"]):
                msg_type = "success"
            elif line.startswith("[") or "Step" in line or "═" in line or "─" in line:
                msg_type = "step"
            safe = line.replace("'","\\'").replace('"','\\"')
            yield f"data: {{\"type\": \"{msg_type}\", \"message\": \"{safe}\"}}\n\n"

        process.wait()
        if process.returncode == 0:
            add_alert("Pipeline complete — new jobs available. Check dashboard.", "success")
            yield f"data: {{\"type\": \"complete\", \"message\": \"Pipeline complete. Refresh dashboard.\"}}\n\n"
        else:
            yield f"data: {{\"type\": \"error\", \"message\": \"Pipeline exited with code {process.returncode}\"}}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"},
    )
