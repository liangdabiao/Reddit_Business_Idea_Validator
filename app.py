import os
import sys
import re
import json
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory, abort

sys.path.insert(0, os.path.dirname(__file__))

app = Flask(__name__)

REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

tasks = {}


def run_analysis_task(task_id, idea, fast_mode=False):
    task = tasks[task_id]
    task["status"] = "running"
    task["progress"] = 5
    task["message"] = "启动分析流程..."

    try:
        cmd = [
            sys.executable,
            str(Path(__file__).parent / "run_agent.py"),
            idea,
        ]
        if fast_mode:
            cmd.append("--fast")

        task["message"] = "正在抓取 Reddit 数据..."
        task["progress"] = 10

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(Path(__file__).parent),
            bufsize=1,
        )

        output_lines = []
        last_lines = []

        for line in iter(process.stdout.readline, ""):
            output_lines.append(line)
            last_lines.append(line.strip())
            if len(last_lines) > 50:
                last_lines.pop(0)

            if "抓取帖子" in line or "数据抓取" in line or "scrape" in line.lower():
                task["progress"] = 15
                task["message"] = "正在抓取 Reddit 数据..."
            elif "analyze" in line.lower() or "分析帖子" in line or "帖子分析" in line:
                if task["progress"] < 30:
                    task["progress"] = 30
                    task["message"] = "正在分析帖子内容..."
            elif "tag" in line.lower() or "标签" in line:
                if task["progress"] < 55:
                    task["progress"] = 55
                    task["message"] = "正在生成标签体系..."
            elif "combined" in line.lower() or "综合分析" in line:
                if task["progress"] < 75:
                    task["progress"] = 75
                    task["message"] = "正在进行综合分析..."
            elif "report" in line.lower() or "报告" in line:
                if task["progress"] < 90:
                    task["progress"] = 90
                    task["message"] = "正在生成报告..."

        process.wait()
        full_output = "".join(output_lines)

        report_match = re.search(r"报告已保存:\s+路径:\s+(.+\.html)", full_output)
        score_match = re.search(r"综合评分:\s*(\d+)/100", full_output)
        summary_match = re.search(r"摘要:\s*(.+?)(?:\n\s*📄|$)", full_output, re.DOTALL)
        posts_match = re.search(r"笔记数:\s*(\d+)", full_output)
        comments_match = re.search(r"评论数:\s*(\d+)", full_output)

        if report_match:
            report_path = report_match.group(1).strip()
            task["status"] = "completed"
            task["progress"] = 100
            task["message"] = "分析完成！"
            task["result"] = {
                "report_path": report_path,
                "report_filename": os.path.basename(report_path),
                "score": score_match.group(1) if score_match else "N/A",
                "summary": summary_match.group(1).strip() if summary_match else "",
                "posts": posts_match.group(1) if posts_match else "0",
                "comments": comments_match.group(1) if comments_match else "0",
                "idea": idea,
            }
        else:
            task["status"] = "failed"
            task["message"] = "分析失败，未找到报告文件"
            task["error"] = full_output[-2000:]

    except Exception as e:
        task["status"] = "failed"
        task["message"] = f"分析出错: {str(e)}"
        task["error"] = str(e)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/tasks", methods=["POST"])
def create_task():
    data = request.get_json()
    idea = data.get("idea", "").strip()
    fast_mode = data.get("fast_mode", False)

    if not idea:
        return jsonify({"error": "请输入业务创意"}), 400

    task_id = str(int(time.time()))
    tasks[task_id] = {
        "id": task_id,
        "idea": idea,
        "fast_mode": fast_mode,
        "status": "pending",
        "progress": 0,
        "message": "",
        "result": None,
        "created_at": datetime.now().isoformat(),
    }

    thread = threading.Thread(
        target=run_analysis_task,
        args=(task_id, idea, fast_mode),
        daemon=True,
    )
    thread.start()

    return jsonify({"task_id": task_id})


@app.route("/api/tasks/<task_id>")
def get_task(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify(task)


@app.route("/api/reports")
def list_reports():
    files = list(REPORTS_DIR.glob("*.html"))
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    reports = []
    for f in files:
        match = re.match(r"(.+)_(\d{8}_\d{6})\.html", f.name)
        idea = f.name
        created_at = ""
        if match:
            idea = match.group(1)
            time_str = match.group(2)
            try:
                dt = datetime.strptime(time_str, "%Y%m%d_%H%M%S")
                created_at = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                created_at = time_str

        reports.append({
            "filename": f.name,
            "idea": idea,
            "created_at": created_at,
            "size_kb": round(f.stat().st_size / 1024, 1),
        })

    return jsonify({"reports": reports})


@app.route("/api/reports/<filename>")
def get_report(filename):
    safe_filename = os.path.basename(filename)
    file_path = REPORTS_DIR / safe_filename
    if not file_path.exists():
        abort(404)

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/reports/<path:filename>")
def serve_report(filename):
    return send_from_directory(str(REPORTS_DIR), filename)


if __name__ == "__main__":
    print("=" * 60)
    print("Reddit 商业创意分析 - Web 界面")
    print("=" * 60)
    print("访问地址: http://localhost:5000")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=False)
