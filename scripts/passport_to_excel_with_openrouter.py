#!/usr/bin/env python3
# scripts/passport_to_excel_with_openrouter.py

import sys
import os
import re
import json
import requests
import pandas as pd
from openai import OpenAI, RateLimitError, OpenAIError

# === Настройки OCR.space ===
API_KEY_OCR = 'K85845231888957'
OCR_URL    = 'https://api.ocr.space/parse/image'

# === Настройка клиента OpenRouter.ai ===
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="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",
)
MODEL = "meta-llama/llama-3.3-70b-instruct"

# === OCR.space извлечение текста ===
def ocr_parse_image(path: str) -> str:
    if not os.path.isfile(path):
        print(f'❌ Файл не найден: {path}', file=sys.stderr)
        sys.exit(1)
    with open(path, 'rb') as f:
        r = requests.post(
            OCR_URL,
            files={'file': f},
            data={'apikey': API_KEY_OCR, 'ocrEngine': '2', 'language': 'rus'}
        )
    r.raise_for_status()
    j = r.json()
    prs = j.get('ParsedResults')
    if not prs or not prs[0].get('ParsedText'):
        print('❌ OCR не вернул текст', file=sys.stderr)
        sys.exit(1)
    return prs[0]['ParsedText']

# === Парсеры и вспомогалки ===
def parse_mrz_manual(lines: list[str]) -> dict:
    mrz = [l for l in lines if '<<' in l]
    if len(mrz) < 2:
        print('❌ MRZ не найден', file=sys.stderr)
        sys.exit(1)
    l1, l2 = mrz[-2], mrz[-1]
    l1 = (l1 + '<'*44)[:44]
    l2 = (l2 + '<'*44)[:44]
    names = l1[5:44]
    fam_lat, rest = names.split('<<', 1)
    fam_lat = fam_lat.replace('<', ' ').strip()
    giv_lat = rest.replace('<', ' ').split('<')[0].strip()
    doc = l2[:9].replace('<', '')
    return {
        'fam_lat': fam_lat,
        'giv_lat': giv_lat,
        'series':   doc[:4],
        'number':   doc[4:],
    }

def extract_cyrillic_name(text: str, mrz: dict) -> tuple[str,str,str]:
    parts = re.split(r'\d{2}\.\d{2}\.\d{4}', text, maxsplit=1)
    prefix = parts[0] if len(parts) > 1 else text
    words = re.findall(r'\b[А-ЯЁ][а-яё]+\b', prefix)
    if len(words) >= 3:
        return words[0], words[1], words[2]
    fam = re.search(r'Фамилия[:\s]*([А-ЯЁ][а-яё]+)', text)
    giv = re.search(r'Имя[:\s]*([А-ЯЁ][а-яё]+)', text)
    pat = re.search(r'Отчество[:\s]*([А-ЯЁ][а-яё]+)', text)
    return (
        fam.group(1) if fam else mrz['fam_lat'],
        giv.group(1) if giv else mrz['giv_lat'],
        pat.group(1) if pat else ''
    )

def extract_dates_and_places(lines: list[str]) -> tuple[str,str,str,str]:
    text = "\n".join(lines)
    dates = re.findall(r'\d{2}\.\d{2}\.\d{4}', text)
    issue = dates[0] if dates else ''
    birth = dates[1] if len(dates) > 1 else ''
    m = re.search(r'Паспорт выдан\s*(.*?)\s*\d{2}\.\d{2}\.\d{4}', text, re.DOTALL)
    place_issue = re.sub(r'\s+', ' ', m.group(1)).strip() if m else ''
    place_birth = ''
    if birth in lines:
        i = lines.index(birth)
        cand = [l for l in lines[i+1:i+3] if re.search(r'[А-ЯЁа-яё]', l)]
        place_birth = " ".join(cand).strip()
    return issue, birth, place_issue, place_birth

def extract_code_division(text: str) -> str:
    m = re.search(r'Код подразделения[:\s]*([\d-]+)', text)
    return m.group(1) if m else ''

# === GPT-cleanup через OpenRouter ===
def gpt_cleanup(raw_text: str, combined: dict) -> dict:
    prompt = f"""
У тебя есть данные, извлечённые OCR+регулярками:
{combined}

И полный сырой текст паспорта:

Исправь неверные ФИО (surname, given_name, patronymic), подтверди или исправь пол,
даты (формат DD.MM.YYYY), места. Верни исключительно JSON с ключами:
surname, given_name, patronymic, sex, date_of_issue, place_of_issue,
series, number, date_of_birth, place_of_birth, division_code.
"""
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "Ты — эксперт по распознаванию российских паспортов."},
                {"role": "user",   "content": prompt}
            ]
        )
        content = resp.choices[0].message.content.strip()
        # Убираем возможные ```json ... ``` ограждения
        content_clean = re.sub(r"^```(?:json)?\s*|```$", "", content, flags=re.DOTALL).strip()
        try:
            return json.loads(content_clean)
        except json.JSONDecodeError:
            print("⚠️ GPT вернул не-JSON, возвращаем исходные данные.", file=sys.stderr)
            print("---- RAW GPT RESPONSE START ----", file=sys.stderr)
            print(content, file=sys.stderr)
            print("----  RAW GPT RESPONSE END  ----", file=sys.stderr)
            return combined
    except RateLimitError:
        print("⚠️ Квота OpenRouter.ai исчерпана, возвращаем исходные данные.", file=sys.stderr)
        return combined
    except OpenAIError as e:
        print("❌ Ошибка OpenRouter.ai:", e, file=sys.stderr)
        return combined

# === Экспорт в Excel ===
def export_to_excel(data: dict, out: str):
    df = pd.DataFrame([data])
    cols = [
        'surname','given_name','patronymic','sex',
        'date_of_issue','place_of_issue','series',
        'number','date_of_birth','place_of_birth','division_code'
    ]
    rus = {
        'surname':         'Фамилия',
        'given_name':      'Имя',
        'patronymic':      'Отчество',
        'sex':             'Пол',
        'date_of_issue':   'Дата выдачи',
        'place_of_issue':  'Место выдачи',
        'series':          'Серия',
        'number':          'Номер',
        'date_of_birth':   'Дата рождения',
        'place_of_birth':  'Место рождения',
        'division_code':   'Код подразделения',
    }
    df = df[cols].rename(columns=rus)
    df.to_excel(out, index=False)
    print(f'✅ Excel сохранён: {out}')

# === Main ===
def usage():
    print(f'Использование: {sys.argv[0]} <image> <output.xlsx>', file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        usage()

    img, out = sys.argv[1], sys.argv[2]
    raw               = ocr_parse_image(img)
    lines             = [l.strip() for l in raw.splitlines() if l.strip()]
    mrz               = parse_mrz_manual(lines)
    issue, birth, pi, pb = extract_dates_and_places(lines)
    fam, giv, pat     = extract_cyrillic_name(raw, mrz)
    sex               = 'Мужской' if re.search(r'\bМУЖ', raw, re.IGNORECASE) else 'Женский'

    combined = {
        'surname':         fam,
        'given_name':      giv,
        'patronymic':      pat,
        'sex':             sex,
        'date_of_issue':   issue,
        'place_of_issue':  pi,
        'series':          mrz['series'],
        'number':          mrz['number'],
        'date_of_birth':   birth,
        'place_of_birth':  pb,
        'division_code':   extract_code_division(raw),
    }

    final = gpt_cleanup(raw, combined)
    export_to_excel(final, out)
