import pandas as pd
import sqlite3
import os
from pathlib import Path
import time

# --- AYARLAR ---
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "instacart.db"

def get_db_connection():
    return sqlite3.connect(DB_PATH)

def create_user_features():
    """
    Kullanıcı bazlı özellikleri (User Features) hesaplar ve yeni bir tabloya yazar.
    1. user_total_orders: Kullanıcının toplam sipariş sayısı
    2. user_avg_days_between: Siparişler arası ortalama gün sayısı
    """
    print("👤 Kullanıcı Özellikleri (User Features) hesaplanıyor...")
    start_time = time.time()
    
    conn = get_db_connection()
    
    # orders tablosundan 'prior' (önceki siparişten bu yana geçen süre) setini alıyoruz (modelin öğrenmesi gereken geçmiş)
    query = """
    SELECT 
        user_id,
        MAX(order_number) as user_total_orders,
        AVG(days_since_prior_order) as user_avg_days_between
    FROM orders
    WHERE eval_set = 'prior'
    GROUP BY user_id
    """
    
    df = pd.read_sql(query, conn)
    
    print(f"   --> {len(df)} kullanıcı için özellikler çıkarıldı.")
    
    # Yeni tablo olarak veritabanına kaydet
    # 'user_features' adında yeni bir tablo yaratıyoruz.
    df.to_sql('user_features', conn, if_exists='replace', index=False)
    
    conn.close()
    print(f"✅ Tamamlandı! Süre: {time.time() - start_time:.2f} sn")

if __name__ == "__main__":
    create_user_features()