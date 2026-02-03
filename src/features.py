import pandas as pd
import sqlite3
import os
from pathlib import Path
import time

"""
    Veri tabanından model için özellikler çıkarır.
    USER_FEATURE TABLOSU (Kullanıcıyı tanıma)
    PRODUCT_FEATURE TABLOSU (Ürünü tanıma)
    USER_PRODUCT_FEATURE (uxp_tablo) TABLOSU (Kullanıcıyı ve Ürünü işilkilendirme)
"""

# --- AYARLAR ---
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "instacart.db"

def get_db_connection():
    return sqlite3.connect(DB_PATH)


"""
    USER_FEATURE TABLOSU (Kullanıcıyı tanıma)
    Kullanıcı bazlı özellikleri hesaplar ve yeni bir tabloya yazar.
    1. user_total_orders: Kullanıcının toplam sipariş sayısı
    2. user_avg_days_between: Siparişler arası ortalama gün sayısı
"""
def create_user_features():
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


"""
    Product_FEATURE TABLOSU
    Ürün bazlı özellikleri hesaplar.
    1. prod_total_orders: Ürün toplam kaç kere satıldı?
    2. prod_reorder_rate: Ürün ne sıklıkla tekrar sipariş ediliyor?
"""
def create_product_features():
    
    print("🍎 Ürün Özellikleri (Product Features) hesaplanıyor...")
    start_time = time.time()
    conn = get_db_connection()
    
    # SQL: Sadece prior tablosunu kullanarak ürün istatistiklerini çıkarıyoruz
    # AVG(reordered) bize o ürünün tekrar alınma olasılığını verir.
    query = """
    SELECT 
        product_id,         --Ürünlerin ID lerini alır
        COUNT(*) as prod_total_orders,      --Alınan her ID nin sipariş tablosunda kaç kere geçtiğini sayar
        AVG(reordered) as prod_reorder_rate         --reordered sütunu 0 (sipariş yok), 1 (sipariş var) şeklindedir. 0 ve 1 lerin ortalamasını alır yani ürünün tekrar sipariş edilme oranını direkt verir
    FROM order_products__prior       --Verileri önceden sipariş edilen ürünlerden al
    GROUP BY product_id         --Satırları tek tek kontrol et aynı ID olanları yanı aynı ürünleri birleştir
    """
    
    df = pd.read_sql(query, conn)
    print(f"   --> {len(df)} ürün için özellikler çıkarıldı.")
    
    df.to_sql('product_features', conn, if_exists='replace', index=False)
    conn.close()
    print(f"✅ Tamamlandı! Süre: {time.time() - start_time:.2f} sn")


"""
    USER_PRODUCT TABLOSU (uxp)
    Kullanıcı-Ürün Çifti Özellikleri
    En kritik tablo budur. "Ahmet - Muz" ilişkisini tutar.
    1. uxp_total_bought: Kullanıcı bu ürünü toplam kaç kere aldı?
    2. uxp_reorder_ratio: Kullanıcının bu ürünü tekrar alma oranı.
"""
def create_uxp_features():
    
    print("🤝 Kullanıcı-Ürün İlişkileri (UxP Features) hesaplanıyor... (Bu biraz sürebilir)")
    start_time = time.time()
    conn = get_db_connection()
    
    # SQL: Hem orders hem order_products tablolarını birleştiriyoruz. Ekler kullanılır.
    query = """
    SELECT 
        o.user_id,      --Order tablosundan kullanıcı idler
        op.product_id,      --order-prod tablosundan ürün idleri
        COUNT(*) as uxp_total_bought,       --Bu kullanıcı bu ürünü toplam kaç kere aldı
        AVG(op.reordered) as uxp_reorder_ratio      --Bu kullanıcı bu ürünü tekrar alma oranı
    FROM order_products__prior op       --order_products tablosundan verileri al
    JOIN orders o ON op.order_id = o.order_id       --orders tablosu ile order_products tablosunu order_id üzerinden birleştir
    GROUP BY o.user_id, op.product_id       --Kullanıcı ve ürün bazında gruplandır
    """
    
    # Chunking (Parçalı Okuma) kullanmıyoruz çünkü sonucun boyutu RAM'e sığar (yaklaşık 10-15 milyon satır).
    # Ancak 8GB RAM altı makinelerde dikkatli olunmalı.
    df = pd.read_sql(query, conn)
    print(f"   --> {len(df)} adet kullanıcı-ürün ilişkisi bulundu.")
    
    df.to_sql('uxp_features', conn, if_exists='replace', index=False)
    conn.close()
    print(f"✅ Tamamlandı! Süre: {time.time() - start_time:.2f} sn")


if __name__ == "__main__":
    create_user_features()
    create_product_features()
    create_uxp_features()