# Haber Radarı

BT gündemini (yapay zeka, AI governance, siber güvenlik, kuantum,
veri merkezi, ödeme sistemleri/CBDC, iş sürekliliği, Türkiye) her hafta otomatik
tarayıp bülten üreten, e-postayla bildiren sistem. Etkinlik Radarı'nın kardeşi —
aynı kurulum mantığı, aynı "bilgisayarda hiçbir şey çalışmaz" prensibi.

## Nasıl çalışır

- **Google News RSS**: her anahtar kelime binlerce siteyi tarar — takip
  listenizde olmayan sitelerdeki haberleri yakalayan keşif motoru budur
- **Site RSS'leri**: düzenli okuduğunuz kaynaklar (`sources.yaml`'a eklenir)
- **Anthropic API filtresi**: başlıkları 0-10 önem puanıyla eler, aynı olayın
  farklı sitelerdeki kopyalarını tekilleştirir (anahtar yoksa filtresiz çalışır)
- **Çıktı**: haftalık markdown bülten (başlık+link) + GitHub Pages dashboard +
  e-posta. `docs/news.json` mevcut bülten üretici uygulamanıza da beslenebilir.

## Kurulum (Etkinlik Radarı ile aynı: repo → dosya yükle → Actions → Pages)

Ek olarak iki grup secret (repo → Settings → Secrets and variables → Actions):

**LLM filtresi** (önerilir, ~$1-3/ay):
- `ANTHROPIC_API_KEY` — console.anthropic.com'dan alınır
- İsteğe bağlı `ANTHROPIC_MODEL` variable'ı (varsayılan: claude-haiku-4-5)

**E-posta bildirimi** (opsiyonel):
- `SMTP_HOST` (Gmail: smtp.gmail.com), `SMTP_PORT` (587)
- `SMTP_USER` (gönderen adres), `SMTP_PASS` (Gmail'de "uygulama şifresi":
  myaccount.google.com/apppasswords), `MAIL_TO` (alıcı — iş adresiniz olabilir)

Secrets tanımlanmazsa sistem yine çalışır: filtresiz tarar, e-posta atlar,
sonuçları repo ve dashboard'a yazar.

## Anahtar kelime ayarı

`sources.yaml` bültenin kalitesini belirleyen yerdir. İlk birkaç hafta bülteni
izleyip sorguları törpüleyin: çok gürültü getiren sorguyu daraltın
("yapay zeka" → "yapay zeka düzenleme"), eksik kalan konuya sorgu ekleyin.
`when: 7d` parametresi son 7 günü tarar (haftalık ritimle uyumlu).
