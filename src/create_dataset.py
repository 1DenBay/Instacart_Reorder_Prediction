import pandas as pd
import sqlite3
import time
from pathlib import Path

"""
Bu dosya; veritabanındaki dağınık istatistikleri alır, geçmiş alışverişlere bakarak bir "Aday Listesi" çıkarır, 
sonra da "Son siparişte bunları aldı mı?" diye kontrol ederek (ayırdığımız test verilerinden kontrolü yapar) yanına 1 veya 0 yazar. Bu ürünler üzerinden kişiye özel çıkarım yapar tüm ürünler ile ilişkilendirmez.
Çıkan sonuç, modelin ders çalışacağı kitaptır. yani gözetimli öğrenme yapıyoruz veriyi ver tahmin etsin sonra kontrol et yanlışlarının üzerinden geçsin
"""

# --- AYARLAR ---
BASE_DIR = Path(__file__).resolve().parent.parent # Proje kök dizini
DB_PATH = BASE_DIR / "data" / "processed" / "instacart.db" # veritabanı yolu
OUTPUT_DIR = BASE_DIR / "data" / "processed" # modele verilecek veri dosyasının çıktı dizini


"""
Veritabanına bağlanır
"""
def get_db_connection():
    return sqlite3.connect(DB_PATH)


"""
    Model eğitimi için gerekli olan 'Master Table'ı oluşturur ve CSV olarak kaydeder.
    Bu tablo şunları içerir:
    - user_id, product_id
    - Tüm featurelar (user, product, uxp)
    - TARGET (reordered): 1 (aldı) veya 0 (almadı) -> tahmine göre 1 veya 0 yazar
"""
def create_train_dataset():

    print("🚂 Eğitim Verisi (Train Dataset) hazırlanıyor...")
    start_time = time.time() # Zaman ölçümü için
    conn = get_db_connection() # Veritabanına bağlan
    
    # --- MODELE VERİLECEK VERİNİN MANTIĞI -> ADAY BELİRLEME (CANDIDATE GENERATION) ---
    # Her kullanıcı için tüm marketteki 50.000 ürünü tahmin etmeye çalışamayız.
    # Sadece kullanıcının "daha önce en az bir kez aldığı" ürünleri (uxp_features tablosundakileri)
    # aday olarak seçiyoruz. Buna "Candidate Generation" denir.
    
    query = """
    SELECT 
        -- Kimlikler
        o.user_id, -- Kullanıcı ID
        uxp.product_id, -- Ürün ID
        
        -- Featurelar (Özellikler - Daha önce hesaplayıp tablolara attığımız istatistikler)
        uxp.uxp_total_bought, -- Kullanıcının bu ürünü kaç kere aldığı
        uxp.uxp_reorder_ratio, -- Kullanıcının bu ürünü tekrar alma oranı
        uf.user_total_orders, -- Kullanıcının toplam sipariş sayısı
        uf.user_avg_days_between, -- Kullanıcının ortalama siparişler arası gün sayısı
        pf.prod_total_orders, -- Ürünün toplam sipariş sayısı
        pf.prod_reorder_rate, -- Ürünün tekrar sipariş edilme oranı
        
        -- Hedef Değişken - Cevap anahtarı (Target Finding -> Bu ürün son siparişte gerçekten alındı mı)
        -- Eğer train setindeki siparişte bu ürün varsa 1, yoksa 0.
        CASE 
            WHEN op_train.reordered = 1 THEN 1  -- Eğer ürün son sepette varsa 1
            ELSE 0  -- Yoksa 0
        END as reordered -- Hedef değişken (Sipariş edildi mi 0(null) yada 1 olarak kaydedecek)
        

    FROM orders o -- Tüm siparişler tablosundan başla
    
    -- 1- Sadece 'train' setindeki kullanıcıları al (Cevabını bildiklerimiz)
    JOIN uxp_features uxp ON o.user_id = uxp.user_id -- Kullanıcı-Ürün özellik tablosu ile eşleştir 
    -- (kim geçmişte neyi almış böylece 50bin üründen 50-100 ürüne düştü kullanıcı başı araştırılması gereken ürün)
    
    -- 2- Özellik Tablolarını Bağla (aslında burada veri kaybını önlemek için LEFT JOIN kullanıyoruz, inner kullansak bazen hesaplanamayan kullanıcılar olduğundan onları yok sayacak)
    LEFT JOIN user_features uf ON o.user_id = uf.user_id
    LEFT JOIN product_features pf ON uxp.product_id = pf.product_id
    
    -- 3- Hedefi Bul (Bu ürün son siparişte var mı?), order_products__train tablosuna bakıyoruz.
    LEFT JOIN order_products__train op_train  -- Sipariş-Ürün tablosu ile eşleştir
        ON o.order_id = op_train.order_id  -- Sipariş ID'leri eşleşmeli
        AND uxp.product_id = op_train.product_id -- Ürün ID'leri eşleşmeli
        
    WHERE o.eval_set = 'train' -- Sadece 'train' setindeki siparişleri al teste dokunma
    """
    
    # Veriyi çek (Chunking kullanmıyoruz, yaklaşık 8-10 milyon satır olabilir
    print("   --> SQL çalıştırılıyor (Bu işlem biraz RAM tüketebilir)...")
    df = pd.read_sql(query, conn)
    
    # Eksik verileri (NaN) doldurma. yukarıda inner yerine Left joinlerden dolayı bazı özellikler boş gelebilir, onları 0 yapıyoruz. null olmasın makine sevmez
    df = df.fillna(0)
    
    print(f"   --> {len(df):,} satırlık veri seti oluşturuldu.")
    
    # CSV'ye kaydet, kaggleda çalıştırıcaz
    output_path = OUTPUT_DIR / "train_data.csv"
    print(f"   --> CSV kaydediliyor: {output_path}")
    df.to_csv(output_path, index=False)
    
    conn.close()
    print(f"✅ Tamamlandı! Süre: {time.time() - start_time:.2f} sn")

if __name__ == "__main__":
    create_train_dataset()