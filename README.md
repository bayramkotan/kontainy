# kontainy

**Docker ve Podman'ın her ayarı, tek arayüzde**

kontainy, Linux sistemlerde (özellikle Arch/CachyOS gibi dağıtımlarda) konteyner
motorlarının **tüm yapılandırma yüzeyini** bir masaüstü arayüzünden yönetilebilir
kılan bir araçtır. Docker Desktop ve Podman Desktop "kolay kullanım" için tasarlandı
ve tam bu yüzden ayarların büyük kısmını ya hiç göstermiyor ya da ham bir JSON
kutusuna bırakıyor. kontainy bunun tersini yapar: **her ayarı açığa çıkarır,
ne işe yaradığını anlatır, tuzaklarını söyler.**

---

## Ayrışma noktası

| | Docker Desktop | Podman Desktop | **kontainy** |
|---|---|---|---|
| Container başlat/durdur | ✅ | ✅ | ✅ |
| `daemon.json` düzenleme | ham JSON kutusu | ✗ | **yapılandırılmış, açıklamalı, doğrulamalı** |
| `containers.conf` / `storage.conf` | ✗ | ✗ | **tam katalog** |
| `registries.conf` (short-name-mode) | ✗ | ✗ | **tam katalog** |
| Ayarın hangi dosyadan geldiği | ✗ | ✗ | **katman zinciri gösterilir** |
| Tüm motorlar aynı tabloda | ✗ (context'e bağlı) | ✗ (provider seçilir) | **✅ Motor sütunuyla birleşik** |
| Terminalin gerçek hedefi | ✗ | ✗ | **✅ çözümlenmiş zincir** |
| Tuzak/teşhis açıklamaları | ✗ | ✗ | **✅ ayar başına** |

---

## Temel ilke: context sistemine güvenme

`docker` CLI hedefini şu öncelikle belirler:

```
1. -H / --host bayrağı
2. DOCKER_HOST ortam değişkeni
3. DOCKER_CONTEXT ortam değişkeni
4. ~/.docker/config.json → currentContext
5. unix:///var/run/docker.sock
```

`DOCKER_HOST` ayarlıysa context **tamamen yok sayılır** — `docker context use`
"başarılı" der, hiçbir şey değişmez. "Container'larım kayboldu" şikayetinin bir
numaralı sebebi budur.

kontainy bu zincire girmez. Bulduğu **her** soketle ayrı ayrı konuşur ve hepsini
aynı anda listeler. Bir container hiçbir zaman kaybolmaz; yalnızca başka bir
motorda olduğu görülür.

---

## Desteklenen motorlar

- **Docker** — yerel daemon, Docker Desktop for Linux, Rancher Desktop, Colima
- **Podman** — rootful ve rootless soketler
- **Kubernetes / K3s** — context ve pod izleme *(planlı)*
- **Compose** — `docker compose` ve `podman-compose` *(planlı)*

Podman soketi Docker Engine API v1.41 ile uyumlu olduğundan tek bir istemci
ikisini de konuşur. Harici bağımlılık yoktur — `docker-py` veya `requests`
gerekmez, UNIX soketi üzerinden doğrudan JSON okunur.

---

## Kurulum

```bash
git clone https://github.com/bayramkotan/kontainy.git
cd kontainy
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

GUI açmadan teşhis:

```bash
.venv/bin/python main.py --scan     # motorlar ve context zinciri
.venv/bin/python main.py --doctor   # teşhis kuralları
.venv/bin/python main.py --stats    # katalog/kural/Learn sayımları
```

---

## Proje yapısı

```text
kontainy/
├── main.py                      # Giriş noktası: --scan · --doctor · --stats
└── src/
    ├── core/
    │   ├── constants.py         # Sürüm ve uygulama sabitleri
    │   ├── api.py               # UNIX soketi üzerinden Docker Engine API
    │   ├── discovery.py         # Motor keşfi + terminal hedefi zinciri
    │   └── catalog/             # AYAR KATALOĞU — projenin kalbi
    │       ├── base.py          #   Setting dataclass'ı, yüzeyler, dosyalar
    │       ├── docker.py        #   daemon.json + ~/.docker/config.json
    │       ├── podman.py        #   containers.conf + storage.conf + registries.conf
    │       ├── run_flags.py     #   container başına çalıştırma bayrakları
    │       └── quadlet.py       #   systemd birim anahtarları
    ├── rules/                   # TEŞHİS MOTORU
    │   ├── engine.py            #   ortam fotoğrafı + Rule/Finding
    │   └── catalog.py           #   kural seti
    ├── learn/
    │   └── content.py           # LEARN İÇERİĞİ — 16 kategori
    ├── gui/
    │   ├── main_window.py       # kenar çubuğu + sayfa yığını
    │   ├── theme.py             # palet ve QSS
    │   └── pages/               # engines · containers · settings · gotchas
    │       └── …                #   diagnostics · learn · logs
    └── utils/
        ├── config.py            # ayar deposu, günlük, komut geçmişi
        └── workers.py           # arka plan işleri (çökme dersi burada)
```

### `settings_catalog.py` — projenin kalbi

Her ayar yapısal veri olarak tanımlanır; arayüz bu katalogtan **üretilir**,
hiçbir ayar GUI'ye elle gömülmez.

```python
S("default-address-pools", "docker", SURFACE_NETWORK, "docker.daemon", "list",
  "Varsayılan Adres Havuzları",
  "Docker'ın kendi ağlarını hangi IP bloklarından üreteceği...",
  restart=True, danger=1,
  gotcha="KURUMSAL AĞ ÇAKIŞMASI: varsayılan 172.17.0.0/16 birçok VPN ile "
         "çakışır; Docker kurulunca VPN'in tamamı erişilemez olur...")
```

Alanlar: anahtar, motor, yüzey, dosya, tür, seçenekler, varsayılan, CLI karşılığı,
yeniden başlatma gerekiyor mu, kullanıcı/root kapsamı, risk düzeyi, açıklama,
**tuzak notu**, doküman bağlantısı.

Mevcut durum: **152 ayar** — 56 Docker, 67 Podman, 29 ortak.
102 tanesi root gerektirmez, 66 tanesinde tuzak notu vardır.

---

## Yetki politikası

kontainy **hiçbir zaman yetki yükseltmez**. Kullanıcı kapsamındaki dosyalar
(`~/.config/containers/*`, `~/.docker/config.json`, kullanıcı systemd birimleri)
doğrudan yönetilir. Root gerektiren dosyalar (`/etc/docker/daemon.json`,
`/etc/containers/*`, `/etc/subuid`) **salt okunur gösterilir** ve yanında
kopyalanabilir komut verilir.

Rootless Podman'ın tüm yapılandırması zaten `~/.config` altında olduğundan
asıl güç oradadır.

---

## Yol haritası

- [x] Motor keşfi — tüm soketler, context'e güvenmeden
- [x] Terminal hedefi çözümleme zinciri
- [x] Birleşik container tablosu (Motor sütunlu)
- [x] Ayar kataloğu + arama/süzme/ayrıntı arayüzü
- [ ] Ayar değerlerini gerçekten okuma (beyan edilen / etkin / hangi dosyadan)
- [ ] Kullanıcı kapsamlı ayarları yazma
- [ ] Teşhis motoru (kural tabanlı: subuid, linger, subnet çakışması, nftables…)
- [ ] Quadlet üretici (`.container`, `.pod`, `.network`, `.volume`)
- [ ] Olay akışı (`/events`) ile canlı tablo
- [ ] Log görüntüleyici (çoklanmış akış çözümlü)
- [ ] Kubernetes context ve pod izleme
- [ ] Compose entegrasyonu

---

## Lisans

MIT
