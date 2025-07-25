from fastapi import FastAPI, Query, Response
from pydantic import BaseModel
import requests
from PIL import Image
from io import BytesIO
import cv2
import numpy as np
from transformers import pipeline
import os
import time
import re

app = FastAPI()
pipe = pipeline("image-to-text", model="microsoft/trocr-large-printed")

headers = {
    'User-Agent': 'Mozilla/5.0',
    'Referer': 'https://my.uzbmb.uz/allow/bachelor-answer',
    'Origin': 'https://my.uzbmb.uz',
    'Content-Type': 'application/x-www-form-urlencoded',
}

class PassportInfo(BaseModel):
    passport_serial: str
    passport_number: str
    passport_pin: str

def preprocess(image):
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    processed = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                      cv2.THRESH_BINARY_INV, 11, 3)
    processed = cv2.resize(processed, (0, 0), fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    return processed

def get_csrf_cookie_captcha():
    session = requests.Session()
    res = session.get("https://my.uzbmb.uz/allow/bachelor-answer", headers=headers)
    html = res.text

    # CSRF token
    csrf_match = re.search(r'name="_csrf" value="([^"]+)"', html)
    csrf_token = csrf_match.group(1) if csrf_match else None

    # Captcha URL
    captcha_match = re.search(r'<img id="my-captcha-image" src="([^"]+)"', html)
    captcha_url = "https://my.uzbmb.uz" + captcha_match.group(1) if captcha_match else None

    cookie_string = "; ".join([f"{c.name}={c.value}" for c in session.cookies])

    return {
        "csrf": csrf_token,
        "captcha_url": captcha_url,
        "cookie": cookie_string,
        "session": session  # reuse session to keep cookies
    }

def solve_captcha(image_url, session):
    try:
        response = session.get(image_url, headers=headers)
        image = Image.open(BytesIO(response.content)).convert("RGB")
    except Exception as e:
        return {"error": f"Captcha image error: {str(e)}"}

    processed = preprocess(image)

    try:
        os.makedirs("images", exist_ok=True)
        timestamp = int(time.time() * 1000)
        path = os.path.join("images", f"captcha_{timestamp}.jpg")
        cv2.imwrite(path, processed)
        expr = pipe(path)[0]['generated_text']
    except Exception as e:
        return {"error": f"OCR error: {str(e)}"}

    expr = expr.replace('×', '*').replace('x', '*').replace('X', '*') \
               .replace('–', '-').replace('—', '-') \
               .replace('÷', '/').replace('=', '').strip()
    try:
        result = eval(expr)
        result = int(result) if result == int(result) else round(result, 2)
        return {"result": str(result)}
    except Exception as e:
        return {"error": f"Eval error: {str(e)}"}

@app.post("/get-dtm-pdf")
def get_dtm_pdf(info: PassportInfo):
    data = get_csrf_cookie_captcha()
    if not data["csrf"] or not data["captcha_url"]:
        return {"status": "error", "message": "CSRF yoki captcha topilmadi"}

    captcha = solve_captcha(data["captcha_url"], data["session"])
    if "error" in captcha:
        return {"status": "error", "message": captcha["error"]}

    form_data = {
        '_csrf': data['csrf'],
        'Allow[psser]': info.passport_serial,
        'Allow[psnum]': info.passport_number,
        'Allow[imie]': info.passport_pin,
        'Allow[verifyCode]': captcha['result'],
        'login-button': ''
    }

    try:
        response = data['session'].post(
            "https://my.uzbmb.uz/allow/bachelor-answer",
            data=form_data,
            headers={**headers, 'Cookie': data['cookie']}
        )

        if response.headers.get('Content-Type') == 'application/pdf':
            return Response(
                content=response.content,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": "attachment; filename=dtm-result.pdf"
                }
            )
        else:
            return {"status": "error", "message": "PDF qaytmadi, ehtimol captcha noto‘g‘ri"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
