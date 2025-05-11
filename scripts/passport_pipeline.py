#!/usr/bin/env python3
import sys
import os
import re
import logging
import cv2
import pandas as pd

# -------------- LOGGING SETUP --------------
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO
)

# -------------- TESSERACT SETUP --------------
# Указываем, где искать языковые данные (.traineddata):
os.environ['TESSDATA_PREFIX'] = r"C:\Program Files\Tesseract-OCR"
import pytesseract
# Явно прописываем путь до tesseract.exe:
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# -------------- IMPORT OCR LIBRARIES --------------
from fastmrz import FastMRZ    # pip install fastmrz
import easyocr                 # pip install easyocr

# Один экземпляр FastMRZ и EasyOCR-ридера
mrz_reader = FastMRZ()
reader     = easyocr.Reader(['ru','en'], gpu=False)


def detect_mrz(path: str) -> dict:
    logging.info(f"Попытка FastMRZ.get_details для {path!r}")
    try:
        details = mrz_reader.get_details(path, include_checkdigit=False)
        logging.info(f"FastMRZ вернул: {details}")
        if details and 'surname' in details:
            return details
    except Exception as e:
        logging.warning(f"FastMRZ упал: {e}")

    logging.info("Fallback: ищем любые строки с '<' через EasyOCR")
    img = cv2.imread(path)
    ocr_lines = reader.readtext(img, detail=0)
    logging.info(f"EasyOCR вернул {len(ocr_lines)} строк")

    # 1) отбираем строки с '<'
    raw = [l for l in ocr_lines if '<' in l]
    # 2) чистим до допустимых символов
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<")
    mrz_cand = []
    for l in raw:
        up = l.upper()
        clean = "".join(ch for ch in up if ch in allowed)
        if len(clean) >= 30:
            mrz_cand.append(clean)
    logging.info(f"MRZ-кандидаты после фильтра: {mrz_cand}")

    # Если получилось сразу две строки — парсим их
    if len(mrz_cand) >= 2:
        l1, l2 = mrz_cand[-2], mrz_cand[-1]
    # Если только одна очень длинная (OCR склеил), разбиваем её
    elif len(mrz_cand) == 1 and len(mrz_cand[0]) >= 80:
        full = mrz_cand[0]
        l1, l2 = full[:44], full[44:88]
        logging.info("Разбили одну длинную MRZ-строку на две")
    else:
        raise RuntimeError("MRZ не найден ни FastMRZ, ни в строках с '<'")

    # Нормируем до ровно 44 символов
    l1 = (l1 + "<"*44)[:44]
    l2 = (l2 + "<"*44)[:44]
    logging.info(f"Используем строки MRZ:\n  {l1}\n  {l2}")

    # Распознаём фамилию, имя, номер
    fam_lat, rest = l1[5:44].split("<<", 1)
    fam_lat = fam_lat.replace("<"," ").strip()
    giv_lat = rest.replace("<"," ").split("<")[0].strip()
    doc     = l2[:9].replace("<","")

    # Пол из MRZ (символ на позиции 20 второй строки)
    sex_char = l2[20] if len(l2)>20 else None
    mrz_sex  = "M" if sex_char=="M" else ("F" if sex_char=="F" else None)

    fallback = {
        "surname":         fam_lat,
        "given_name":      giv_lat,
        "document_number": doc,
        "sex":             mrz_sex
    }
    logging.info(f"Fallback MRZ parsed: {fallback}")
    return fallback

    raise RuntimeError("MRZ не найден ни FastMRZ, ни в строках с '<'")


def ocr_all(path: str) -> list[str]:
    """Считываем весь паспорт EasyOCR-ом и возвращаем список строк."""
    img   = cv2.imread(path)
    lines = reader.readtext(img, detail=0)
    logging.info(f"Полный OCR (строк: {len(lines)})")
    return lines


