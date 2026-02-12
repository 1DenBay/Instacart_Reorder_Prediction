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
    user_total_orders: Kullanıcının toplam sipariş sayısı
    user_avg_days_between: Siparişler arası ortalama gün sayısı
    v2-user_avg_basket_size: Ortalama sepet büyüklüğü (Hacim)
    user_avg_hour: Kullanıcının ortalama alışveriş saati.
    user_avg_dow: Kullanıcının ortalama alışveriş günü
    user_recent_avg_days: Kullanıcının son 3 siparişi arasındaki ortalama gün sayısı (trend göstergesi)
"""
def create_user_features():
    print("Kullanıcı Özellikleri (User Features) hesaplanıyor")
    start_time = time.time()
    
    conn = get_db_connection()
    
    # Önce her siparişte kaç ürün var (Sepet Büyüklüğü) hesaplayalım
    # Bu orders tablosunda yok, order_products tablosundan hesaplamamız lazım
    query_basket = """
    SELECT 
        o.user_id,
        COUNT(*) as total_items,
        COUNT(DISTINCT o.order_id) as total_orders
    FROM order_products__prior op
    JOIN orders o ON op.order_id = o.order_id
    GROUP BY o.user_id
    """
    df_basket = pd.read_sql(query_basket, conn)
    # Ortalama sepet büyüklüğünü (Hacim) hesapla
    df_basket['user_avg_basket_size'] = df_basket['total_items'] / df_basket['total_orders']


# Genel ve Trend Hesaplamaları
# SQL yerine veriyi çekip Pandas ile işliyoruz, çünkü "son 3 satırı al" işlemi Pandas'ta daha kolay.    
    query_orders = """
    SELECT          --tüm geçmiş siparişleri çekiyoruz çünkü kullanıcı bazlı özellikler için tüm geçmişe ihtiyacımız var
        user_id, 
        order_number, 
        days_since_prior_order,
        order_hour_of_day,
        order_dow
    FROM orders     --siparişler tablosundan
    WHERE eval_set = 'prior' --geçmiş sipariş olanları al
    """
    # yazdığımız üstteki sql sorgusunu pythona aktarıp dataframe'e dönüştürüyoruz
    df_orders = pd.read_sql(query_orders, conn) 
    
    # Genel Ortalamalar (Tüm Geçmiş)
    user_general = df_orders.groupby('user_id').agg({   # kullanıcı bazında gruplandır
        'order_number': 'max',              # user_total_orders
        'days_since_prior_order': 'mean',   # user_avg_days_between
        'order_hour_of_day': 'mean',        # user_avg_hour
        'order_dow': 'mean'                 # user_avg_dow
    }).reset_index()
    
    # Sütun isimlerini eskisiyle (trend özelliği öncesi sql ile normal çekiyorduk verileri) uyumlu yapalım. yani eski sorgu ile tablo isimleri aynı oldu
    user_general.columns = ['user_id', 'user_total_orders', 'user_avg_days_between', 'user_avg_hour', 'user_avg_dow']
    
    # Trend Analizi (SADECE SON 3 SİPARİŞ)
    # Veriyi sırala ve her kullanıcının son 3 siparişini al
    last_3_orders = df_orders.sort_values(['user_id', 'order_number']).groupby('user_id').tail(3) 
    
    # Son 3 siparişin gün ortalaması (Ahmet son zamanlarda sıklaştırdı mı?)
    user_recent = last_3_orders.groupby('user_id')['days_since_prior_order'].mean().reset_index()
    user_recent.columns = ['user_id', 'user_recent_avg_days']

    
    # birleştirme (Merge)
    # Genel Özellikler (eski sql sorgusu python ile yapıldı) + Sepet Büyüklüğü
    final_df = pd.merge(user_general, df_basket[['user_id', 'user_avg_basket_size']], on='user_id', how='left')
    
    # Trend Özelliği (Yeni eklenen)
    final_df = pd.merge(final_df, user_recent, on='user_id', how='left')
    # Boş değer varsa (nadiren olur) doldur
    final_df = final_df.fillna(0)
    
    print(f"   --> {len(final_df)} kullanıcı için gelişmiş özellikler çıkarıldı")
    final_df.to_sql('user_features', conn, if_exists='replace', index=False)
    
    conn.close()
    print(f"✅ Tamamlandı! Süre: {time.time() - start_time:.2f} sn")


"""
    Product_FEATURE TABLOSU
    Ürün bazlı özellikleri hesaplar.
    prod_total_orders: Ürün toplam kaç kere satıldı?
    prod_reorder_rate: Ürün ne sıklıkla tekrar sipariş ediliyor?
    prod_avg_position: Ürün ortalama olarak sepetin kaçıncı sırasına ekleniyor? (Popüler ürünler genellikle daha erken eklenir)
    id güncellemeleri ile artık ürünlerin hangi reyonda ve departmanda olduğunu da ekliyoruz (tabloları bağladık)
