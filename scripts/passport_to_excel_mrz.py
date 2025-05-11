# #!/usr/bin/env python3
# # scripts/passport_to_excel_mrz.py

# import sys
# import os
# import shutil

# import pandas as pd
# import pytesseract
# from passporteye import read_mrz

# # Попытаемся найти tesseract в PATH
# _tess_path = shutil.which('tesseract')
# if not _tess_path:
#     print("❌ tesseract не найден в PATH. Установите Tesseract-OCR и добавьте в PATH.", file=sys.stderr)
#     sys.exit(1)
# pytesseract.pytesseract.tesseract_cmd = _tess_path

# def format_date(yyMMdd: str) -> str:
#     if len(yyMMdd) != 6 or not yyMMdd.isdigit():
#         return ''
#     yy, mm, dd = yyMMdd[:2], yyMMdd[2:4], yyMMdd[4:]
#     year = int(yy)
#     century = 1900 if year >= 50 else 2000
#     return f"{dd}.{mm}.{century + year}"

# def parse_mrz(img_path: str) -> dict:
#     if not os.path.isfile(img_path):
#         print(f"❌ Файл не найден: {img_path}", file=sys.stderr)
#         sys.exit(1)

#     mrz = read_mrz(img_path, save_roi=True)
#     if mrz is None:
#         print("❌ MRZ не обнаружен на фото.", file=sys.stderr)
#         sys.exit(1)

#     return mrz.to_dict()

# def export_to_excel(data: dict, out_path: str):
#     row = {
#         'Фамилия':                  data.get('surname', ''),
#         'Имя':                      data.get('given_names', '').split()[0] if data.get('given_names') else '',
#         'Отчество':                 ' '.join(data.get('given_names', '').split()[1:]) if data.get('given_names') else '',
#         'Серия':                    data.get('number', '')[:4],
#         'Номер':                    data.get('number', '')[4:],
#         'Пол':                      data.get('sex', ''),
#         'Дата рождения':            format_date(data.get('date_of_birth', '')),
#         'Дата выдачи':              '',  # MRZ не содержит
#         'Срок действия':            format_date(data.get('expiration_date', '')),
#         'Национальность':           data.get('nationality', ''),
#         'Номер документа (полный)': data.get('number', ''),
#     }
#     df = pd.DataFrame([row])
#     cols = [
#         'Фамилия','Имя','Отчество','Пол','Дата рождения',
#         'Серия','Номер','Номер документа (полный)',
#         'Дата выдачи','Срок действия','Национальность'
#     ]
#     df = df[cols]
#     df.to_excel(out_path, index=False)
#     print(f"✅ Excel сохранён: {out_path}")

# def usage():
#     print(f"Использование: {sys.argv[0]} <путь_к_изображению> <выходной_xlsx>", file=sys.stderr)
#     sys.exit(1)

# if __name__ == "__main__":
#     if len(sys.argv) != 3:
#         usage()
#     img_path, out_xlsx = sys.argv[1], sys.argv[2]
#     mrz_data = parse_mrz(img_path)
#     export_to_excel(mrz_data, out_xlsx)






























####################################################



#!/usr/bin/env python3
# scripts/passport_to_excel_mrz_manual.py

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
            data={
                'apikey': API_KEY,
                'ocrEngine': '2',
                'language': 'rus'     # русский для точного чтения кириллицы
            }
        )
    r.raise_for_status()
    j = r.json()
    prs = j.get('ParsedResults')
    if not prs or not prs[0].get('ParsedText'):
        print('❌ OCR не вернул текст', file=sys.stderr)
        sys.exit(1)
    return prs[0]['ParsedText']

def fmt_date(yyMMdd: str) -> str:
    if not re.match(r'^\d{6}$', yyMMdd):
        return ''
    yy, mm, dd = yyMMdd[:2], yyMMdd[2:4], yyMMdd[4:6]
    year = int(yy)
    century = 1900 if year >= 50 else 2000
    return f'{dd}.{mm}.{century + year}'

def parse_mrz_manual(lines: list) -> dict:
    # ищем две MRZ-строки
    mrz = [l for l in lines if '<<' in l]
    if len(mrz) < 2:
        print('❌ MRZ не найден', file=sys.stderr)
        sys.exit(1)
    l1, l2 = mrz[-2], mrz[-1]
    l1 = (l1 + '<'*44)[:44]
    l2 = (l2 + '<'*44)[:44]

    # латиница: фамилия и имя
    names = l1[5:44]
    fam_lat, rest = names.split('<<', 1)
    fam_lat = fam_lat.replace('<',' ').strip()
    giv_lat = rest.replace('<',' ').strip().split(' ')[0] if rest else ''

    # серия и номер
    doc = l2[0:9].replace('<','')
    series = doc[:4]
    number = doc[4:]

    return {
        'fam_lat': fam_lat,
        'giv_lat': giv_lat,
        'series': series,
        'number': number,
    }

