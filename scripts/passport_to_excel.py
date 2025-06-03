#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import re
import json
import requests
import pandas as pd
import logging

# Используем новый клиент openai>=1.0.0
from openai import OpenAI, OpenAIError, RateLimitError

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

API_KEY_OCR = 'K85845231888957'
OCR_URL = 'https://api.ocr.space/parse/image'
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
MODEL = "gpt-4"

# Инициализируем клиента OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

def ocr_parse_image(path: str) -> str:
    """
    Возвращает полный распознанный текст из изображения через OCR.space.
    """
    logger.info(f"ocr_parse_image: проверяем существование файла '{path}'")
    if not os.path.isfile(path):
        logger.error(f"ocr_parse_image: файл не найден: {path}")
        print(f'❌ Файл не найден: {path}', file=sys.stderr)
        sys.exit(1)

    logger.info(f"ocr_parse_image: отправляем запрос в OCR.space для файла '{path}'")
    with open(path, 'rb') as f:
        r = requests.post(
            OCR_URL,
            files={'file': f},
            data={'apikey': API_KEY_OCR, 'ocrEngine': '2', 'language': 'rus'}
        )
    try:
        r.raise_for_status()
    except Exception as e:
        logger.error(f"ocr_parse_image: HTTP ошибка при OCR: {e}")
        raise

    j = r.json()
    prs = j.get('ParsedResults')
    if not prs or not prs[0].get('ParsedText'):
        logger.error("ocr_parse_image: OCR не вернул текст")
        print('❌ OCR не вернул текст', file=sys.stderr)
        sys.exit(1)

    raw_text = prs[0]['ParsedText']
    logger.debug(f"ocr_parse_image: получен сырой текст (первые 200 символов): {raw_text[:200]!r}")
    return raw_text

def parse_mrz_manual(lines: list[str]) -> dict:
    """
    Ищет MRZ (две строки с '<<') и извлекает серию/номер, фамилию, имя латиницей.
    """
    logger.info("parse_mrz_manual: ищем MRZ-строки...")
    mrz = [l for l in lines if '<<' in l]
    if len(mrz) < 2:
        logger.error("parse_mrz_manual: MRZ не найден")
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
    series = doc[:4]
    number = doc[4:]
    logger.debug(f"parse_mrz_manual: fam_lat={fam_lat}, giv_lat={giv_lat}, series={series}, number={number}")
    return {'fam_lat': fam_lat, 'giv_lat': giv_lat, 'series': series, 'number': number}

def extract_cyrillic_name(text: str, mrz: dict) -> tuple[str, str, str]:
    """
    Ищет кириллическое ФИО в тексте. Если не находится, возвращает данные из MRZ (латиница).
    """
    logger.info("extract_cyrillic_name: пытаемся найти ФИО кириллицей...")
    parts = re.split(r'\d{2}\.\d{2}\.\d{4}', text, maxsplit=1)
    prefix = parts[0] if len(parts) > 1 else text

    words = re.findall(r'\b[А-ЯЁ][а-яё]+\b', prefix)
    if len(words) >= 3:
        logger.debug(f"extract_cyrillic_name: найдено >=3 слов: {words[:3]}")
        return words[0], words[1], words[2]

    fam = re.search(r'Фамилия[:\s]*([А-ЯЁ][а-яё]+)', text)
    giv = re.search(r'Имя[:\s]*([А-ЯЁ][а-яё]+)', text)
    pat = re.search(r'Отчество[:\s]*([А-ЯЁ][а-яё]+)', text)

    fam_c = fam.group(1) if fam else mrz['fam_lat']
    giv_c = giv.group(1) if giv else mrz['giv_lat']
    pat_c = pat.group(1) if pat else ''
    logger.debug(f"extract_cyrillic_name: fam={fam_c}, giv={giv_c}, pat={pat_c}")
    return fam_c, giv_c, pat_c

def fix_date_format(date_str: str) -> str:
    """
    Приводит дату к формату DD.MM.YYYY, либо возвращает пустую строку, если не подходит.
    """
    if not date_str:
        return ''
    parts = date_str.split('.')
    if len(parts) != 3:
        return ''
    day, month, year = parts
    try:
        d = int(day)
        m = int(month)
        y = int(year)
        return f"{d:02d}.{m:02d}.{y:04d}"
    except ValueError:
        return ''