"""
def create_product_features():
    
    print("Ürün Özellikleri (Product Features) hesaplanıyor")
    start_time = time.time()
    conn = get_db_connection()
    
    # SQL: Sadece prior tablosunu kullanarak ürün istatistiklerini çıkarıyoruz
    query = """
    SELECT 
        op.product_id,         --Ürünlerin ID lerini alır
        MAX(p.aisle_id) as aisle_id, --reyonların id lerini alır
        MAX(p.department_id) as department_id, --ürünlerin ait olduğu departmanların id lerini alır
        -- max ifadelerini hata vermesin diye yazdık yoksa hep saten aynı değeri döndüreceklerdi çünkü ürünler tek bir reyonda ve departmanda olur

        COUNT(*) as prod_total_orders,      --Alınan her ID nin sipariş tablosunda kaç kere geçtiğini sayar
        AVG(reordered) as prod_reorder_rate,         --reordered sütunu 0 (sipariş yok), 1 (sipariş var) şeklindedir. 0 ve 1 lerin ortalamasını alır yani ürünün tekrar sipariş edilme oranını direkt verir
        AVG(add_to_cart_order) as prod_avg_position    -- Bu ürünün ortalama olarak sepetin kaçıncı sırasına eklendiği bilgisi. Genellikle popüler ürünler daha erken eklenir, bu da onların tercih edildiğini gösterebilir. 
    
    FROM order_products__prior op       --Verileri önceden sipariş edilen ürünlerden al
    JOIN products p ON op.product_id = p.product_id -- Ürün detaylarını almak için birleştir
    GROUP BY op.product_id         --Satırları tek tek kontrol et aynı ID olanları yanı aynı ürünleri birleştir
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
    uxp_last_order_number
    uxp_avg_position
"""
def create_uxp_features():
    
    print("Kullanıcı-Ürün İlişkileri (UxP Features) hesaplanıyor")
    start_time = time.time()
    conn = get_db_connection()
    
    # SQL: Hem orders hem order_products tablolarını birleştiriyoruz. Ekler kullanılır.
    query = """
    SELECT 
        o.user_id,      --Order tablosundan kullanıcı idler
        op.product_id,      --order-prod tablosundan ürün idleri
        COUNT(*) as uxp_total_bought,       --Bu kullanıcı bu ürünü toplam kaç kere aldı
        AVG(op.reordered) as uxp_reorder_ratio,      --Bu kullanıcı bu ürünü tekrar alma oranı
        -- v2 güncellemesi ile
        MAX(o.order_number) as uxp_last_order_number, --Bu kullanıcı bu ürünü en son kaçıncı siparişinde aldı
        AVG(op.add_to_cart_order) as uxp_avg_position --Bu kullanıcı bu ürünü ortalama olarak sepetin kaçıncı sırasına ekliyor
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