def extract_cyrillic_name(text: str, mrz_data: dict) -> tuple[str,str,str]:
    """
    Сначала пытаемся найти три подряд идущие кириллические слова (ФИО)
    до строки с датой рождения. Если не получается — ищем метки,
    и только потом — MRZ-латиницу.
    """
    # 1) Извлекаем текст до даты рождения
    parts = re.split(r'\d{2}\.\d{2}\.\d{4}', text, maxsplit=1)
    prefix = parts[0] if len(parts) > 1 else text

    # 2) Собираем все вхождения кириллицы подряд (слова)
    words = re.findall(r'\b[А-ЯЁ][а-яё]+\b', prefix)

    if len(words) >= 3:
        # первые три слова и будут ФИО
        return words[0], words[1], words[2]

    # 3) fallback по меткам
    fam = ''
    giv = ''
    pat = ''
    m = re.search(r'Фамилия[:\s]*([А-ЯЁ][а-яё]+)', text)
    if m: fam = m.group(1).strip()
    m = re.search(r'Имя[:\s]*([А-ЯЁ][а-яё]+)', text)
    if m: giv = m.group(1).strip()
    m = re.search(r'Отчество[:\s]*([А-ЯЁ][а-яё]+)', text)
    if m: pat = m.group(1).strip()

    # 4) если всё ещё нет — MRZ
    if not fam: fam = mrz_data['fam_lat']
    if not giv: giv = mrz_data['giv_lat']

    return fam, giv, pat

def extract_dates_and_places(lines: list):
    # находим все даты dd.MM.yyyy
    dates = []
    for idx, l in enumerate(lines):
        if re.match(r'^\d{2}\.\d{2}\.\d{4}$', l):
            dates.append((idx, l))
    issue_date = dates[0][1] if len(dates) > 0 else ''
    birth_idx, birth_date = (dates[1][0], dates[1][1]) if len(dates) > 1 else (None, '')
    # место выдачи — всё между "Паспорт выдан" и первой датой
    text = '\n'.join(lines)
    m = re.search(r'Паспорт выдан\s*(.*?)\s*\d{2}\.\d{2}\.\d{4}', text, re.DOTALL)
    place_issue = re.sub(r'\s+', ' ', m.group(1)).strip() if m else ''
    # место рождения — две строки сразу после birth_idx
    place_birth = ''
    if birth_idx is not None and birth_idx+1 < len(lines):
        part = [lines[birth_idx+1]]
        if birth_idx+2 < len(lines):
            part.append(lines[birth_idx+2])
        # оставляем только кириллические
        part = [p for p in part if re.search(r'[А-ЯЁа-яё]', p)]
        place_birth = ' '.join(part).strip()
    return issue_date, birth_date, place_issue, place_birth

def extract_code_division(text: str) -> str:
    m = re.search(r'Код подразделения[:\s]*([\d-]+)', text)
    return m.group(1).strip() if m else ''

def export_to_excel(data: dict, out: str):
    df = pd.DataFrame([data])
    cols = [
        'Фамилия',
        'Имя',
        'Отчество',
        'Пол',
        'Дата выдачи',
        'Место выдачи',
        'Серия',
        'Дата рождения',
        'Место рождения',
        'Код подразделения',
    ]
    df = df[cols]
    df.to_excel(out, index=False)
    print(f'✅ Excel сохранён: {out}')

def usage():
    print(f'Использование: {sys.argv[0]} <путь_к_изображению> <выходной_xlsx>', file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        usage()
    img_path, out_xlsx = sys.argv[1], sys.argv[2]

    raw_text = ocr_parse_image(img_path)
    # готовим список строк
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]

    # парсим MRZ для серии/номера и латиницы
    mrz = parse_mrz_manual(lines)

    # даты и места
    issue_date, birth_date, place_issue, place_birth = extract_dates_and_places(lines)

    # код подразделения
    code_div = extract_code_division(raw_text)

    # ФИО кириллицей
    fam, giv, pat = extract_cyrillic_name(raw_text, mrz)

    combined = {
        'Фамилия':           fam,
        'Имя':               giv,
        'Отчество':          pat,
        'Пол':               'Мужской' if re.search(r'\bМУЖ', raw_text, re.IGNORECASE) else 'Женский',
        'Дата выдачи':       issue_date,
        'Место выдачи':      place_issue,
        'Серия':             mrz['series'],
        'Дата рождения':     birth_date,
        'Место рождения':    place_birth,
        'Код подразделения': code_div,
    }

    for k, v in combined.items():
        print(f'{k}: "{v}"')

    export_to_excel(combined, out_xlsx)
