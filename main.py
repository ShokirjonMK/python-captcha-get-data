from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
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

# -------------------- CONSTANTS --------------------
# DTM
MAIN_URL_DTM = "https://my.uzbmb.uz"
DTM_CAPTCHA_PAGE = f"{MAIN_URL_DTM}/allow/bachelor-answer"
DTM_HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'Referer': DTM_CAPTCHA_PAGE,
    'Origin': MAIN_URL_DTM,
    'Content-Type': 'application/x-www-form-urlencoded',
}

# PM
MAIN_URL_PM = "https://pm.gov.uz"
PM_CAPTCHA_URL = f"{MAIN_URL_PM}/site/captcha?v=68836b9bc2df8"
PM_API_URL = f"{MAIN_URL_PM}/uz/api/gsp/person-data"
PM_HEADERS = {
    'Content-Type': 'application/x-www-form-urlencoded',
    'Origin': MAIN_URL_PM,
    'Referer': f'{MAIN_URL_PM}/uz',
    'User-Agent': 'Mozilla/5.0',
    'Cookie': 'login_sessionPmGovUz=b3nvb3hbp6of6qf03fonk92hf3; _language=06b99ca738b40b8d759d6e14412dbf2a7e4750139d5846dcb9d04e71727be7b0a%3A2%3A%7Bi%3A0%3Bs%3A9%3A%22_language%22%3Bi%3A1%3Bs%3A2%3A%22uz%22%3B%7D; _csrf=245dda40f7c9d70987a2abbf7d7b480017a833c8d356c60f9eb28076e75b17fea%3A2%3A%7Bi%3A0%3Bs%3A5%3A%22_csrf%22%3Bi%3A1%3Bs%3A32%3A%221SoJaUpZd50s3nFRM4vd1BjU4fJkFNZe%22%3B%7D; smart_top=1'
}

# -------------------- MODELS --------------------


class PassportInfoPM(BaseModel):
    passport_serial: str
    passport_number: str
    birth_date: str  # format: DD.MM.YYYY


class PassportInfoDTM(BaseModel):
    passport_serial: str
    passport_number: str
    passport_pin: str

# -------------------- UTILS --------------------


def preprocess(image):
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    processed = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                      cv2.THRESH_BINARY_INV, 11, 3)
    processed = cv2.resize(processed, (0, 0), fx=3, fy=3,
                           interpolation=cv2.INTER_CUBIC)
    return processed


def solve_captcha(image_url, session, headers):
    try:
        response = session.get(image_url, headers=headers)
        image = Image.open(BytesIO(response.content)).convert("RGB")
        processed = preprocess(image)
        expr = pipe(Image.fromarray(processed))[0]['generated_text']
    except Exception as e:
        return {"error": f"OCR or image error: {str(e)}"}

    expr = expr.replace('×', '*').replace('x', '*').replace('X', '*') \
               .replace('–', '-').replace('—', '-') \
               .replace('÷', '/').replace('=', '').strip()

    try:
        result = eval(expr)
        return {"result": str(int(result))}
    except Exception as e:
        return {"error": f"Eval error: {str(e)}"}

# -------------------- DTM: GET CAPTCHA + CSRF --------------------


def get_dtm_csrf_and_captcha():
    session = requests.Session()
    try:
        res = session.get(DTM_CAPTCHA_PAGE, headers=DTM_HEADERS)
        html = res.text

        csrf_match = re.search(r'name="_csrf" value="([^"]+)"', html)
        csrf_token = csrf_match.group(1) if csrf_match else None

        captcha_match = re.search(
            r'<img id="my-captcha-image" src="([^"]+)"', html)
        captcha_url = MAIN_URL_DTM + \
            captcha_match.group(1) if captcha_match else None

        cookie_string = "; ".join(
            [f"{c.name}={c.value}" for c in session.cookies])

        return {
            "csrf": csrf_token,
            "captcha_url": captcha_url,
            "cookie": cookie_string,
            "session": session
        }
    except Exception as e:
        return {"error": f"CSRF or captcha fetch error: {str(e)}"}

# -------------------- ENDPOINT: DTM PDF --------------------


@app.post("/get-dtm-pdf")
def get_dtm_pdf(info: PassportInfoDTM):
    dtm = get_dtm_csrf_and_captcha()
    if "error" in dtm:
        return JSONResponse(status_code=400, content={"status": "error", "message": dtm["error"]})

    if not dtm["csrf"] or not dtm["captcha_url"]:
        return JSONResponse(status_code=400, content={"status": "error", "message": "CSRF yoki captcha topilmadi"})

    captcha = solve_captcha(dtm["captcha_url"], dtm["session"], DTM_HEADERS)
    if "error" in captcha:
        return JSONResponse(status_code=400, content={"status": "error", "message": captcha["error"]})

    form_data = {
        '_csrf': dtm['csrf'],
        'Allow[psser]': info.passport_serial,
        'Allow[psnum]': info.passport_number,
        'Allow[imie]': info.passport_pin,
        'Allow[verifyCode]': captcha['result'],
        'login-button': ''
    }

    try:
        response = dtm['session'].post(
            f"{MAIN_URL_DTM}/allow/bachelor-answer",
            data=form_data,
            headers={**DTM_HEADERS, 'Cookie': dtm['cookie']}
        )

        if response.headers.get('Content-Type') == 'application/pdf':
            return Response(
                content=response.content,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": "attachment; filename=dtm-result.pdf"}
            )
        else:
            return JSONResponse(
                status_code=422,
                content={"status": "error",
                         "message": "PDF qaytmadi, ehtimol captcha noto‘g‘ri"}
            )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# -------------------- ENDPOINT: PM JSON --------------------


@app.post("/get-pm-data")
def get_pm_data(info: PassportInfoPM):
    session = requests.Session()
    captcha = solve_captcha(PM_CAPTCHA_URL, session, PM_HEADERS)
    if "error" in captcha:
        return JSONResponse(status_code=400, content={"status": "error", "message": captcha["error"]})

    form_data = {
        'document_type': 'passport',
        'person_passport_seria': info.passport_serial,
        'person_passport_number': info.passport_number,
        'person_birth_date': info.birth_date,
        'verify_code': captcha['result'],
        'is_consent': 1
    }

    try:
        response = session.post(PM_API_URL, data=form_data, headers=PM_HEADERS)
        data = response.json()

        if data.get("status") is True:
            return JSONResponse(status_code=200, content={"status": "success", "data": data["result"]})
        else:
            return JSONResponse(
                status_code=422,
                content={
                    "status": "fail",
                    "message": data.get("message", "Xatolik"),
                    "code": data.get("code", 422)
                }
            )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
