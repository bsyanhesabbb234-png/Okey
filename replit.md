# Kahvehane Okey Botu

Discord üzerinden tam kapsamlı, çok oyunculu Okey deneyimi sunan premium bir Discord botu.

## Run & Operate

- `cd discord-bot && python main.py` — botu başlat
- Workflow: **Discord Okey Botu** (konsol çıktısı)
- Gerekli secret: `DISCORD_BOT_TOKEN`

## Stack

- Python 3.11
- discord.py 2.7
- Pillow (görsel isteka render)
- aiosqlite (yerel SQLite veritabanı)

## Where things live

- `discord-bot/main.py` — giriş noktası
- `discord-bot/src/bot.py` — bot + tüm slash komutları
- `discord-bot/src/game/okey_engine.py` — Okey oyun motoru (taşlar, per, kazanma kontrolü)
- `discord-bot/src/game/manager.py` — masa & oyun akışı yöneticisi
- `discord-bot/src/economy/db.py` — SQLite veritabanı, çip ekonomisi
- `discord-bot/src/ui/views.py` — Discord buton/modal View'ları
- `discord-bot/src/ui/render.py` — Pillow ile görsel isteka & profil render
- `discord-bot/okey.db` — oyuncu veritabanı (otomatik oluşur)

## Architecture decisions

- Oyun durumu bellekte tutulur (GameState dict), bot yeniden başlayınca aktif masalar sıfırlanır.
- Kalıcı lobi paneli `LobiView(timeout=None)` ile her boot'ta yeniden kaydedilir.
- Masa butonları `build_masa_view(masa_id)` ile dinamik olarak oluşturulur; her masanın custom_id'si benzersizdir.
- Görsel render (Pillow) her istekte anlık üretilir, dosyaya kaydedilmez.
- Bot oyuncuları negatif user_id (-1, -2, -3, -4) ile temsil edilir.

## Product

- Ana panel: 5 kalıcı buton (4 kişilik masa, bot maçı, karışık, VIP bahisli, profil)
- Oyun: taş çekme/atma, per dizme, AI bot rakipler, okey açma
- Ekonomi: çip sistemi, günlük ödül, transfer, seviye
- Slash komutları: /okey kur/katil/hizli-mac/izle/ayril, /cuzdan, /gunluk, /gonder, /profil, /liderlik, /yardim
- Görsel: Pillow ile render edilmiş renkli isteka görseli (ephemeral)

## User preferences

- Yönetici ID: 1513128919182606378 (panel gönderme yetkisi)
- Dil: Türkçe
- Emoji: Özel sunucu emojileri ilerleyen aşamada ID ile değiştirilecek

## Gotchas

- `DATABASE_URL` bu projede kullanılmaz; SQLite kullanılır (`okey.db`)
- pnpm workspace'deki `api-server` bu botla ilgisizdir
- Slash komutları ilk başlatmada guild'e sync edilir, yayılması 1-60 dakika sürebilir
- Bot yeniden başlatılırsa aktif masalar sıfırlanır (in-memory)

## Pointers

- discord.py docs: https://discordpy.readthedocs.io/
