import sqlite3
import pandas as pd
import xgboost as xgb
from flask import Flask, request, jsonify
import os

app = Flask(__name__)

""" DOSYA YOLUNUN DÜZENLENMESİ """
# app.py dosyasının olduğu klasörün tam adresini alıyoruz (model ve veritabanının dosya dizininde nerede olduğunu oto bulmak için)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Modeli ve Veritabanını bu adrese göre buluyoruz
# (Dosyalar app.py ile aynı klasörde veya alt klasörlerde olmalı)
MODEL_PATH = os.path.join(BASE_DIR, "xgb_prod_final_v3.json")
DB_PATH = os.path.join(BASE_DIR, "data", "processed", "instacart.db")

print(f"Çalışma Dizini: {BASE_DIR}")
print(f"Model Yolu: {MODEL_PATH}")

# Dosya var mı kontrolü (Hata varsa baştan söylesin)
if not os.path.exists(MODEL_PATH):
    print("❌ HATA: Model dosyası bulunamadı!")
    print("   Lütfen 'xgb_prod_final_v3.json' dosyasının app.py ile aynı dizinde olduğundan emin olun.")
    exit(1)


""" MODEL VE VERİTABANI BAĞLANTISI """
print("Model hafızaya yükleniyor")
model = xgb.XGBClassifier() 
model.load_model(MODEL_PATH)
print(f"✅ Model başarıyla yüklendi!")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
