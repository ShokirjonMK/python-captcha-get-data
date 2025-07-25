import requests
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
from io import BytesIO
import re
import datetime
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()

CAPTCHA_URL = "https://my.uzbmb.uz/site/captcha?v=687e14335d2c49.56273221"

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
            return {"text": "topildi", "expression": expr, "result": result}
        except Exception:
            return {"text": "topilmadi", "expression": expr}
    else:
        return {"text": "topilmadi", "expression": ""}

@app.get("/solve-captcha")
def solve_captcha():
    try:
        image = download_and_process_image(CAPTCHA_URL)
        raw = extract_text(image)
        cleaned = clean_text(raw)
        result = evaluate_expression(cleaned)
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(content={"text": "xatolik", "error": str(e)})
