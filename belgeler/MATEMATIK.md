# Matematiksel Model ve Yöntemler

Bu belge, motorun kullandığı endüstri mühendisliği ve yöneylem araştırması
yöntemlerini formülleriyle anlatır. Her bölümün sonunda yöntemin koddaki yeri
verilmiştir. Sayısal örnekler `veri/ornek_fabrika.json` içindeki **hayali**
atölyeden alınmıştır.

**Problem sınıfı:** Paralel makineli, sıradan bağımsız ayar süreli, takım
(aparat) kısıtlı, kaynak takvimli ve termin tarihli **hibrit akış tipi üretim**
(hybrid flow shop). Buna yasal çalışma süresi sınırlarıyla **personel
çizelgeleme** (rostering) eklenir.

İçindekiler

1. [Notasyon](#1-notasyon)
2. [Kapasite, çevrim süresi ve darboğaz](#2-kapasite-çevrim-süresi-ve-darboğaz)
3. [Paralel makinelerde yük dengeleme — P‖Cmax](#3-paralel-makinelerde-yük-dengeleme--pcmax)
4. [Personel tahsisi — min-maks problemi](#4-personel-tahsisi--min-maks-problemi)
5. [Kaynak takvimi ve zaman dönüşümü](#5-kaynak-takvimi-ve-zaman-dönüşümü)
6. [Parti (kampanya) planı](#6-parti-kampanya-planı)
7. [Takım kısıtlı varyant planı](#7-takım-kısıtlı-varyant-planı)
8. [Üretim sırası — EDD ve heijunka](#8-üretim-sırası--edd-ve-heijunka)
9. [Akış hesabı — ileri özyineleme](#9-akış-hesabı--ileri-özyineleme)
10. [Amaç hiyerarşisi ve arama](#10-amaç-hiyerarşisi-ve-arama)
11. [Personel çizelgeleme — yasal sınırlar](#11-personel-çizelgeleme--yasal-sınırlar)
12. [Ek mesai önerisi — darboğaz takibi](#12-ek-mesai-önerisi--darboğaz-takibi)
13. [Hat yeterliliği — analitik açık](#13-hat-yeterliliği--analitik-açık)
14. [Performans ölçütleri](#14-performans-ölçütleri)
15. [Kaynakça](#15-kaynakça)

---

## 1. Notasyon

| Simge | Anlam |
|---|---|
| $N$ | toplam ürün adedi (bütün siparişler) |
| $i = 1..N$ | üretim sırasındaki ürün indeksi |
| $u \in U$ | tahsis birimi (makine grubu, hücre ya da hat istasyonu) |
| $w_u$ | birime verilen personel = paralel kaynak sayısı |
| $\tau_u$ | birimin ürün başına işlem süresi (sn) |
| $f_u(w)$ | $w$ kaynakla birimin çevrim süresi (sn/adet) |
| $t_p$ | parça $p$'nin makine işlem süresi (sn/adet) |
| $m$ | paralel makine sayısı |
| $S$ | ayar (aparat ya da renk değişimi) süresi |
| $K,\ r$ | parti sayısı ve rampa katsayısı |
| $d_v,\ T_v$ | varyant $v$'nin talebi ve takım adedi |
| $g_k(t)$ | kaynak $k$'nin $t$ anına kadar birikmiş çalışma süresi |
| $R_j(i),\ S_j(i),\ F_j(i)$ | ürün $i$'nin operasyon $j$'ye hazır olma, başlama ve bitiş anı |
| $H_{gün}, H_{hafta}, H_{yıl}$ | günlük, haftalık ve yıllık fazla çalışma sınırları |

---

## 2. Kapasite, çevrim süresi ve darboğaz

*Kaynak: Hopp & Spearman (2011); Pinedo (2016).*

Seri bağlı birimlerden oluşan bir hatta kararlı durumdaki çıktı hızını en yavaş
birim belirler. Birim $u$'nun çevrim süresi, işlem süresinin paralel kaynak
sayısına bölümüdür:

$$
f_u(w_u) = \frac{\tau_u}{w_u}, \qquad
C(\mathbf{w}) = \max_{u \in U} f_u(w_u), \qquad
\text{kapasite} = \frac{3600}{C}\ \ \text{adet/saat}.
$$

$C$'yi veren birim **darboğazdır**. Hattın tamamlanma süresi için kaba alt sınır
$N \cdot C$'dir. Ayar kayıpları, hattın dolma süresi ve takvim boşlukları bu sınırın
üstüne eklenir.

**Yapısal alt sınır.** Personel sınırsız olsa bile her birim en fazla $\bar w_u$ kaynağa
çıkabilir. Bu durumda aşılamayan çevrim süresi şudur:

$$
C_{taban} = \max_{u} \min_{1 \le w \le \bar w_u} f_u(w).
$$

Örnek atölyede $C_{taban} = 78$ sn/adet ve bu değeri CNC grubu verir. Bundan sonra
personel eklemek kapasiteyi artırmaz. Araç bu durumu uyarı olarak raporlar.

> Kod: `motor/tahsis.py` → `yapisal_alt_sinir`, `Tahsis.kapasite_saat`

---

## 3. Paralel makinelerde yük dengeleme — P‖Cmax

Bir makine grubunda $m$ özdeş makine ve aparatı tek olan $n$ parça vardır.
Aparat tek olduğu için bir parça bölünemez ve tümüyle tek bir makineye atanır.
Her ürün her parçadan birer adet gerektirir. Makine $k$'nin ürün başına yükü ve
grubun çevrim süresi:

$$
L_k = \sum_{p \in P_k} t_p, \qquad f(m) = C_{max} = \max_k L_k .
$$

**Tam sayılı model.** $x_{pk} = 1$, parça $p$ makine $k$'ye atanmışsa:

$$
\min\ C \quad \text{öyle ki} \quad
\sum_k x_{pk} = 1\ \ \forall p, \qquad
\sum_p t_p\, x_{pk} \le C\ \ \forall k, \qquad x_{pk} \in \{0,1\}.
$$

Problem güçlü anlamda NP-zordur; $m = 2$ için bile PARTITION'a indirgenir.

*Kaynak: Graham (1969); Pinedo (2016, böl. 5).*

**Alt sınır:**
$$C^* \ge \max\!\left(\frac{\sum_p t_p}{m},\ \max_p t_p\right).$$

**LPT (Longest Processing Time).** Parçalar sürelerine göre azalan sırada, o anda
en az yüklü makineye atanır. Bir ikili yığın kullanıldığında karmaşıklık
$O(n \log n + n \log m)$ olur. Graham'ın (1969) en kötü durum garantisi:

$$
\frac{C_{LPT}}{C^*} \le \frac{4}{3} - \frac{1}{3m}.
$$

**Yerel arama (en dik iniş).** En yüklü makine $a$ için iki hamle türü denenir:

- *taşıma:* $p \in P_a$ başka bir makine $b$'ye geçer → yeni çift maksimumu $\max(L_a - t_p,\ L_b + t_p)$,
- *takas:* $p \in P_a$ ile $q \in P_b$ yer değiştirir ($t_p > t_q$) → yeni çift maksimumu $\max(L_a - \delta,\ L_b + \delta)$, burada $\delta = t_p - t_q$.

Yeni çift maksimumunu en çok düşüren hamle uygulanır. Bir hamle yalnızca bu
değer mevcut $C_{max}$'tan **kesin küçükse** kabul edilir.

*Sonlanma:* Kabul edilen her hamlede iki makine arasında $\delta > 0$ kadar yük,
büyük olandan küçük olana geçer ve iki yükün ikisi de eski büyük değerin altında
kalır. Bu durumda $\sum_k L_k^2$ kesin olarak azalır. Atama sayısı sonlu olduğundan
arama sonlu adımda durur.

Testlerde 30 rastgele örnekte (7 parça, 3 makine) kaba kuvvet optimumuyla
karşılaştırılır. Sonuç en az 24 örnekte optimumdur, bütün örneklerde de Graham
sınırının içindedir.

> Kod: `motor/dengeleme.py` → `dengele`, `alt_sinir` · Test: `testler/test_yontemler.py::DengelemeTesti`

---

## 4. Personel tahsisi — min-maks problemi

Her makine ve her istasyon tam bir personel gerektirir. $N_p$ kişilik kadro
birimlere dağıtılır:

$$
\min_{\mathbf{w}}\ \max_{u \in U} f_u(w_u)
\quad \text{öyle ki} \quad
\sum_u w_u \le N_p, \qquad 1 \le w_u \le \bar w_u, \qquad w_u \in \mathbb{Z}.
$$

Birimlerin yanıt fonksiyonları:

| Birim | $f_u(w)$ | Üst sınır $\bar w_u$ |
|---|---|---|
| Parça makine grubu | $C_{max}$ (P‖Cmax, $w$ makine) | makine sayısı |
| Varyant grubu | $\tau / w$ | $\min\!\left(m,\ \sum_{v:\,d_v>0} T_v\right)$ |
| Hücre / hat istasyonu | $\tau / w$ | azami istasyon |

*Kaynak: min-maks (darboğaz) kaynak tahsisi için bkz. Ibaraki & Katoh (1988).*

**Kesin çözüm: aday çevrim taraması.** Optimal değer $C^*$ mutlaka
$\mathcal{A} = \{ f_u(k) : u \in U,\ 1 \le k \le \bar w_u \}$ kümesinin bir
elemanıdır. Adaylar küçükten büyüğe taranır. Her aday $c$ için birimlerin asgari
ihtiyacı hesaplanır:

$$
n_u(c) = \min\{\, k : f_u(k) \le c \,\}.
$$

$\sum_u n_u(c) \le N_p$ koşulunu sağlayan **ilk** $c$ optimaldir.

*Kanıt.* Çevrimi $c$'yi aşmayan herhangi bir tahsiste her $u$ için
$f_u(w_u) \le c$ olmalıdır. Tanım gereği bu $w_u \ge n_u(c)$ demektir; dolayısıyla
$\sum_u w_u \ge \sum_u n_u(c)$. $\sum_u n_u(c) > N_p$ ise $c$ ulaşılamazdır.
Toplamı sağlayan ilk aday için $n_u(c)$ vektörünün kendisi geçerli bir tahsistir
ve aynı $c$'ye ulaşan tahsisler içinde en az personeli kullanır. ∎

Tam sayım $\prod_u \bar w_u$ kombinasyon dener. Tarama ise
$O(|\mathcal{A}| \cdot |U| \cdot \max \bar w)$ adımda biter. Ayrıca $f_u$'nun
monoton olması gerekmez; LPT sezgiseli $m$ arttıkça her zaman iyileşmeyebilir ve
yöntem bu durumda da doğru çalışır.

**Artık personel.** Optimum çoğu zaman bütün kadroyu kullanmaz. Artan personel
önce makine gruplarına verilir: paralel makine arttıkça parti ve ayar yükü
bölüşülür. Kalanlar her adımda çevrimi en yüksek birime verilir; böylece darboğaz
dışındaki birimlerde emniyet payı oluşur.

Örnek atölyede 18 kişiyle $C^* = 96$ sn/adet (darboğaz H2), 20 kişiyle 78 sn/adet
(yapısal alt sınır) elde edilir.

> Kod: `motor/tahsis.py` → `min_max_tahsis`, `en_iyi_dagilim` · Test: kaba kuvvetle eşitlik (`TahsisTesti`)

---

## 5. Kaynak takvimi ve zaman dönüşümü

Bütün zamanlar plan başlangıç gününün 00:00'ından itibaren **mutlak saniye**
cinsindendir. Her kaynağın kendine ait bir takvimi vardır, çünkü ek mesai tek bir
kaynağa verilebilir. Bir kaynağın takvimi ayrık çalışma aralıklarının birleşimidir:

$$
W_k = \bigcup_{j} [a_j, b_j), \qquad K_j = \sum_{l<j} (b_l - a_l).
$$

**Birikimli çalışma** ve **tersi** şöyle tanımlanır ($K_j < w \le K_{j+1}$ için):

$$
g(t) = K_j + \big(\min(t, b_j) - a_j\big), \quad j = \max\{l : a_l \le t\},
\qquad
g^{-1}(w) = a_j + (w - K_j).
$$

$t$ anında başlayan ve $d$ saniye çalışma gerektiren işin bitişi artık $t + d$
değildir:

$$
\text{ilerlet}(t, d) = g^{-1}\big(g(t) + d\big).
$$

İki dönüşüm de ikili aramayla $O(\log n)$ sürede hesaplanır. Bu soyutlama sayesinde
geceler, hafta sonları, molalar ve tek kaynağa verilen ek mesai algoritmaların
geri kalanına görünmez olur.

**Günün blokları.** Üretim günü vardiya başlangıcında başlar ve 24 saat sürer;
gece yarısından sonraki mesai bir önceki üretim gününe aittir. Hedef net süre
$h$, vardiya başından itibaren yerleştirilir. Araya iki tür mola girer:

1. sabit molalar (çay ve öğle),
2. **zorunlu mola:** son moladan beri kesintisiz çalışma $A$ saati aşarsa
   $\Delta$ uzunluğunda mola eklenir.

Molalar çalışma süresi değildir; gün, net $h$'ye ulaşana kadar uzar. Örnek
atölyede $A = 5$ sa ve $\Delta = 0{,}5$ sa'dir. *Gündüz* düzeninde net süre
8,5 sa/gün olur; bir üretim gününde çalışılabilecek azami net süre 21,25 saattir.

**Çalışma düzenleri.** Vardiya başı ve molalar sabittir; düzen yalnızca brüt
bitişi ve haftadaki iş günü sayısını değiştirir (D1 gündüz, D2 uzun gün, D3
haftada 6 gün, D4 çift vardiya). Aynı kaynak ve gün için birden çok ek mesai
talimatı varsa brüt bitişi en geç olan düzen geçerli olur, ek saatler toplanır.

> Kod: `motor/takvim.py` → `KaynakTakvimi`, `gunun_dilimleri`, `FabrikaTakvimi`

---

## 6. Parti (kampanya) planı

Bir makinede birden çok parça varsa her parça değişimi $S$ süren bir ayar
gerektirir. $N$ ürünlük talep $K$ partiye bölünür. Her partide makine, partinin
adedi kadar kendi parçalarını sırayla üretir.

**Ödünleşim.**

- Ayar sayısı yaklaşık $K \cdot |P_k|$ olduğundan $K$ arttıkça artar.
- Hattın ilk ürünü alabilmesi için her parçanın en az bir partisinin bitmiş olması gerekir. İlk partinin uzunluğu yaklaşık $q_1 \cdot L_k$'dir; $K$ arttıkça hat daha erken beslenir.

Hangi değerin uygun olduğunu termin belirler (bkz. § 10).

*Kaynak (Hamilton yuvarlaması): Balinski & Young (1982).*

**Geometrik rampa.** Parti büyüklükleri ilk partiyi küçük tutacak şekilde dağıtılır:

$$
q_j^{ideal} = N \cdot \frac{r^{\,j}}{\sum_{l=0}^{K-1} r^{\,l}}, \qquad j = 0..K-1, \qquad r \ge 1.
$$

Tam sayıya yuvarlamada **en büyük kalan (Hamilton) yöntemi** kullanılır:
$q_j = \max(1, \lfloor q_j^{ideal} \rfloor)$ alınır, kalan adetler kesirli kısmı en
büyük partilerden başlanarak dağıtılır. Toplam korunur ve
$|q_j - q_j^{ideal}| < 1$ olur.

**Yılan (serpantin) sıra.** Ardışık partilerde parça sırası ters çevrilir:
$(A,B,C \mid C,B,A \mid A,B,C \dots)$. Bir partinin son parçası bir sonrakinin ilk
parçası olduğu için parti geçişinde ayar gerekmez. Böylece makine başına
$K - 1$ ayar kazanılır. Bu, sıradan bağımsız ayarlarda maliyetsiz bir iyileştirmedir.

**Sipariş atfı.** $j$. parti, üretim sırasındaki
$\left[\sum_{l<j} q_l,\ \sum_{l \le j} q_l\right)$ aralığındaki ürünlere birer
parça üretir. İş emirlerindeki sipariş sütunu buradan türetilir.

> Kod: `motor/parti.py` → `parti_buyuklukleri`, `parca_partileri`, `ParcaZamanlari`

---

## 7. Takım kısıtlı varyant planı

Varyantı (örnekte rengi) belirleyen bileşen $m$ paralel makinede üretilir. Varyant
$v$ için aynı anda en fazla $T_v$ makine çalışabilir; bu sınırı takım adedi koyar.

*Kaynak (D'Hondt/Jefferson bölenleri): Balinski & Young (1982).*

**1) Başlangıç payları — akışkan gevşetme.** Makineler sürekli bölünebilseydi her
varyanta talebi oranında pay düşerdi:

$$
s_v = m \cdot \frac{d_v}{\sum_l d_l}, \qquad n_v = \operatorname{clamp}\big(\lfloor s_v \rfloor,\ 1,\ T_v\big).
$$

- $\sum n_v > m$ ise, sıraya **en geç ihtiyaç duyulan** varyanttan eksiltilir.
- $\sum n_v < m$ ise kalan makineler, takım sınırı içinde, $d_v / (n_v + 1)$ oranı en büyük varyanta verilir (**D'Hondt / Jefferson** bölen yöntemi).

**2) Olay güdümlü benzetim.** Makineler, müsait olma anına göre bir öncelik
kuyruğunda tutulur. Her olayda makine ya bir adet daha üretir ya da varyant değiştirir:

- *Talep bitti:* takımı boşta olan varyantlar içinde, bir sonraki adedi hatta
  **en erken** gereken varyanta geçilir. İhtiyaç anı, o adedin üretim sırasındaki
  konumudur.
- *Amortisman kesmesi:* Hiç makinesi olmayan ("aç") bir varyant varsa ve iki koşul
  birlikte sağlanıyorsa seri kesilir ve aç varyanta geçilir:

$$
\text{seri} \ \ge\ q_{min}
\qquad \text{ve} \qquad \text{ihtiyaç}(v_{aç}) < \text{ihtiyaç}(v_{mevcut}).
$$

İkinci koşul, hattın aç varyantı mevcut varyanttan önce isteyeceğini söyler; varyant
sayısı makine sayısından fazla olduğunda makinenin iki varyant arasında gereksiz yere
gidip gelmesini önler.

**Asgari seri — ayar payı sınırı.** İlk koşul, ayarın makine zamanındaki payını
$\alpha$ ile sınırlar. $q$ adetlik bir seride bu pay şöyledir:

$$
\frac{S}{S + q\,\tau} \le \alpha
\iff
q \ge \frac{S\,(1-\alpha)}{\alpha\,\tau}
\qquad\Rightarrow\qquad
q_{min} = \left\lceil \frac{S\,(1-\alpha)}{\alpha\,\tau} \right\rceil .
$$

$\alpha = 0{,}5$ başa baş noktasıdır ($q_{min} = \lceil S/\tau \rceil$): ayar süresi
kadar üretim yapılmış ve ayar kendini amorti etmiştir. Örnek atölyede $S = 3$ sa ve
$\tau = 150$ sn için $\alpha = 0{,}5 \Rightarrow q_{min} = 72$, varsayılan
$\alpha = 0{,}25 \Rightarrow q_{min} = 216$ olur. Bu değişiklik renk değişimi
sayısını 24'ten 14'e indirir; terminler ve tamamlanma süresi değişmez.

**Sipariş atfı.** Varyant $v$'nin $j$. bitirilen bileşeni, sırada $v$ varyantlı
$j$. ürünü besler.

> Kod: `motor/varyant.py` → `varyant_paylari`, `varyant_plani`

---

## 8. Üretim sırası — EDD ve heijunka

*Kaynak: Jackson (1955); Monden (1983).*

**Siparişler arası — EDD.** Siparişler termin tarihine göre sıralanır. Tek makinede
en büyük gecikmeyi ($L_{max}$) en aza indiren kural budur (Jackson, 1955). Akış
tipi hatta da güçlü bir sezgiseldir.

**Sipariş içi — hedef kovalama (goal chasing).** Varyantlar bloklar hâlinde değil,
oranları korunarak karıştırılır. $k$. adımda, ideal birikimli üretimin en çok
gerisinde kalan varyant seçilir:

$$
v_k = \arg\max_v \left( d_v \cdot \frac{k}{D} - x_v(k-1) \right), \qquad D = \sum_v d_v .
$$

Burada $x_v$, o ana kadar sıraya giren $v$ adedidir. Sonuç olarak her önekte
$\left|x_v(k) - d_v k / D\right| < 1$ olur ve varyant bileşeni hattı düzgün bir
hızla tüketir.

> Kod: `motor/siralama.py` · Test: oran sapması < 1 (`PartiVeSiraTesti`)

---

## 9. Akış hesabı — ileri özyineleme

Ürünler sırayla işlenir. Operasyon $j$'nin $c_j$ paralel istasyonu vardır. Ürün
$i$'nin $j$'ye hazır olma anı, tükettiği bütün girdilerin en geç bitişidir:

$$
R_j(i) = \max\Big( F_{j-1}(i),\ \max_{p \in \text{parça}_j} P_p(i),\ \max_{h \in \text{hücre}_j} F_h(i),\ V_{v(i)}(\kappa_i) \Big).
$$

- $P_p(i)$: parça $p$'nin $i$. adedinin bitişi (§ 6). İkili aramayla $O(\log K)$ sürede bulunur.
- $V_v(\kappa)$: varyant $v$'nin $\kappa$. bileşeninin bitişi (§ 7). $\kappa_i$, sırada $i$'ye kadar gelen $v$ varyantlı ürün sayısıdır.

**Liste çizelgeleme.** Ürün, en erken **bitirecek** istasyona verilir ($A_s$:
istasyonun müsait olduğu an):

$$
s^* = \arg\min_s\ \text{ilerlet}_s\big(\max(R_j(i), A_s),\ \tau_j\big),
\qquad
F_j(i) = \text{ilerlet}_{s^*}\big(S_j(i),\ \tau_j\big).
$$

Bütün istasyonların takvimi özdeşse bu, bilinen kapalı biçime indirgenir:

$$
S_j(i) = \max\big( R_j(i),\ F_j(i - c_j) \big), \qquad F_j(i) = S_j(i) \oplus \tau_j .
$$

Burada $\oplus$, takvim üzerinde ilerletmedir. Takvimler farklıysa (tek istasyona
ek mesai verildiyse) genel kural kullanılır. Karmaşıklık
$O\big(N \cdot \sum_j c_j \cdot \log |W|\big)$'dir.

**Kısıt analizi.** Her ürün ve istasyon için gecikmeye hangi girdinin yol açtığı
sayılır. İstasyon boştayken girdi bekleniyorsa bu **aç kalma süresi**, çalışma
saniyesi olarak $g(R) - g(A)$ ile ölçülür ve o girdiye yazılır.

> Kod: `motor/akis.py` → `akisi_coz`

---

## 10. Amaç hiyerarşisi ve arama

Çözüm, aşağıdaki **leksikografik** amaçla karşılaştırılır:

$$
\text{lex-min}\ \Big(\ \underbrace{\mathbb{1}[\exists\ \text{gecikme}]}_{1)\ \text{termin}},\ \
\underbrace{\begin{cases}\#\text{ayar} & \text{termine yetişiyorsa}\\ L_{max} & \text{aksi hâlde}\end{cases}}_{2)},\ \
\underbrace{C_{son}}_{3)\ \text{tamamlanma}}\ \Big).
$$

Karar değişkenleri $(K, r)$ küçük bir ızgaradır, örneğin
$K \in \{1,2,3,4\}$ ve $r \in \{1, 2\}$. Varyant planı $K$'dan bağımsız olduğu
için bir kez hesaplanır. Her aday için parti planı ve akış hesabı yeniden yapılır.

Örnek senaryonun arama tablosu ödünleşimi açıkça gösterir:

| K | r | ayar | tamamlanma (gün) | en büyük gecikme (gün) | termin |
|---|---|---|---|---|---|
| **1** | 1 | **26** | 39,5 | −0,4 | **EVET ← seçilen** |
| 2 | 2 | 34 | 29,6 | −10,2 | EVET |
| 4 | 1 | 50 | 28,6 | −11,3 | EVET |

Ek mesai **yalnızca planlamacının talimatıyla** eklenir. Termine yetişmiyorsa en küçük
gecikmeli planı gösterir, hangi hattın ne kadar yetersiz kaldığını raporlar (§ 13)
ve ek mesai kararını planlamacıya bırakır.

> Kod: `motor/cozucu.py` → `plan_olustur`

---

## 11. Personel çizelgeleme — yasal sınırlar

*Kaynak: Ernst ve ark. (2004).*

Girdi, her (kaynak $k$, üretim günü $g$) için fiilen çalışılacak net süre
$h_{kg}$'dir. Bu süre, meşgul aralıkların takvim pencereleriyle kesişiminden
hesaplanır.

**Model.** $y_{ekg} = 1$, personel $e$ o gün $k$'ye atanmışsa:

$$
\begin{aligned}
&\textstyle\sum_e y_{ekg} = 1 && \forall k, g \quad \text{(her kaynak-gün bir kişi)}\\
&\textstyle\sum_k y_{ekg} \le 1 && \forall e, g \quad \text{(kişi başına günde tek vardiya)}\\
&\textstyle\sum_k h_{kg}\, y_{ekg} \le H_{gün} = 11 && \text{(4857 s. İş K. m.63)}\\
&\textstyle\sum_{g \in w} \sum_k h_{kg}\, y_{ekg} \le H_{hafta} && \text{(işletme politikası)}\\
&\textstyle B_e + \sum_w \max\!\big(0,\ \sum_{g\in w}\sum_k h_{kg}y_{ekg} - 45\big) \le H_{yıl} = 270 && \text{(m.41)}
\end{aligned}
$$

Burada $B_e$, personelin yıl içinde önceki planlardan biriken fazla çalışmasıdır
(kalıcı defterden okunur).

**Bölme.** $h_{kg} > H_{gün}$ ise gün $n = \lceil h / H_{gün} \rceil$ eşit vardiyaya
bölünür ve her vardiyaya ayrı bir personel atanır.

**Açgözlü sezgisel.** Model bir tam sayılı programdır ve gün gün ilerleyen açgözlü
bir yöntemle çözülür. Vardiyalar süresi büyükten küçüğe atanır. Üç sınırı da
sağlayan adaylar şu sırayla seçilir:

1. **marjinal fazla çalışma** doğurmayanlar önce:
   $\Delta FM = \max(0, H_w + h - 45) - \max(0, H_w - 45)$
2. süreklilik: dün aynı kaynakta çalışan,
3. bu hafta en az çalışmış olan, ardından yıllık fazla çalışması en düşük olan.

Uygun aday kalmazsa vardiya **atanamayan** olarak raporlanır. Plan değiştirilmez;
böylece ustabaşı kaynağın neden boş kalacağını görür.

Zorunlu molalar çalışma süresi değildir. Ancak uzun günde ortaya çıktıkları için
(seçenek açıksa) personelin fazla çalışmasına eklenir.

> Kod: `motor/personel.py` → `personel_ata` · `motor/defter.py` (SQLite) · Test: `PersonelTesti`

---

## 12. Ek mesai önerisi — darboğaz takibi

Soru: "Bu atölyede $a$ kaynağı günde $E$ saat uzatacaksam hangilerini seçmeliyim?"
Her grubun günlük kapasitesi şöyledir:

$$
\kappa_g = \frac{(c_g H + s_g E) \cdot 3600}{\tau_g} \quad [\text{adet/gün}].
$$

- $c_g$: gruptaki kaynak sayısı,
- $s_g$: gruptan şimdiye kadar seçilen kaynak sayısı,
- $H$: taban günlük net süre.

Her adımda $\kappa_g$'si en küçük gruptan bir kaynak seçilir ve kapasiteler yeniden
hesaplanır. Böylece hep aynı grubu uzatıp darboğazı bir sonraki gruba kaydırma
hatası önlenir. Parça makinelerinde her makine ayrı bir gruptur ($\tau_g = L_k$),
çünkü parçaları başka bir makinede işlenemez.

> Kod: `motor/cozucu.py` → `ek_mesai_onerisi`

---

## 13. Hat yeterliliği — analitik açık

Her grup için yeniden planlama yapmadan **günlük gereken çalışma** hesaplanır:

$$
h^{gerekli}_g = \frac{N' \cdot \tau_g}{c_g \cdot 3600 \cdot D}, \qquad
\text{açık}_g = h^{gerekli}_g - h^{mevcut}_g .
$$

- $N'$: incelenen siparişe kadar (EDD sırasında önündekiler dahil) üretilmesi gereken adet,
- $D$: plan başı ile termin arasındaki iş günü sayısı,
- $h^{mevcut}_g$: grubun ortalama günlük net çalışması.

Açığı en büyük grup **kritik hattır**. Açık $\le 0$ olduğu hâlde sipariş gecikiyorsa
kararlı durum kapasitesi yeterlidir. Gecikme geçici etkilerden kaynaklanır: ayar
kayıpları, hattın dolma süresi ya da sıra bekleme. Bu durumda doğru müdahale ek
mesai değil, parti sayısını değiştirmektir.

> Kod: `motor/uyarilar.py` → `grup_aciklari`, `geciken_siparisler`

---

## 14. Performans ölçütleri

**Kullanım oranı** çalışma süresiyle ölçülür. Geceler ve molalar "boş" sayılmaz:

$$
\rho_k = \frac{\sum_{[a,b) \in \text{meşgul}_k} \big(g_k(b) - g_k(a)\big)}{g_k(C_{son})}.
$$

| Ölçüt | Tanım |
|---|---|
| Tamamlanma süresi | $C_{son} = \max_i F_{son}(i)$ |
| Sipariş gecikmesi | $L_o = \big(\max_{i \in o} F_{son}(i) - \text{termin}_o\big) / 86400$ (gün) |
| Ayar kaybı | $\sum_{\text{ayar}} g(b) - g(a)$, iş günü cinsinden |
| Fazla çalışma | $\sum_e \sum_w \max(0,\ \text{saat}_{e,w} - 45)$ |

Termin anı, termin gününün (o gün çalışılmıyorsa önceki iş gününün) varsayılan
vardiya bitişidir.

> Kod: `motor/analiz.py`

---

## 15. Kaynakça

- Graham, R. L. (1969). *Bounds on multiprocessing timing anomalies.* SIAM Journal on Applied Mathematics, 17(2), 416–429.
- Jackson, J. R. (1955). *Scheduling a production line to minimize maximum tardiness.* Research Report 43, UCLA.
- Balinski, M. L., & Young, H. P. (1982). *Fair Representation: Meeting the Ideal of One Man, One Vote.* Yale University Press. (Hamilton ve D'Hondt yöntemleri)
- Ibaraki, T., & Katoh, N. (1988). *Resource Allocation Problems: Algorithmic Approaches.* MIT Press.
- Monden, Y. (1983). *Toyota Production System.* Industrial Engineering and Management Press. (hedef kovalama, heijunka)
- Pinedo, M. L. (2016). *Scheduling: Theory, Algorithms, and Systems* (5. baskı). Springer.
- Hopp, W. J., & Spearman, M. L. (2011). *Factory Physics* (3. baskı). Waveland Press.
- Ernst, A. T., Jiang, H., Krishnamoorthy, M., & Sier, D. (2004). *Staff scheduling and rostering: A review of applications, methods and models.* European Journal of Operational Research, 153(1), 3–27.
- 4857 sayılı İş Kanunu, m.41 (fazla çalışma) ve m.63 (çalışma süresi).
