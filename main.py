import requests
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
from io import BytesIO
import re
import os
import datetime
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

app = FastAPI()

MAIN_URL = "https://pm.gov.uz"

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


IMAGE_DIR = "images"  # Rasmlar saqlanadigan papka

def download_and_process_image(url: str) -> Image.Image:
    response = requests.get(url)
    image = Image.open(BytesIO(response.content)).convert("L")
    image = image.resize((image.width * 2, image.height * 2))
    image = image.filter(ImageFilter.SHARPEN)
    image = ImageEnhance.Contrast(image).enhance(3)

    # 📂 Rasmni saqlash uchun papka yaratish
    os.makedirs(IMAGE_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = os.path.join(IMAGE_DIR, f"captcha_{timestamp}.jpg")
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


@app.get("/verify-person")
def verify_person(
    passport_seria: str = Query(..., min_length=2, max_length=2),
    passport_number: str = Query(..., min_length=5),
    birth_date: str = Query(..., regex=r"\d{2}\.\d{2}\.\d{4}")
):
    try:
        # 1-qadam: CAPTCHA ni yechish
        captcha_url = f"{MAIN_URL}/uz/site/captcha"
        image = download_and_process_image(captcha_url)
        raw = extract_text(image)
        cleaned = clean_text(raw)
        code = evaluate_expression(cleaned)

        if code is None:
            return JSONResponse(content={"text": "CAPTCHA topilmadi", "raw": raw, "cleaned": cleaned}, status_code=400)

        print(f"🔢 CAPTCHA natijasi: {code}")

        # 2-qadam: ma'lumot yuborish
        data_url = f"{MAIN_URL}/uz/api/gsp/person-data"
        payload = {
            "document_type": "passport",
            "person_passport_seria": passport_seria,
            "person_passport_number": passport_number,
            "person_birth_date": birth_date,
            "verify_code": code,
            "is_consent": 1
        }

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://pm.gov.uz',
            'Referer': 'https://pm.gov.uz/uz',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            'Cookie': 'login_sessionPmGovUz=b3nvb3hbp6of6qf03fonk92hf3; _language=06b99ca738b40b8d759d6e14412dbf2a7e4750139d5846dcb9d04e71727be7b0a%3A2%3A%7Bi%3A0%3Bs%3A9%3A%22_language%22%3Bi%3A1%3Bs%3A2%3A%22uz%22%3B%7D; _csrf=245dda40f7c9d70987a2abbf7d7b480017a833c8d356c60f9eb28076e75b17fea%3A2%3A%7Bi%3A0%3Bs%3A5%3A%22_csrf%22%3Bi%3A1%3Bs%3A32%3A%221SoJaUpZd50s3nFRM4vd1BjU4fJkFNZe%22%3B%7D; smart_top=1; _language=06b99ca738b40b8d759d6e14412dbf2a7e4750139d5846dcb9d04e71727be7b0a%3A2%3A%7Bi%3A0%3Bs%3A9%3A%22_language%22%3Bi%3A1%3Bs%3A2%3A%22uz%22%3B%7D; login_sessionPmGovUz=88htmg596gmejv1b0jfnhaqots'
        }

        response = requests.post(data_url, data=payload, headers=headers)
        return JSONResponse(content=response.json())

    except Exception as e:
        return JSONResponse(content={"text": "xatolik", "error": str(e)}, status_code=500)
