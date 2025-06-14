#!/usr/bin/env python3
# server.py

import os
import re
import json
import tempfile
from flask import Flask, request, send_file, jsonify

# Импортируем функции из passport_to_excel_with_openai.py
from passport_to_excel import (
    ocr_parse_image,
    parse_mrz_manual,
    extract_cyrillic_name,
    extract_dates_and_places,
    extract_code_division,
    gpt_cleanup,
    export_to_excel
)

app = Flask(__name__)

@app.route('/process', methods=['POST'])
def process_passport():
    # Приходят form-data: file (image), filename (desired .xlsx name)
    img = request.files.get('file')
    out_name = request.form.get('filename', 'out.xlsx')
    if not img:
        return jsonify({'error': 'file is required'}), 400

    # Сохраним во временный файл
    tmp_img = tempfile.NamedTemporaryFile(suffix=os.path.splitext(img.filename)[1], delete=False)
    img.save(tmp_img.name)

    # 1) raw OCR
    raw = ocr_parse_image(tmp_img.name)
    lines = [l.strip() for l in raw.splitlines() if l.strip()]

    # 2) MRZ и поля
    mrz = parse_mrz_manual(lines)
    issue, birth, pi, pb = extract_dates_and_places(lines)
    fam, giv, pat = extract_cyrillic_name(raw, mrz)
    sex = 'Мужской' if re.search(r'\bМУЖ', raw, re.IGNORECASE) else 'Женский'

    combined = {
        'surname':       fam,
        'given_name':    giv,
        'patronymic':    pat,
        'sex':           sex,
        'date_of_issue': issue,
        'place_of_issue':pi,
        'series':        mrz['series'],
        'number':        mrz['number'],
        'date_of_birth': birth,
        'place_of_birth':pb,
        'division_code': extract_code_division(raw),
    }

    # 3) GPT-коррекция
    final = gpt_cleanup(raw, combined)

    # 4) Экспорт во временный Excel
    tmp_xlsx = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
    export_to_excel(final, tmp_xlsx.name)

    return send_file(tmp_xlsx.name,
                     as_attachment=True,
                     download_name=out_name,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
