from fastapi import FastAPI, Query
from pydantic import BaseModel
import requests
from PIL import Image
from io import BytesIO
import cv2
import numpy as np
from transformers import pipeline
import os
import time

app = FastAPI()

pipe = pipeline("image-to-text", model="microsoft/trocr-large-printed")

def preprocess(image):
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    processed = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                      cv2.THRESH_BINARY_INV, 11, 3)
    processed = cv2.resize(processed, (0, 0), fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    return processed

def solve_expression_image(image_url: str):
    try:
        response = requests.get(image_url)
        response.raise_for_status()
        image = Image.open(BytesIO(response.content)).convert("RGB")
    except Exception as e:
        return {"error": f"Image download or open failed: {str(e)}"}

    processed = preprocess(image)

    try:
        os.makedirs("images", exist_ok=True)
        timestamp = int(time.time() * 1000)  # Millisekundli vaqt tamg‘asi
        save_path = os.path.join("images", f"processed_{timestamp}.jpg")
        if not cv2.imwrite(save_path, processed):
            return {"error": "Failed to save the image. imwrite returned False."}
    except Exception as e:
        return {"error": f"Image save error: {str(e)}"}

    try:
        expr = pipe(save_path)[0]['generated_text']
        print("OCR natija:", expr)
    except Exception as e:
        return {"error": f"OCR error: {str(e)}"}

    expr = expr.replace('×', '*').replace('x', '*').replace('X', '*') \
               .replace('–', '-').replace('—', '-') \
               .replace('÷', '/').replace('=', '').strip()

    try:
        result = eval(expr)
        result = int(result) if result == int(result) else round(result, 2)
        return {"expression": expr, "result": result}
    except Exception as e:
        return {"expression": expr, "error": f"Eval error: {str(e)}"}

@app.get("/solve")
def solve(image_url: str = Query(..., description="Captcha image URL")):
    return solve_expression_image(image_url)