def parse_name(lines: list[str], mrz: dict) -> tuple[str,str,str]:
    """
    1) Ищем метки Фамилия/Имя/Отчество.
    2) Если нет — три подряд кириллических слова ≥3 букв.
    3) Если и этого нет — fallback на MRZ.
    """
    text = "\n".join(lines)
    logging.info("Парсим ФИО по меткам")
    m_fam = re.search(r'Фамилия[:\s]*([А-ЯЁ][а-яё]+)', text)
    m_giv = re.search(r'Имя[:\s]*([А-ЯЁ][а-яё]+)', text)
    m_pat = re.search(r'Отчество[:\s]*([А-ЯЁ][а-яё]+)', text)
    if m_fam and m_giv:
        res = (m_fam.group(1), m_giv.group(1), m_pat.group(1) if m_pat else "")
        logging.info(f"Нашли по меткам: {res}")
        return res

    logging.info("Ищем три подряд кириллических слова ≥3 букв")
    words = re.findall(r'\b[А-ЯЁ][а-яё]{2,}\b', text)
    logging.info(f"Кириллические слова: {words}")
    if len(words) >= 3:
        res = (words[0], words[1], words[2])
        logging.info(f"Нашли подряд: {res}")
        return res

    logging.info("Fallback на MRZ-латиницу")
    surname = mrz.get("surname","")
    given   = mrz.get("given_name","").split()[0] if mrz.get("given_name") else ""
    res = (surname, given, "")
    logging.info(f"MRZ fallback ФИО: {res}")
    return res


def parse_dates_places(lines: list[str]) -> tuple[str,str,str,str]:
    """Извлекаем дату выдачи, дату рождения, место выдачи, место рождения."""
    text = "\n".join(lines)
    dates = re.findall(r'\d{2}\.\d{2}\.\d{4}', text)
    did   = dates[0] if dates else ""
    dob   = dates[1] if len(dates) > 1 else ""
    m1    = re.search(r'Паспорт выдан\s*(.*?)\s*\d{2}\.\d{2}\.\d{4}', text, re.DOTALL)
    pi    = re.sub(r'\s+'," ", m1.group(1)).strip() if m1 else ""
    pb    = ""
    if dob in lines:
        idx  = lines.index(dob)
        cand = [l for l in lines[idx+1:idx+3] if re.search(r'[А-ЯЁа-яё]', l)]
        pb  = " ".join(cand).strip()
    logging.info(f"Даты/места: выдача={did}, рожд={dob}, выдано='{pi}', рождено='{pb}'")
    return did, dob, pi, pb


def parse_sex(text: str, mrz: dict) -> str:
    """1) MRZ-пол, 2) метка 'Пол:', 3) fallback по слову 'МУЖ'."""
    if mrz.get("sex") == "M":
        logging.info("Пол из MRZ: Мужской")
        return "Мужской"
    if mrz.get("sex") == "F":
        logging.info("Пол из MRZ: Женский")
        return "Женский"
    m = re.search(r'Пол[:\s]*([^\r\n]+)', text, re.IGNORECASE)
    if m:
        sex = m.group(1).strip()
        logging.info(f"Пол по метке: {sex}")
        return sex
    sex = "Мужской" if "МУЖ" in text.upper() else "Женский"
    logging.info(f"Пол fallback: {sex}")
    return sex


def parse_code(text: str) -> str:
    """Извлечение кода подразделения."""
    m = re.search(r'Код подразделения[:\s]*([\d-]+)', text)
    code = m.group(1).strip() if m else ""
    logging.info(f"Код подразделения: {code}")
    return code


def main(img_path: str, out_xlsx: str):
    logging.info(f"=== START {img_path!r} ===")
    mrz   = detect_mrz(img_path)
    lines = ocr_all(img_path)
    text  = "\n".join(lines)

    fam, giv, pat = parse_name(lines, mrz)
    did, dob, pi, pb = parse_dates_places(lines)
    sex  = parse_sex(text, mrz)
    code = parse_code(text)

    data = {
        "Фамилия":           fam,
        "Имя":               giv,
        "Отчество":          pat,
        "Пол":               sex,
        "Дата выдачи":       did,
        "Место выдачи":      pi,
        "Серия":             mrz.get("document_number","")[:4],
        "Номер документа":   mrz.get("document_number",""),
        "Дата рождения":     dob,
        "Место рождения":    pb,
        "Код подразделения": code
    }

    logging.info(f"Итоговые данные: {data}")
    pd.DataFrame([data]).to_excel(out_xlsx, index=False)
    logging.info(f"=== DONE, записано в {out_xlsx!r} ===")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python passport_pipeline.py <image> <output.xlsx>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
