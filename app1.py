from flask import Flask, request, jsonify
from ultralytics import YOLO
import cv2
import numpy as np
import requests

# Flask ilova
app = Flask(__name__)

# Model va klasslar
MODEL_PATH = "best.pt"
CLASS_NAMES = list("0123456789×=+-*/")
model = YOLO(MODEL_PATH)

def load_image_from_url(url):
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        img_array = np.asarray(bytearray(resp.content), dtype=np.uint8)
        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        return image
    except Exception as e:
        print(f"[ERROR] {e}")
        return None

def clean_expression(text):
    text = text.replace('x', '*').replace('×', '*').replace('=', '')
    return ''.join(c for c in text if c in '0123456789+-*/(). ')

@app.route('/ocr', methods=['POST'])
def ocr_from_url():
    data = request.get_json()
    url = data.get('url')

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    image = load_image_from_url(url)
    if image is None:
        return jsonify({'error': 'Image download failed'}), 400

    # YOLO predict
    results = model.predict(image, imgsz=640, conf=0.25)
    boxes = results[0].boxes
    detected_text = ""

    if boxes is not None and len(boxes) > 0:
        sorted_boxes = sorted(
            zip(boxes.cls.tolist(), boxes.xyxy.tolist()),
            key=lambda x: x[1][0]
        )
        for class_id, _ in sorted_boxes:
            detected_text += CLASS_NAMES[int(class_id)]

        expression = clean_expression(detected_text)
        try:
            result = eval(expression)
        except:
            result = None

        return jsonify({
            'text': detected_text,
            'expression': expression,
            'result': result
        })
    else:
        return jsonify({'text': '', 'expression': '', 'result': None})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
