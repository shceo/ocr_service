#!/usr/bin/env python3
# scripts/passport_to_excel_combined.py

import sys
import os
import re
import requests
import pandas as pd

API_KEY = 'K85845231888957'
OCR_URL = 'https://api.ocr.space/parse/image'

def ocr_parse_image(path: str) -> str:
    if not os.path.isfile(path):
        print(f'❌ Файл не найден: {path}', file=sys.stderr)
        sys.exit(1)
    with open(path, 'rb') as f:
        r = requests.post(
            OCR_URL,
            files={'file': f},
            data={'apikey': API_KEY, 'language': 'rus+eng', 'ocrEngine': '2'},
            timeout=60
        )
    r.raise_for_status()
    parsed = r.json().get('ParsedResults')
    txt = parsed[0].get('ParsedText','') if parsed else ''
    if not txt.strip():
        print('❌ OCR не вернул текст', file=sys.stderr)
        sys.exit(1)
    return txt

def parse_mrz_manual(lines: list[str]) -> dict:
    mrz = [l.replace(' ','') for l in lines if '<<' in l]
    if len(mrz) < 2:
        print('❌ MRZ не найден', file=sys.stderr); sys.exit(1)
    l1, l2 = mrz[-2], mrz[-1]
    l1 = (l1 + '<'*44)[:44]
    l2 = (l2 + '<'*44)[:44]
    names = l1[5:44]
    fam_lat, rest = names.split('<<',1)
    fam_lat = fam_lat.replace('<',' ').strip()
    giv_lat = rest.replace('<',' ').strip().split(' ')[0] if rest else ''
    doc = l2[:9].replace('<','')
    return {'fam_lat': fam_lat, 'giv_lat': giv_lat, 'series': doc[:4], 'number': doc[4:]}

def extract_dates_and_places(lines: list[str]) -> tuple[str,str,str,str]:
    dates = [(i,l) for i,l in enumerate(lines) if re.match(r'^\d{2}\.\d{2}\.\d{4}$', l)]
    issue = dates[0][1] if dates else ''
    birth_idx, birth = (dates[1][0], dates[1][1]) if len(dates)>1 else (None, '')
    full = '\n'.join(lines)
    m = re.search(r'Паспорт выдан\s*(.*?)\s*\d{2}\.\d{2}\.\d{4}', full, re.DOTALL)
    place_issue = re.sub(r'\s+',' ', m.group(1)).strip() if m else ''
    place_birth = ''
    if birth_idx is not None:
        cand = []
        for o in (1,2):
            idx = birth_idx + o
            if idx < len(lines) and re.search(r'[А-ЯЁа-яё]', lines[idx]):
                cand.append(lines[idx])
        place_birth = ' '.join(cand).strip()
    return issue, birth, place_issue, place_birth

def extract_code_division(text: str) -> str:
    m = re.search(r'Код подразделения[:\s]*([\d-]+)', text)
    return m.group(1).strip() if m else ''

def extract_cyrillic_name(lines: list[str], raw: str, mrz: dict) -> tuple[str,str,str]:
    # По трём строкам над датой рождения
    fam=giv=pat=''
    idxs = [i for i,l in enumerate(lines) if re.match(r'^\d{2}\.\d{2}\.\d{4}$', l)]
    if idxs:
        idx = idxs[1] if len(idxs)>1 else idxs[0]
        if idx>=3:
            block = lines[idx-3:idx]
            if re.search(r'[А-ЯЁа-яё]', block[0]) and re.search(r'[А-ЯЁа-яё]', block[1]):
                fam, giv = block[0], block[1]
                if re.search(r'[А-ЯЁа-яё]', block[2]):
                    pat = block[2]
    # fallback: метки
    if not fam:
        m = re.search(r'Фамилия[:\s]*([А-ЯЁ][а-яё]+)', raw); 
        fam = m.group(1).strip() if m else mrz['fam_lat']
    if not giv:
        m = re.search(r'Имя[:\s]*([А-ЯЁ][а-яё]+)', raw);
        giv = m.group(1).strip() if m else mrz['giv_lat']
    if not pat:
        m = re.search(r'\b[А-ЯЁ][а-яё]+ич\b', raw)
        pat = m.group(0) if m else ''
    return fam, giv, pat

def extract_all(text: str, lines: list[str], mrz: dict) -> dict:
    # ФИО
    fam, giv, pat = extract_cyrillic_name(lines, text, mrz)
    # Пол
    sex = 'Мужской' if re.search(r'\bМУЖ', text, re.IGNORECASE) else 'Женский'
    m = re.search(r'Пол[:\s]*([^\r\n]+)', text, re.IGNORECASE)
    if m: sex = m.group(1).strip()
    # Даты и места
    issue, birth, place_issue, place_birth = extract_dates_and_places(lines)
    m = re.search(r'Дата выдачи[:\s]*([^\r\n]+)', text, re.IGNORECASE)
    did = m.group(1).strip() if m else issue
    m = re.search(r'Дата рождения[:\s]*([^\r\n]+)', text, re.IGNORECASE)
    dob = m.group(1).strip() if m else birth
    m = re.search(r'Место выдачи[:\s]*([^\r\n]+)', text, re.IGNORECASE)
    pi = m.group(1).strip() if m else place_issue
    m = re.search(r'Место рождения[:\s]*([^\r\n]+)', text, re.IGNORECASE)
    pb = m.group(1).strip() if m else place_birth
    code = extract_code_division(text)
    return {
        'Фамилия': fam,
        'Имя': giv,
        'Отчество': pat,
        'Пол': sex,
        'Дата выдачи': did,
        'Место выдачи': pi,
        'Серия': mrz['series'],
        'Номер документа': mrz['number'],
        'Дата рождения': dob,
        'Место рождения': pb,
        'Код подразделения': code,
    }

def export_to_excel(data: dict, out: str):
    df = pd.DataFrame([data])
    cols = [
        'Фамилия','Имя','Отчество','Пол',
        'Дата выдачи','Место выдачи','Серия','Номер документа',
        'Дата рождения','Место рождения','Код подразделения'
    ]
    df[cols].to_excel(out, index=False)
    print(f'✅ Excel сохранён: {out}')

def usage():
    print(f'Использование: {sys.argv[0]} <image> <output.xlsx>', file=sys.stderr)
    sys.exit(1)

if __name__=='__main__':
    if len(sys.argv)!=3: usage()
    img, out = sys.argv[1], sys.argv[2]
    txt = ocr_parse_image(img)
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    mrz  = parse_mrz_manual(lines)
    data = extract_all(txt, lines, mrz)
    for k,v in data.items():
        print(f'{k}: "{v}"')
    export_to_excel(data, out)
