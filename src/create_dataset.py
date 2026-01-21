import pandas as pd
import sqlite3
import time
from pathlib import Path

# --- AYARLAR ---
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "instacart.db"
OUTPUT_DIR = BASE_DIR / "data" / "processed"

def get_db_connection():
    return sqlite3.connect(DB_PATH)

def create_train_dataset():
    """
    Model eğitimi için gerekli olan 'Master Table'ı oluşturur ve CSV olarak kaydeder.
    Bu tablo şunları içerir:
    - user_id, product_id
    - Tüm featurelar (user, product, uxp)
    - TARGET (reordered): 1 (aldı) veya 0 (almadı)
    """
    print("🚂 Eğitim Verisi (Train Dataset) hazırlanıyor...")
    start_time = time.time()
    conn = get_db_connection()
    
    # --- MÜHENDİSLİK VİZYONU: ADAY BELİRLEME (CANDIDATE GENERATION) ---
    # Her kullanıcı için tüm marketteki 50.000 ürünü tahmin etmeye çalışamayız.
    # Sadece kullanıcının "daha önce en az bir kez aldığı" ürünleri (uxp_features tablosundakileri)
    # aday olarak seçiyoruz. Buna "Candidate Generation" denir.
    
    query = """
    SELECT 
        -- Kimlikler
        o.user_id,
        uxp.product_id,
        
        -- Featurelar (Özellikler)
        uxp.uxp_total_bought,
        uxp.uxp_reorder_ratio,
        uf.user_total_orders,
        uf.user_avg_days_between,
        pf.prod_total_orders,
        pf.prod_reorder_rate,
        
        -- Hedef Değişken (Label Construction)
        -- Eğer train setindeki siparişte bu ürün varsa 1, yoksa 0.
        CASE 
            WHEN op_train.reordered = 1 THEN 1 
            ELSE 0 
        END as reordered
        
    FROM orders o
    
    -- 1. ADIM: Sadece 'train' setindeki kullanıcıları al (Cevabını bildiklerimiz)
    JOIN uxp_features uxp ON o.user_id = uxp.user_id
    
    -- 2. ADIM: Özellik Tablolarını Bağla (LEFT JOIN)
    LEFT JOIN user_features uf ON o.user_id = uf.user_id
    LEFT JOIN product_features pf ON uxp.product_id = pf.product_id
    
    -- 3. ADIM: Hedefi Bul (Bu ürün son siparişte var mı?)
    -- order_products__train tablosuna bakıyoruz.
    LEFT JOIN order_products__train op_train 
        ON o.order_id = op_train.order_id 
        AND uxp.product_id = op_train.product_id
        
    WHERE o.eval_set = 'train'
    """
    
    # Veriyi çek (Chunking kullanmıyoruz, yaklaşık 8-10 milyon satır olabilir, 
    print("   --> SQL çalıştırılıyor (Bu işlem biraz RAM tüketebilir)...")
    df = pd.read_sql(query, conn)
    
    # Eksik verileri (NaN) doldurma
    # Left joinlerden dolayı bazı özellikler boş gelebilir, onları 0 yapıyoruz.
    df = df.fillna(0)
    
    print(f"   --> {len(df):,} satırlık veri seti oluşturuldu.")
    
    # CSV'ye kaydet
    output_path = OUTPUT_DIR / "train_data.csv"
    print(f"   --> CSV kaydediliyor: {output_path}")
    df.to_csv(output_path, index=False)
    
    conn.close()
    print(f"✅ Tamamlandı! Süre: {time.time() - start_time:.2f} sn")

if __name__ == "__main__":
    create_train_dataset()