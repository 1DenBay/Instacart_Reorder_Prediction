import sqlite3
import pandas as pd
import xgboost as xgb
from flask import Flask, request, jsonify, render_template
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


""" FLASK API TANIMLARI """
# basit bir anasayfa oluşturduk onu çekiyoruz
@app.route('/')
def home():
    return render_template('index.html') 

# Kullanıcı ID'sini almak için kullanıcıdan gelen sorgu parametresi alıyoruz ve kontrol ediyoruz
@app.route('/predict', methods=['GET'])
def predict():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "Lütfen bir user_id girin. Örn: /predict?user_id=1"}), 400
    conn = get_db_connection()


    # ARAMA İÇİN SQL SORGUSU
    # SQL ile Anlık Veri Hazırlığı (geliştirme aşamasında eğitim setindeki mantığın birebir aynısını kuruyoruz gecikme yada eksiklik olmaması için)
    query = """
    SELECT 
        -- Ürün Bilgileri (Sonuçta ismini göstermek için)
        p.product_name,
        p.product_id,
        
        -- ÖZELLİKLER (MODELİN GİRDİLERİ)
        -- 1. UXP (Kullanıcı-Ürün)
        uxp.uxp_total_bought,
        uxp.uxp_reorder_ratio,
        uxp.uxp_avg_position,
        
        -- 2. USER (Kullanıcı)
        uf.user_total_orders,
        uf.user_avg_days_between,
        uf.user_avg_basket_size,
        uf.user_avg_hour,
        uf.user_avg_dow,
        uf.user_recent_avg_days,
        
        -- 3. PRODUCT (Ürün)
        pf.prod_total_orders,
        pf.prod_reorder_rate,
        pf.prod_avg_position,
        pf.aisle_id,       
        pf.department_id, 
        
        -- 4. DİNAMİK HESAPLAMALAR
        -- Model 'orders_since_last_bought' özelliğini ister.
        -- Şu an yeni bir sipariş (Gelecek Sipariş) anında olduğumuz için:
        -- (Toplam Sipariş + 1) - (Son Alınan Sipariş Numarası)
        ((uf.user_total_orders + 1) - uxp.uxp_last_order_number) as orders_since_last_bought,
        
        -- Context (Zaman): Canlı veride 'şu anki saat' alınmalı ama
        -- basitlik için kullanıcının 'ortalama saati'ni şimdiki saat gibi veriyoruz.
        uf.user_avg_hour as order_hour_of_day,
        uf.user_avg_dow as order_dow

    FROM uxp_features uxp
    JOIN user_features uf ON uxp.user_id = uf.user_id
    JOIN product_features pf ON uxp.product_id = pf.product_id
    JOIN products p ON uxp.product_id = p.product_id
    WHERE uxp.user_id = ?
    """
    
    df = pd.read_sql(query, conn, params=(user_id,))
    conn.close()
    
    if df.empty:
        return jsonify({"message": "Kullanıcı bulunamadı veya geçmiş verisi yok.", "user_id": user_id}), 404


    # TAHMİN İÇİN MODEL GİRİŞLERİNİN HAZIRLANMASI
    # Model eğitilirken sütunlar hangi sıradaysa, burada da ÖYLE OLMAK ZORUNDA.
    feature_columns = [
        'uxp_total_bought', 
        'uxp_reorder_ratio', 
        'user_total_orders', 
        'user_avg_days_between', 
        'prod_total_orders', 
        'prod_reorder_rate',      
        'user_avg_basket_size',    
        'prod_avg_position', 
        'uxp_avg_position', 
        'order_hour_of_day', 
        'order_dow', 
        'user_avg_hour', 
        'user_avg_dow', 
        'aisle_id', 
        'department_id', 
        'user_recent_avg_days', 
        'orders_since_last_bought' # <-- En sona geldi
    ]
    # Sadece özellik sütunlarını seç ve eksikleri doldur
    X_pred = df[feature_columns].fillna(0)
    # Tahmin
    # Model bize her satır için 0 ile 1 arası bir olasılık verir
    probs = model.predict_proba(X_pred)[:, 1]
    df['probability'] = probs
    

    # EŞİK DEĞER FİLTRELEMESİ
    # Sadece %22'nin üzerindekileri al ve puana göre sırala
    threshold = 0.22
    recommendations = df[df['probability'] > threshold].sort_values(by='probability', ascending=False)
    

    # JSON ÇIKTISI
    results = []
    for _, row in recommendations.iterrows(): # Her öneri için ürün adı, olasılık ve reyon ID'sini alıyoruz
        results.append({
            "product_name": row['product_name'],
            "probability": round(float(row['probability']), 4),
            "aisle_id": int(row['aisle_id'])
        })
    
    return jsonify({ # Sonuçları JSON formatında döndürüyoruz
        "user_id": user_id,
        "count": len(results),
        "recommendations": results
    })


if __name__ == '__main__':
    print("🚀 Sunucu başlatılıyor... http://127.0.0.1:5000")
    app.run(debug=True, port=5000)