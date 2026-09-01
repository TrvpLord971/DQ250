#!/usr/bin/env python3
"""Integrated local Flask app for BIN→SGO workflow (preview + tester)

Endpoints:
 - GET /            -> UI (Plotly heatmap + controls)
 - POST /api/preview -> JSON preview (calls extract_sgo_preview.py)
 - POST /api/heatmap -> generate PNG heatmap (calls make_heatmap.py)
 - POST /api/test    -> run virtual-CAN tester (calls bin_to_sgo_can_tester.py)

This is a minimal prototype that shells out to existing tools in files/.
"""
import os
import subprocess
import json
from flask import Flask, request, jsonify, send_from_directory, render_template
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / 'files'
EXTRACT = BASE / 'extract_sgo_preview.py'
MAKEHM = BASE / 'make_heatmap.py'
TESTER = BASE / 'bin_to_sgo_can_tester.py'
VISUALS = BASE / 'visuals'
VISUALS.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, template_folder=str(Path(__file__).parent / 'templates'))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/preview', methods=['POST'])
def api_preview():
    data = request.json or {}
    path = data.get('path')
    if not path:
        return jsonify({'ok': False, 'error': 'missing path'}), 400
    if not Path(path).exists():
        return jsonify({'ok': False, 'error': 'file not found', 'path': path}), 404
    proc = subprocess.run(['python', str(EXTRACT), path], capture_output=True, text=True)
    try:
        out = json.loads(proc.stdout)
    except Exception:
        return jsonify({'ok': False, 'error': 'extract failed', 'stdout': proc.stdout, 'stderr': proc.stderr}), 500
    return jsonify(out)

@app.route('/api/heatmap', methods=['POST'])
def api_heatmap():
    data = request.json or {}
    path = data.get('path')
    if not path:
        return jsonify({'ok': False, 'error': 'missing path'}), 400
    if not Path(path).exists():
        return jsonify({'ok': False, 'error': 'file not found', 'path': path}), 404
    proc = subprocess.run(['python', str(MAKEHM), path], capture_output=True, text=True)
    try:
        out = json.loads(proc.stdout)
    except Exception:
        return jsonify({'ok': False, 'error': 'heatmap generation failed', 'stdout': proc.stdout, 'stderr': proc.stderr}), 500
    return jsonify(out)

@app.route('/api/test', methods=['POST'])
def api_test():
    data = request.json or {}
    path = data.get('path')
    if not path:
        return jsonify({'ok': False, 'error': 'missing path'}), 400
    if not Path(path).exists():
        return jsonify({'ok': False, 'error': 'file not found', 'path': path}), 404
    proc = subprocess.run(['python', str(TESTER), path], capture_output=True, text=True)
    return jsonify({'ok': proc.returncode==0, 'returncode': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr})

@app.route('/visuals/<path:filename>')
def visuals(filename):
    return send_from_directory(str(VISUALS), filename)

if __name__ == '__main__':
    app.run(port=5005)
