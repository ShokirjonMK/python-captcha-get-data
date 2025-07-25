from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
from PIL import Image
from io import BytesIO
import cv2
import numpy as np
from transformers import pipeline
import re

app = FastAPI()
pipe = pipeline("image-to-text", model="microsoft/trocr-large-printed")

PM_CAPTCHA_URL = "https://pm.gov.uz/site/captcha?v=68836b9bc2df8"
PM_API_URL = "https://pm.gov.uz/uz/api/gsp/person-data"

HEADERS_PM = {
    'Content-Type': 'application/x-www-form-urlencoded',
    'Origin': 'https://pm.gov.uz',
    'Referer': 'https://pm.gov.uz/uz',
    'User-Agent': 'Mozilla/5.0',
    'Cookie': 'login_sessionPmGovUz=b3nvb3hbp6of6qf03fonk92hf3; _language=06b99ca738b40b8d759d6e14412dbf2a7e4750139d5846dcb9d04e71727be7b0a%3A2%3A%7Bi%3A0%3Bs%3A9%3A%22_language%22%3Bi%3A1%3Bs%3A2%3A%22uz%22%3B%7D; _csrf=245dda40f7c9d70987a2abbf7d7b480017a833c8d356c60f9eb28076e75b17fea%3A2%3A%7Bi%3A0%3Bs%3A5%3A%22_csrf%22%3Bi%3A1%3Bs%3A32%3A%221SoJaUpZd50s3nFRM4vd1BjU4fJkFNZe%22%3B%7D; smart_top=1'
}


class PassportInfo(BaseModel):
    passport_serial: str
    passport_number: str
    birth_date: str  # format: DD.MM.YYYY


def preprocess(image):
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    processed = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                      cv2.THRESH_BINARY_INV, 11, 3)
    processed = cv2.resize(processed, (0, 0), fx=3, fy=3,
                           interpolation=cv2.INTER_CUBIC)
    return processed


def solve_captcha(image_url, session):
    try:
        response = session.get(image_url, headers=HEADERS_PM)
        image = Image.open(BytesIO(response.content)).convert("RGB")
    except Exception as e:
        return {"error": f"Captcha image error: {str(e)}"}

    processed = preprocess(image)

    try:
        expr = pipe(Image.fromarray(processed))[0]['generated_text']
    except Exception as e:
        return {"error": f"OCR error: {str(e)}"}

    expr = expr.replace('×', '*').replace('x', '*').replace('X', '*') \
               .replace('–', '-').replace('—', '-') \
               .replace('÷', '/').replace('=', '').strip()

    try:
        result = eval(expr)
        return {"result": str(int(result))}
    except Exception as e:
        return {"error": f"Eval error: {str(e)}"}


@app.post("/get-pm-data")
def get_pm_data(info: PassportInfo):
    session = requests.Session()

    # 1. Get captcha and solve
    captcha = solve_captcha(PM_CAPTCHA_URL, session)
    if "error" in captcha:
        return JSONResponse(status_code=400, content={"status": "error", "message": captcha["error"]})

    verify_code = captcha["result"]


    birth_date = info.birth_date.strftime('%d.%m.%Y')
    # 2. Prepare form data
    form_data = {
        'document_type': 'passport',
        'person_passport_seria': info.passport_serial,
        'person_passport_number': info.passport_number,
        'person_birth_date': birth_date,
        'verify_code': verify_code,
        'is_consent': 1
    }

    try:
        response = session.post(PM_API_URL, data=form_data, headers=HEADERS_PM)
        data = response.json()

        if data.get("status") is True:
            return JSONResponse(
                status_code=200,
                content={"status": "success", "data": data["result"]}
            )
        else:
            return JSONResponse(
                status_code=422,
                content={"status": "fail", "message": data.get(
                    "message", "Xatolik"), "code": data.get("code", 422)}
            )

    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