def extract_dates_and_places(lines: list[str]) -> tuple[str, str, str, str]:
    """
    Извлекает дату выдачи, дату рождения, место выдачи и место рождения.
    """
    logger.info("extract_dates_and_places: анализируем даты и места...")
    text = "\n".join(lines)
    dates = re.findall(r'\d{1,2}\.\d{1,2}\.\d{4}', text)
    issue_raw = dates[0] if dates else ''
    birth_raw = dates[1] if len(dates) > 1 else ''

    issue = fix_date_format(issue_raw)
    birth = fix_date_format(birth_raw)

    m = re.search(r'Паспорт выдан\s*(.*?)\s*\d{1,2}\.\d{1,2}\.\d{4}', text, re.DOTALL)
    place_issue = re.sub(r'\s+', ' ', m.group(1)).strip() if m else ''
    place_birth = ''
    if birth_raw and birth_raw in lines:
        i = lines.index(birth_raw)
        cand = [l for l in lines[i+1:i+3] if re.search(r'[А-ЯЁа-яё]', l)]
        place_birth = " ".join(cand).strip()

    logger.debug(f"extract_dates_and_places: issue={issue}, birth={birth}, place_issue={place_issue}, place_birth={place_birth}")
    return issue, birth, place_issue, place_birth

def extract_code_division(text: str) -> str:
    """
    Ищет 'Код подразделения: ХХХ-ХХХ' и возвращает найденное, иначе пустую строку.
    """
    m = re.search(r'Код подразделения[:\s]*([\d-]+)', text)
    code = m.group(1) if m else ''
    logger.debug(f"extract_code_division: division_code={code}")
    return code

