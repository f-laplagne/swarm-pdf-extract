#!/bin/bash
set -e

MODE="${1:-serve}"

case "$MODE" in
    serve)
        echo "Starting PP-StructureV3 API server on port 8080..."
        python -c "
import json
import base64
import tempfile
import os
from flask import Flask, request, jsonify
from paddleocr import PPStructureV3

app = Flask(__name__)
pipeline = PPStructureV3()

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'model': 'PP-StructureV3'})

@app.route('/predict', methods=['POST'])
def predict():
    data = request.get_json()
    if 'file_base64' in data:
        file_bytes = base64.b64decode(data['file_base64'])
        suffix = data.get('suffix', '.pdf')
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(file_bytes)
            tmp_path = f.name
        try:
            output = pipeline.predict(input=tmp_path)
            results = []
            for res in output:
                for item in res:
                    results.append(str(item))
            return jsonify({'status': 'ok', 'results': results})
        finally:
            os.unlink(tmp_path)
    elif 'file_path' in data:
        output = pipeline.predict(input=data['file_path'])
        results = []
        for res in output:
            for item in res:
                results.append(str(item))
        return jsonify({'status': 'ok', 'results': results})
    else:
        return jsonify({'status': 'error', 'message': 'No file_base64 or file_path provided'}), 400

app.run(host='0.0.0.0', port=8080)
"
        ;;
    process)
        INPUT_FILE="${2}"
        if [ -z "$INPUT_FILE" ]; then
            echo "Usage: entrypoint.sh process <file.pdf>"
            exit 1
        fi
        echo "Processing $INPUT_FILE with PP-StructureV3..."
        python -c "
import json
import sys
from paddleocr import PPStructureV3
pipeline = PPStructureV3()
output = pipeline.predict(input='${INPUT_FILE}')
results = []
for res in output:
    for item in res:
        results.append(str(item))
print(json.dumps({'status': 'ok', 'results': results}, ensure_ascii=False, indent=2))
"
        ;;
    *)
        echo "Unknown mode: $MODE"
        echo "Usage: entrypoint.sh [serve|process <file>]"
        exit 1
        ;;
esac
