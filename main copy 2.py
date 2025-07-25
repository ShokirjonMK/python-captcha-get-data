import requests
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
from io import BytesIO
import re
import datetime
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

app = FastAPI()

MAIN_URL_DTM = "https://my.uzbmb.uz"
MAIN_URL_PM = "https://my.uzbmb.uz"
CAPTCHA_URL_DTM = f"{MAIN_URL_DTM}/uz/site/captcha?v=688323046add4"
CAPTCHA_URL_PM = f"{MAIN_URL_PM}/uz/site/captcha?v=688323046add4"

REPLACEMENTS = {
    '{': '2', '(': '2', '[': '2',
    '|': '1', 'i': '1', 'l': '1',
    'o': '0', 'O': '0',
    's': '5', 'z': '2',
    'S': '8', 'B': '8',
    'g': '9', 'G': '9',
    'x': '*', '×': '*',
    '=': '', '—': '', '-': '',
    'y': '', 'Y': '',
}


def download_and_process_image(url: str) -> Image.Image:
    response = requests.get(url)
    image = Image.open(BytesIO(response.content)).convert("L")
    image = image.resize((image.width * 2, image.height * 2))
    image = image.filter(ImageFilter.SHARPEN)
    image = ImageEnhance.Contrast(image).enhance(3)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"captcha_debug_{timestamp}.jpg"
    image.save(filename)
    print(f"📷 CAPTCHA saqlandi: {filename}")

    return image


def extract_text(image: Image.Image) -> str:
    raw_text = pytesseract.image_to_string(image, config="--psm 7")
    print("🧠 OCR natijasi:", raw_text.strip())
    return raw_text.strip().lower()


def clean_text(text: str) -> str:
    for old, new in REPLACEMENTS.items():
        text = text.replace(old, new)
    text = re.sub(r'[^\d\+\-\*/]', '', text)
    text = re.sub(r'\*+', '*', text)
    return text


def evaluate_expression(text: str):
    match = re.search(r'\d+[\+\-\*/]\d+', text)
    if match:
        expr = match.group(0)
        try:
            result = eval(expr)
            return int(result)
        except Exception:
            return None
    return None


@app.get("/solve-captcha")
def solve_captcha():
    try:
        image = download_and_process_image(CAPTCHA_URL_DTM)
        raw = extract_text(image)
        cleaned = clean_text(raw)
        result = evaluate_expression(cleaned)
        if result is not None:
            return JSONResponse(content={"text": "topildi", "code": result})
        else:
            return JSONResponse(content={"text": "topilmadi", "code": None})
    except Exception as e:
        return JSONResponse(content={"text": "xatolik", "error": str(e)})


@app.get("/get-data")
def get_data(
    seria: str = Query(..., min_length=2, max_length=2),
    raqam: str = Query(..., min_length=6, max_length=7),
    sana: str = Query(..., regex=r"\d{2}\.\d{2}\.\d{4}")  # Format: DD.MM.YYYY
):
    try:
        # 1-qadam: CAPTCHA ni hal qilish
        image = download_and_process_image(CAPTCHA_URL_PM)
        raw = extract_text(image)
        cleaned = clean_text(raw)
        code = evaluate_expression(cleaned)

        if code is None:
            return JSONResponse(content={"text": "captcha xato o'qildi"})

        # 2-qadam: Ma’lumot yuborish
        payload = {
            "document_type": "passport",
            "person_passport_seria": seria,
            "person_passport_number": raqam,
            "person_birth_date": sana,
            "verify_code": str(code),
            "is_consent": 1
        }

        response = requests.post(
            f"{MAIN_URL_PM}/uz/api/gsp/person-data",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        return JSONResponse(content=response.json())

    except Exception as e:
        return JSONResponse(content={"text": "xatolik", "error": str(e)})