def gpt_cleanup(raw_text: str, combined: dict) -> dict:
    """
    Вызывает GPT-4 для 'чистки' и корректировки ФИО и остальных полей.
    Логирует входные и выходные данные.
    """
    logger.info("gpt_cleanup: формируем prompt для GPT...")
    prompt = f"""У тебя есть данные, извлечённые OCR+регулярками:
{json.dumps(combined, ensure_ascii=False, indent=2)}

И полный сырой текст паспорта:
{raw_text}
Ты — эксперт по распознаванию и “чистке” российских ФИО из OCR-вывода. Твоя задача — максимально точно восстановить фамилию, имя и отчество, даже если в исходном тексте есть цифры вместо букв, опечатки, пропуски или артефакты. При этом ключевые правила:

1) Проверка и исправление ФИО (суффиксы surname, given_name, patronymic):
   - Если часть ФИО содержит цифры (например, “ART2M” или “IGOREVI3”), автоматически замени цифры на наиболее вероятные буквы (например, “2” → “Е” или “Т”, “3” → “З” или “Ч”) и приведите всё к корректному русскому написанию.
   - Если после замены остаются сомнения, выбери наиболее правдоподобный вариант на русском языке.  
     Например:  
     - “ART2M” → “АРТЕМ”  
     - “IGOREVI3” → “ИГОРЕВИЧ”  
   - Если в каком-то слове нельзя однозначно восстановить буквы, предложи вариант с пометкой «(предположительно)», но не оставляй цифры.  
   - Если полностью потерялась фамилия, имя или отчество и восстановить по контексту не получается, верни значение "Не удалось распознать" в соответствующем ключе.

2) Проверка пола (sex):
   - Сначала ищи явные указания “МУЖ” или “ЖЕН” в тексте.  
   - Если их нет, определяй пол по окончанию отчества:  
     - Окончание “–овна” или “–евна” → “Женский”  
     - Окончание “–ович” или “–евич” → “Мужской”  
   - Если отчество отсутствует или неявное, укажи “Не удалось распознать”, если уверенности нет.

3) Проверка и форматирование дат (DD.MM.YYYY):
   - Выявляй все даты в формате D.M.YYYY или DD.MM.YYYY и приводь их к формату с двумя цифрами для дня и месяца (например, “2.1.1990” → “02.01.1990”).  
   - Если OCR склеил числа (например, “02121990”), попробуй разделить по логике (если не получается — оставь пустую строку).

4) Проверка и восстановление мест (place_of_issue, place_of_birth):
   - Если строка с местом выдачи усечена или содержит лишние пробелы/переносы, восстанавливай по привычным фразам: “Выдано ____” / “г. ____” / “МОУ ____”.  
   - Если не можешь восстановить полный текст, оставь пустую строку.

5) Остальные поля:
   - series и number берем из MRZ или OCR-вывода без изменений, только удаляем лишние пробелы.
   - division_code ищем по шаблону “Код подразделения: ХХХ-ХХХ” и сохраняем в том же формате.

В результате верни строго JSON со следующими ключами (никакого дополнительного текста, только JSON):
{{
"surname": "...",
"given_name": "...",
"patronymic": "...",
"sex": "...",
"date_of_issue": "...",
"place_of_issue": "...",
"series": "...",
"number": "...",
"date_of_birth": "...",
"place_of_birth": "...",
"division_code": "..."
}}

Пример корректного вывода (НЕ повторяй этот пример в ответе, просто верни JSON):
```json
{{
  "surname": "Иванов",
  "given_name": "Пётр",
  "patronymic": "Александрович",
  "sex": "Мужской",
  "date_of_issue": "12.05.2010",
  "place_of_issue": "ОВД г. Москвы",
  "series": "4510",
  "number": "123456",
  "date_of_birth": "15.03.1985",
  "place_of_birth": "г. Санкт-Петербург",
  "division_code": "770-001"
}}
```"""
    try:
        logger.debug(f"gpt_cleanup: отправляем запрос в OpenAI. combined={combined}")
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "Ты — эксперт по распознаванию российских паспортов. Всегда исправляй и дополняй некорректные данные."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        )
        content = response.choices[0].message.content.strip()
        logger.debug(f"gpt_cleanup: получен сырой ответ GPT (первые 200 символов): {content[:200]!r}")
        content_clean = re.sub(r"^```(?:json)?\s*|```$", "", content, flags=re.DOTALL).strip()

        try:
            result = json.loads(content_clean)
            logger.info("gpt_cleanup: успешно распарсили JSON от GPT.")
            return result
        except json.JSONDecodeError:
            logger.error("gpt_cleanup: JSONDecodeError, возвращаем исходный combined.")
            logger.debug(f"gpt_cleanup: RAW GPT RESPONSE:\n{content}")
            return combined

    except RateLimitError:
        logger.error("gpt_cleanup: RateLimitError — квота исчерпана, возвращаем исходный combined.")
        return combined
    except OpenAIError as e:
        logger.error(f"gpt_cleanup: OpenAIError: {e}")
        return combined

def export_to_excel(data: dict, out: str):
    """
    Сохраняет результат в Excel и логирует записанные данные.
    """
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
    logger.info(f"export_to_excel: финальные данные для записи: {df.to_dict(orient='records')}")
    df.to_excel(out, index=False)
    logger.info(f"export_to_excel: ✅ Excel сохранён: {out}")
    print(f'✅ Excel сохранён: {out}')

def usage():
    print(f'Использование: {sys.argv[0]} <image> <output.xlsx>', file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        usage()

    img, out = sys.argv[1], sys.argv[2]
    logger.info("=== Начало обработки изображения паспорта ===")

    # OCR
    raw = ocr_parse_image(img)
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    logger.debug(f"main: всего строк OCR: {len(lines)}")

    # MRZ
    mrz = parse_mrz_manual(lines)

    # Даты и места
    issue, birth, pi, pb = extract_dates_and_places(lines)

    # ФИО кириллицей
    fam, giv, pat = extract_cyrillic_name(raw, mrz)

    # Пол
    sex = 'Мужской' if re.search(r'\bМУЖ', raw, re.IGNORECASE) else 'Женский'

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
    logger.info(f"main: собранный словарь combined: {combined}")

    # GPT-cleanup
    final = gpt_cleanup(raw, combined)
    logger.info(f"main: словарь после gpt_cleanup: {final}")

    # Сохраняем в Excel
    export_to_excel(final, out)
    logger.info("=== Обработка завершена ===")
