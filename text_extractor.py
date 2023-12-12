# from pytesseract import pytesseract
# from PIL import Image
# import os

# pytesseract.pytesseract_cmd = '/opt/homebrew/bin/tesseract'

# def text_extractor(image_path):
#   try:
#     text = pytesseract.image_to_string(Image.open(image_path))
#     print("OCR Result:")
#     print(text)
#     return text
#   except pytesseract.TesseractError as e:
#     print(f"Error during OCR: {e}")

import easyocr
import cv2
import ssl
ssl._create_default_https_context = ssl._create_unverified_context


def text_extractor(image_path):
  reader = easyocr.Reader(['en'], gpu=True)
  result = reader.readtext(image_path)
  extracted_text = [entry[1] for entry in result]
  result_string = '\n'.join(extracted_text)
  print(result_string)
  return result_string