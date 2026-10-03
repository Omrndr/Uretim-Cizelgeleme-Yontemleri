# Kullanım Kılavuzu

## 1. Kurulum ve çalıştırma

### Windows — hazır .exe

[Releases](https://github.com/Omrndr/Uretim-Cizelgeme-Yontemleri/releases) sayfasından `UretimCizelgeleme.exe` dosyasını indirip
çift tıklayın. Kurulum, yönetici izni ya da Python gerekmez. Dosya, deponun
GitHub Actions iş akışı tarafından her sürümde otomatik olarak derlenir
(`.github/workflows/derle.yml`).

### Python ile

Python 3.10 veya üstü yeterlidir. **Ek paket gerekmez**; arayüz Python ile gelen
Tkinter'dır.

```bash
python baslat.py
```

Linux'ta Tkinter ayrı bir pakettir: `sudo apt install python3-tk`.

### Komut satırı

```bash
python -m motor                                    # örnek senaryo → metin raporu
python -m motor senaryo.json --paket Ciktilar      # + PDF çıktı paketi
python -m motor senaryo.json --fabrika fab.json    # başka bir fabrika tanımı
python -m motor --duzenler                         # bütün çalışma düzenlerini karşılaştır
```

### Kendi .exe dosyanızı üretmek

```bash
pip install pyinstaller
python paketle.py            # → dist/UretimCizelgeleme.exe (~15 MB)
```

## 2. Arayüz

| Sekme | İçerik |
|---|---|
| **Girdiler** | Plan başlangıcı, varsayılan çalışma düzeni, ayar süreleri; sipariş, ek mesai ve personel tabloları; hesaplamadan önce girdi denetimi |
| **Uyarılar** | Pano A (yasal durum), Pano B (hat yeterliliği ve günlük açık), genel uyarılar |
| **Özet** | Temel göstergeler, sipariş durumu, personel tahsisi, parti araması tablosu |
| **Günlük şema** | Atölye × gün, saat ölçekli (A4) |
| **Haftalık şema** | Atölye × hafta (A3) |
| **Genel bakış** | Termin çizelgesi ve hafta × atölye kullanım ısı haritası |
| **İş emirleri** | Zaman · kaynak · personel · iş emri satırları; atölye, personel ve siparişe göre süzme; CSV |
| **Personel ve defter** | Bu plandaki personel yükü; yıllık fazla çalışma defteri (işle, sıfırla, ad değişikliğinde bakiye taşı) |
| **Tablolar** | Kaynak kullanımı, makine dengeleme, günlük çıkış, ayar listesi, kısıt analizi ve diğerleri; bütün tablolar XLSX |
| **Çıktı** | Yazıcıya hazır paket (PDF/HTML + XLSX + CSV) |

**Döngü:** girdileri düzenle → **HESAPLA** (F5) → uyarıları oku → gerekirse ek mesai
talimatı ekle → yeniden hesapla → şemaları incele → **Çıktı paketi**.

Hesap arka planda çalışır; pencere donmaz ve **İptal** ile durdurulabilir.

### Ek mesai talimatı

Talimat **tek bir kaynağa** (ör. `M1.2`, `TORNA-3`, `KABİN-1`) verilir. Belirtilen
tarih aralığında yalnız o kaynak uzun çalışır.

| Alan | Anlamı |
|---|---|
| Ek saat/gün | Seçilen düzenin üstüne eklenen net çalışma (0 olabilir) |
| Düzen | Talimatın üzerine kurulduğu çalışma düzeni (ör. D2 · Uzun gün) |
| Hafta sonu | Evet ise hafta sonu günlerinde de yalnızca ek saat kadar çalışılır |

Bir kaynak-günü 11 saati aşarsa gün iki vardiyaya bölünür ve ikinci vardiyaya
**ayrı bir personel** atanır. Uygun personel kalmazsa vardiya "atanamayan" olarak
raporlanır.

**Öneri düğmesi:** Ek mesai sekmesindeki *darboğaz takibi* hangi kaynakların
uzatılması gerektiğini önerir ve satırları tabloya ekler. Bu yalnızca bir öneridir;
satırları dilediğiniz gibi değiştirebilirsiniz.

## 3. Senaryo dosyası

```json
{
  "baslangic": "2026-11-02",
  "siparisler": [
    {"kod": "S-101", "miktarlar": {"Antrasit": 1500, "Krem": 700}, "termin": "2026-11-27"}
  ],
  "ek_mesailer": [
    {"kaynak": "M1.2", "baslangic": "2026-11-09", "bitis": "2026-11-20",
     "ek_saat": 2, "duzen": "D1", "hafta_sonu": false, "aktif": true}
  ],
  "personel": ["P01", "P02", "P03"],
  "ayarlar": {
    "parti_sayilari": [1, 2, 3, 4],
    "ramp_adaylari": [1.0, 2.0],
    "ayar_saatleri": {"CNC": 1.5, "BOYA": 3.0},
    "ayari_gun_basina_hizala": false,
    "serpantin_sira": true,
    "azami_ayar_payi": 0.25,
    "personel_denetimi": true,
    "varsayilan_duzen": "D1"
  }
}
```

`personel` boş bırakılırsa fabrika tanımındaki sayı kadar `P01, P02, …` üretilir.

## 4. Çıktı paketi

```
Ciktilar/Plan_2026-11-02 (olusturma …)/
  BENIOKU.txt
  00_Genel_Bakis.pdf          termin çizelgesi + ısı haritası
  01_Plan_Raporu.txt          kapasite, dengeleme, parti araması, panolar
  02_Plan_Tablolari.xlsx      15 sayfa
  03_Is_Emirleri.csv
  Hafta 01 (02.11-08.11)/
    CNC Torna Atolyesi/
      _Haftalik_Plan.pdf      A3 yatay — panoya
      Gun_2026-11-02_Pzt.pdf  A4 yatay — vardiya başında
  Personel Kartlari/P01.pdf
```

- PDF'ler bilgisayardaki Edge, Chrome ya da Chromium ile "headless" kipte üretilir.
- Tarayıcı bulunamazsa dosyalar HTML olarak kalır; tarayıcıda açıp Ctrl+P ile aynı düzende yazdırılabilir.
- Tarayıcının yerini `CIZELGE_TARAYICI` ortam değişkeniyle belirtebilirsiniz.

## 5. Kendi fabrikanızı tanımlamak

Motor hiçbir fabrikayı "bilmez"; bütün yapı JSON dosyasından gelir.
`veri/ornek_fabrika.json` dosyasını kopyalayıp düzenleyin, ardından
**Dosya → Fabrika tanımı aç** ile yükleyin.

| Bölüm | Alanlar |
|---|---|
| `varyantlar` | Ürün varyantları (renk, kaplama, model…) |
| `parca_gruplari[]` | `kod`, `ad`, `kaynak_oneki`, `makine_sayisi`, `ayar_saat`, `ayar_etiketi`, `parcalar{kod: {ad, sure_sn}}` — her parçanın tek aparatı vardır |
| `varyant_grubu` | `makine_sayisi`, `sure_sn`, `ayar_saat`, `bilesen`, `takim_adi`, `takim_adedi{varyant: adet}` |
| `hucreler.liste[]` | `kod`, `ad`, `girdiler` (parça kodları), `sure_sn`, `azami_istasyon` |
| `hat.istasyonlar[]` | Sıralı istasyonlar; `girdiler` parça, hücre kodu ya da `"VARYANT"` olabilir |
| `personel_sayisi` | Varsayılan kadro |
| `takvim` | `vardiya_baslangic`, `molalar`, `gun_molalari{haftanın_günü: [...]}`, `araliksiz_azami_saat`, `zorunlu_mola_saat`, `duzenler[]{kod, ad, brut_bitis, gun}`, `varsayilan_duzen` |
| `mevzuat` | `gunluk_azami_saat`, `haftalik_normal_saat`, `haftalik_azami_saat`, `yillik_fazla_calisma_tavani` |

Saatler `"HH:MM"` biçimindedir. Gece yarısını aşan bitişler `"02:00+1"` biçiminde
yazılır. Dosya yüklenirken doğrulanır: tanımsız bir girdi, tüketilmeyen bir varyant
grubu ya da takımı olmayan bir varyant açık bir hata mesajı üretir.

## 6. Fazla çalışma defteri

Yıllık 270 saatlik fazla çalışma tavanı takvim yılı boyunca birikir. Onaylanan bir
planın fazla çalışmasını **Personel ve defter → Planı deftere işle** ile kaydedin;
sonraki planlar açılış bakiyesini buradan okur.

- Veritabanı Windows'ta `%APPDATA%\UretimCizelgeleme\fazla_mesai_defteri.db`, Linux'ta `~/.local/share/UretimCizelgeleme/` altında durur.
- Bir personelin adını değiştirirseniz bakiyesini **Bakiye taşı** ile yeni adına aktarın. Girdi denetimi, defterde bakiyesi olup kadroda bulunmayan adları uyarır.

## 7. Testler

```bash
python -m unittest discover -s testler -v
```
