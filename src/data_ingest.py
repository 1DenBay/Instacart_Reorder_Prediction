import pandas as pd
import sqlite3
import os
from pathlib import Path
import time

# --- AYARLAR ---
# Projenin ana dizinini bulur
BASE_DIR = Path(__file__).resolve().parent.parent #bilgisayarda dosya yolu
DATA_RAW = BASE_DIR / "data" / "raw" # ham verilerin bulunduğu klasör
DB_PATH = BASE_DIR / "data" / "processed" / "instacart.db" # SQLite veritabanı dosyası, final yeri

def ingest_data():
    """
    CSV dosyalarını okur ve SQLite veritabanına kaydeder.
    """
    print(f"🚀 Veri aktarımı başlıyor...")
    print(f"📂 Kaynak: {DATA_RAW}")
    print(f"💾 Hedef: {DB_PATH}")
    
    # Veritabanı bağlantısını aç (yoksa oluşturur)
    conn = sqlite3.connect(DB_PATH) # db nin bulunduğu yer
    
    # İşlenecek dosyalar listesi
    files = [
        'aisles.csv',
        'departments.csv',
        'products.csv',
        'orders.csv',
        'order_products__train.csv',
        'order_products__prior.csv' # En büyük dosya sona saklandı
    ]

    start_total = time.time() # Toplam süre ölçümü için başlangıç zamanı

    for file_name in files: # tablo adı için dosyaların uzantıları kaldırır ve aynı isimle tablosunu oluşturur
        file_path = DATA_RAW / file_name
        table_name = file_name.replace('.csv', '') # örn: aisles 
        
        if not file_path.exists():
            print(f"⚠️ UYARI: {file_name} bulunamadı, atlanıyor.")
            continue

        print(f"\n--> ⏳ {file_name} okunuyor ve '{table_name}' tablosuna yazılıyor...")
        
        # ETL -> LOAD kısmı , CSV okuma
        # Not: Gerçek hayatta TB'lık verilerde yada RAM in kaldırmayacağı büyüklüktekilerde 'chunksize' parametresini kullanırız. Bu sayede büyük veriyi parçalar halinde okur ve yazarız.
        # Örnek: pd.read_csv(file_path, chunksize=100000) -> 100.000 satırlık parçalar halinde okur ve işler.
        # veri seti = 550MB ram kaldırdığından böyle bir işleme gerek yok
        start = time.time()
        df = pd.read_csv(file_path)
        
        # SQL'e yazma
        # if_exists='replace': Tablo varsa siler yeniden oluşturur (geliştirme aşamasında pratik)
        # index=False: Pandas indexini veritabanına yazmasın çünkü gereksiz yer kaplıyor
        df.to_sql(table_name, conn, if_exists='replace', index=False)
        
        # start time başlangıçtı bu da bitiş noktası performans ölçümü için
        end = time.time()
        print(f"    ✅ Tamamlandı! {len(df):,} satır eklendi. (Süre: {end-start:.2f} sn)")

    conn.close()
    print(f"\n🎉 TÜM İŞLEMLER BİTTİ! Toplam Süre: {time.time() - start_total:.2f} sn")

 # klasik Python main guard. terminalden direkt bu dosyayı çalıştırırsak direkt çalışsın
 # ama başka dosyaya import ederek çağırıp çalıştırıyorsak beklesin hemen çalışmasın
if __name__ == "__main__":
    ingest_data()