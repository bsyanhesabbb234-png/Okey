import discord
import asyncio
import uuid
from typing import Optional
from src.game.okey_engine import OkeyGame, GameState, COLOR_EMOJI, COLOR_NAMES
from src.economy.db import ensure_oyuncu, update_cip, mac_bitti
from src.ui.render import render_el

IZLEYICI_ROL_ID = 1513129008554971256
KARISIK_BEKLEME = 30   # saniye
BOT_SAYAC = 10         # saniye

class GameManager:
    def __init__(self):
        self.masalar: dict[str, OkeyGame] = {}

    def yeni_masa_id(self) -> str:
        return uuid.uuid4().hex[:8].upper()

    def _masa_bul_oyuncu(self, user_id: int) -> Optional[str]:
        for mid, masa in self.masalar.items():
            if user_id in masa.oyuncular:
                return mid
        return None

    # ── Kanal oluştur ────────────────────────────────────────────────────────
    async def _oyun_kanali_olustur(self, guild: discord.Guild, masa: OkeyGame) -> Optional[discord.TextChannel]:
        """Oyun için özel kanal açar. İzleyici rolü görür ama yazamaz."""
        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
            }
            izleyici_rol = guild.get_role(IZLEYICI_ROL_ID)
            if izleyici_rol:
                overwrites[izleyici_rol] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=False,
                    read_message_history=True
                )
            # Oyuncuları kanala ekle (yazma izniyle)
            for uid in masa.oyuncular:
                if uid > 0:
                    member = guild.get_member(uid)
                    if member:
                        overwrites[member] = discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=True,
                            read_message_history=True
                        )
            # Okey kategorisi var mı bul, yoksa root'a ekle
            kategori = discord.utils.get(guild.categories, name="🎲 Okey Masaları")
            if not kategori:
                kategori = await guild.create_category("🎲 Okey Masaları")
            kanal = await guild.create_text_channel(
                name=f"okey-masa-{masa.masa_id.lower()}",
                category=kategori,
                overwrites=overwrites,
                topic=f"🎲 Okey Masası #{masa.masa_id} | Bahis: {'Yok' if masa.bahis == 0 else f'{masa.bahis:,} çip'}"
            )
            masa.oyun_kanal_id = kanal.id
            return kanal
        except discord.Forbidden:
            return None
        except Exception as e:
            print(f"Kanal oluşturma hatası: {e}")
            return None

    async def _oyun_kanali_sil(self, guild: discord.Guild, masa: OkeyGame):
        """Oyun bitince kanalı siler."""
        if not masa.oyun_kanal_id:
            return
        try:
            kanal = guild.get_channel(masa.oyun_kanal_id)
            if kanal:
                await asyncio.sleep(10)  # 10 saniye bekle, herkes sonucu görsün
                await kanal.delete(reason="Okey oyunu bitti")
        except Exception:
            pass

    # ── Panel mesajı gönder ──────────────────────────────────────────────────
    async def _panel_gonder(self, channel: discord.TextChannel, masa_id: str) -> Optional[discord.Message]:
        """Oyun buton panelini kanala gönderir."""
        masa = self.masalar.get(masa_id)
        if not masa:
            return None
        from src.ui.views import build_masa_view
        embed = self._oyun_embed(masa)
        view = build_masa_view(masa_id)
        try:
            msg = await channel.send(embed=embed, view=view)
            masa.panel_mesaj_id = msg.id
            return msg
        except Exception:
            return None

    async def _mesaj_sayaci_artir(self, channel, masa_id: str):
        """Her çağrıda sayacı artırır; 2'ye ulaşınca panel yeniler."""
        masa = self.masalar.get(masa_id)
        if not masa or masa.durum != GameState.PLAYING:
            return
        masa.mesaj_sayaci += 1
        if masa.mesaj_sayaci >= 2:
            masa.mesaj_sayaci = 0
            await self._panel_gonder(channel, masa_id)

    # ── Masa kur ─────────────────────────────────────────────────────────────
    async def masa_kur(self, interaction: discord.Interaction, max_oyuncu: int = 4,
                       bot_modu=False, bahis: int = 0):
        await ensure_oyuncu(interaction.user.id, interaction.user.display_name)

        mevcut = self._masa_bul_oyuncu(interaction.user.id)
        if mevcut:
            await interaction.response.send_message(
                f"❌ Zaten bir masadasınız! Masa: `{mevcut}`\nÖnce ayrılın: `/okey ayrıl`",
                ephemeral=True
            )
            return

        masa_id = self.yeni_masa_id()
        masa = OkeyGame(masa_id=masa_id, max_oyuncu=max_oyuncu, bahis=bahis, bot_modu=bot_modu)
        masa.kanal_id = interaction.channel_id
        masa.oyuncu_ekle(interaction.user.id, interaction.user.display_name)

        if bot_modu is True:
            # Tüm yerleri botlarla doldur
            masa.doldur_botlarla()

        self.masalar[masa_id] = masa

        embed = self._masa_embed(masa)
        from src.ui.views import build_masa_view
        view = build_masa_view(masa_id)

        if bot_modu is True:
            # Önce lobi göster, 10sn sayaçlı
            await interaction.response.send_message(
                f"⏳ **Oyun kuruluyor...** 3 Bot ekleniyor!\n"
                f"🤖 **10 saniye** içinde oyun başlıyor...",
                embed=embed, view=view
            )
            try:
                msg = await interaction.original_response()
                masa.mesaj_id = msg.id
            except Exception:
                pass
            asyncio.create_task(self._bot_sayac_baslat(interaction, masa_id))

        elif bot_modu == "karisik":
            await interaction.response.send_message(
                f"🎲 **Karışık Masa kuruldu!** `({masa.doluluk})`\n"
                f"⏳ Katılmak için **{KARISIK_BEKLEME} saniye** bekleniyor, eksik yerler botlarla doldurulacak...",
                embed=embed, view=view
            )
            try:
                msg = await interaction.original_response()
                masa.mesaj_id = msg.id
            except Exception:
                pass
            asyncio.create_task(self._karisik_sayac_baslat(interaction, masa_id))

        else:
            gercek = len([u for u in masa.oyuncular if u > 0])
            await interaction.response.send_message(
                f"🎮 **Masa kuruldu!** `({gercek}/{max_oyuncu})`\nKatılmak için **Masaya Katıl** butonuna basın!",
                embed=embed, view=view
            )
            try:
                msg = await interaction.original_response()
                masa.mesaj_id = msg.id
            except Exception:
                pass

    async def _bot_sayac_baslat(self, interaction: discord.Interaction, masa_id: str):
        """10 saniye sayar, sonra oyunu başlatır."""
        for i in range(BOT_SAYAC, 0, -1):
            await asyncio.sleep(1)
            masa = self.masalar.get(masa_id)
            if not masa or masa.durum != GameState.WAITING:
                return
        await self.masayi_baslat_otomatik(interaction.guild, interaction.channel, masa_id)

    async def _karisik_sayac_baslat(self, interaction: discord.Interaction, masa_id: str):
        """30 saniye bekler, eksik yerleri botlarla doldurur."""
        await asyncio.sleep(KARISIK_BEKLEME)
        masa = self.masalar.get(masa_id)
        if not masa or masa.durum != GameState.WAITING:
            return
        gercek = len([u for u in masa.oyuncular if u > 0])
        if gercek < 2:
            # Yeterli oyuncu yok, masa kapat
            del self.masalar[masa_id]
            try:
                await interaction.channel.send("⚠️ Yeterli oyuncu gelmedi, masa kapatıldı.")
            except Exception:
                pass
            return
        # Eksikleri botlarla doldur
        eksik = masa.max_oyuncu - len(masa.oyuncular)
        if eksik > 0:
            masa.doldur_botlarla()
            try:
                await interaction.channel.send(
                    f"⏰ **Süre doldu!** Karşınızda **{eksik} Bot** eklendi. Oyun başlıyor!"
                )
            except Exception:
                pass
        await self.masayi_baslat_otomatik(interaction.guild, interaction.channel, masa_id)

    # ── Masaya katıl ─────────────────────────────────────────────────────────
    async def masaya_katil(self, interaction: discord.Interaction, masa_id: str):
        await ensure_oyuncu(interaction.user.id, interaction.user.display_name)
        masa = self.masalar.get(masa_id)
        if not masa:
            await interaction.response.send_message("❌ Masa bulunamadı.", ephemeral=True)
            return
        if masa.durum != GameState.WAITING:
            await interaction.response.send_message("❌ Masa zaten başlamış.", ephemeral=True)
            return
        if interaction.user.id in masa.oyuncular:
            await interaction.response.send_message("❌ Zaten bu masadasınız!", ephemeral=True)
            return
        mevcut = self._masa_bul_oyuncu(interaction.user.id)
        if mevcut:
            await interaction.response.send_message(f"❌ Zaten `{mevcut}` masadasınız.", ephemeral=True)
            return
        if masa.bahis > 0:
            oyuncu = await ensure_oyuncu(interaction.user.id, interaction.user.display_name)
            if oyuncu.get("cip", 0) < masa.bahis:
                await interaction.response.send_message(
                    f"❌ VIP masa için **{masa.bahis:,}** 🪙 gerekmektedir. Mevcut: **{oyuncu.get('cip',0):,}** 🪙",
                    ephemeral=True
                )
                return

        ok = masa.oyuncu_ekle(interaction.user.id, interaction.user.display_name)
        if not ok:
            await interaction.response.send_message("❌ Masa dolu.", ephemeral=True)
            return

        gercek = len([u for u in masa.oyuncular if u > 0])
        embed = self._masa_embed(masa)

        if len(masa.oyuncular) >= masa.max_oyuncu:
            # Masa doldu
            await interaction.response.edit_message(
                content=f"🎉 **Masa doldu! Oyun başlıyor...**\nOyuncular: {self._oyuncu_mention_str(masa, interaction.guild)}",
                embed=embed
            )
            await asyncio.sleep(1)
            await self.masayi_baslat_otomatik(interaction.guild, interaction.channel, masa_id)
        else:
            await interaction.response.edit_message(
                content=f"✅ **{interaction.user.display_name}** masaya katıldı! `({gercek}/{masa.max_oyuncu})`\nKatılmak için butona basın!",
                embed=embed
            )

    def _oyuncu_mention_str(self, masa: OkeyGame, guild: Optional[discord.Guild]) -> str:
        parts = []
        for uid in masa.oyuncular:
            if uid > 0 and guild:
                member = guild.get_member(uid)
                parts.append(member.mention if member else masa.oyuncu_adlari.get(uid, "?"))
            else:
                parts.append(masa.oyuncu_adlari.get(uid, "?"))
        return ", ".join(parts)

    # ── Oyunu başlat ─────────────────────────────────────────────────────────
    async def masayi_baslat(self, interaction: discord.Interaction, masa_id: str):
        masa = self.masalar.get(masa_id)
        if not masa:
            await interaction.response.send_message("❌ Masa bulunamadı.", ephemeral=True)
            return
        if masa.oyuncular and interaction.user.id != masa.oyuncular[0]:
            await interaction.response.send_message("❌ Sadece masa kurucusu başlatabilir.", ephemeral=True)
            return
        if masa.durum != GameState.WAITING:
            await interaction.response.send_message("❌ Masa zaten başlamış.", ephemeral=True)
            return
        if len([u for u in masa.oyuncular if u > 0]) < 1:
            await interaction.response.send_message("❌ En az 1 gerçek oyuncu gerekli.", ephemeral=True)
            return

        # Eksikleri botlarla doldur (el ile başlatınca)
        if len(masa.oyuncular) < masa.max_oyuncu:
            masa.doldur_botlarla()

        await interaction.response.defer()
        await self.masayi_baslat_otomatik(interaction.guild, interaction.channel, masa_id)

    async def masayi_baslat_otomatik(self, guild: Optional[discord.Guild], kanal, masa_id: str):
        masa = self.masalar.get(masa_id)
        if not masa or masa.durum != GameState.WAITING:
            return
        masa.oyunu_baslat()

        # Özel oyun kanalı oluştur
        oyun_kanali = None
        if guild:
            oyun_kanali = await self._oyun_kanali_olustur(guild, masa)

        hedef_kanal = oyun_kanali or kanal

        # Oyun başlangıç duyurusu
        oyuncu_list = self._oyuncu_mention_str(masa, guild)
        if kanal and oyun_kanali and oyun_kanali.id != kanal.id:
            await kanal.send(
                f"🎲 **Oyun başladı!** Oyuncular: {oyuncu_list}\n"
                f"📍 Oyun kanalı: {oyun_kanali.mention}"
            )

        # Oyun kanalına başlangıç mesajı + panel
        if hedef_kanal:
            await hedef_kanal.send(
                f"🎲 **Kahvehane Okey Başladı!**\n"
                f"👥 Oyuncular: {oyuncu_list}\n"
                f"🎴 Okey Taşı: {self._okey_str(masa)}\n"
                f"⏳ İlk Sıra: **{masa.oyuncu_adlari.get(masa.siradaki_oyuncu_id(), '?')}**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            await self._panel_gonder(hedef_kanal, masa_id)

        await self._bot_tur_kontrol(hedef_kanal, masa_id)

    # ── Bot turları ──────────────────────────────────────────────────────────
    async def _bot_tur_kontrol(self, channel, masa_id: str):
        masa = self.masalar.get(masa_id)
        if not masa or masa.durum != GameState.PLAYING:
            return
        siradaki = masa.siradaki_oyuncu_id()
        if siradaki in masa.bot_oyuncular:
            await asyncio.sleep(1.5)
            masa = self.masalar.get(masa_id)
            if not masa or masa.durum != GameState.PLAYING:
                return
            atilan = masa.bot_hamle_yap(siradaki)
            bot_ad = masa.oyuncu_adlari.get(siradaki, "Bot")
            if masa.durum == GameState.FINISHED:
                if channel:
                    await channel.send(f"🤖 **{bot_ad}** OKEY AÇTI! 🎉")
                await self._oyun_bitti(channel, masa_id, siradaki)
                return
            if channel and atilan:
                await channel.send(f"🤖 **{bot_ad}** taş attı: `{str(atilan)}`")
                await self._mesaj_sayaci_artir(channel, masa_id)
            sonraki = masa.siradaki_oyuncu_id()
            if sonraki in masa.bot_oyuncular:
                await self._bot_tur_kontrol(channel, masa_id)
            else:
                if channel:
                    await channel.send(
                        f"🎴 Sıra: **{masa.oyuncu_adlari.get(sonraki, '?')}** — Taş çekin veya paneli kullanın!"
                    )
                    await self._mesaj_sayaci_artir(channel, masa_id)

    # ── El gör ──────────────────────────────────────────────────────────────
    async def el_goster(self, interaction: discord.Interaction, masa_id: str):
        masa = self.masalar.get(masa_id)
        if not masa:
            await interaction.response.send_message("❌ Masa bulunamadı.", ephemeral=True)
            return
        if interaction.user.id not in masa.oyuncu_elleri:
            await interaction.response.send_message("❌ Bu masada değilsiniz veya oyun başlamadı.", ephemeral=True)
            return
        el = masa.oyuncu_elleri[interaction.user.id]
        img_buf = render_el(el, masa.okey_tas, title=f"🀄 {interaction.user.display_name} — Elinizdeki Taşlar")
        file = discord.File(img_buf, filename="el.png")

        # El listesini text olarak da göster (renk+sayı şeklinde)
        el_text = "\n".join(
            f"`{i+1}.` {str(t)}"
            for i, t in enumerate(el)
        )
        embed = discord.Embed(
            title="🀄 Elinizdeki Taşlar",
            description=(
                f"Okey taşı: {self._okey_str(masa)}\n"
                f"Taş sayınız: **{len(el)}**\n\n"
                f"**Taş Listesi:**\n{el_text}\n\n"
                f"💡 *Taş atmak için **Taş At** butonuna basın, renk ve sayısını girin.*"
            ),
            color=0x2ecc71
        )
        embed.set_image(url="attachment://el.png")
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

    # ── Per diz ─────────────────────────────────────────────────────────────
    async def per_diz(self, interaction: discord.Interaction, masa_id: str):
        masa = self.masalar.get(masa_id)
        if not masa:
            await interaction.response.send_message("❌ Masa bulunamadı.", ephemeral=True)
            return
        if interaction.user.id not in masa.oyuncu_elleri:
            await interaction.response.send_message("❌ Bu masada değilsiniz.", ephemeral=True)
            return
        masa.peri_diz(interaction.user.id)
        el = masa.oyuncu_elleri[interaction.user.id]
        img_buf = render_el(el, masa.okey_tas, title="🀄 Perlenmiş El")
        file = discord.File(img_buf, filename="per.png")
        el_text = " | ".join(str(t) for t in el)
        embed = discord.Embed(
            title="🀄 Perlendi!",
            description=f"Taşlarınız renk+sayıya göre sıralandı.\n\n`{el_text}`",
            color=0x3498db
        )
        embed.set_image(url="attachment://per.png")
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

    # ── Talon çek ───────────────────────────────────────────────────────────
    async def talon_cek(self, interaction: discord.Interaction, masa_id: str):
        masa = self.masalar.get(masa_id)
        if not masa:
            await interaction.response.send_message("❌ Masa bulunamadı.", ephemeral=True)
            return
        if masa.durum != GameState.PLAYING:
            await interaction.response.send_message("❌ Oyun başlamadı.", ephemeral=True)
            return
        if masa.siradaki_oyuncu_id() != interaction.user.id:
            await interaction.response.send_message("❌ Sıra sizde değil!", ephemeral=True)
            return
        if masa.el_cekti.get(interaction.user.id):
            await interaction.response.send_message("❌ Bu turda zaten taş çektiniz. Şimdi bir taş atın!", ephemeral=True)
            return
        tas = masa.tas_cek(interaction.user.id)
        if not tas:
            await interaction.response.send_message("❌ Talon boş!", ephemeral=True)
            return
        el = masa.oyuncu_elleri[interaction.user.id]
        img_buf = render_el(el, masa.okey_tas, title=f"🎴 Çekilen: {str(tas)}")
        file = discord.File(img_buf, filename="cek.png")
        embed = discord.Embed(
            title="🎴 Taş Çekildi!",
            description=(
                f"Çektiğiniz taş: **{str(tas)}**\n"
                f"Taş sayınız: **{len(el)}**\n\n"
                f"💡 Şimdi **Taş At** butonuna basıp atmak istediğiniz taşın **rengini** ve **sayısını** girin."
            ),
            color=0xf39c12
        )
        embed.set_image(url="attachment://cek.png")
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

    # ── Çöpten çek ──────────────────────────────────────────────────────────
    async def cop_cek(self, interaction: discord.Interaction, masa_id: str):
        masa = self.masalar.get(masa_id)
        if not masa:
            await interaction.response.send_message("❌ Masa bulunamadı.", ephemeral=True)
            return
        if masa.durum != GameState.PLAYING:
            await interaction.response.send_message("❌ Oyun başlamadı.", ephemeral=True)
            return
        if masa.siradaki_oyuncu_id() != interaction.user.id:
            await interaction.response.send_message("❌ Sıra sizde değil!", ephemeral=True)
            return
        if masa.el_cekti.get(interaction.user.id):
            await interaction.response.send_message("❌ Bu turda zaten taş çektiniz.", ephemeral=True)
            return
        if not masa.cop_yigi:
            await interaction.response.send_message("❌ Çöp yığını boş!", ephemeral=True)
            return
        tas = masa.cop_cek(interaction.user.id)
        if not tas:
            await interaction.response.send_message("❌ Taş alınamadı.", ephemeral=True)
            return
        el = masa.oyuncu_elleri[interaction.user.id]
        img_buf = render_el(el, masa.okey_tas, title=f"♻️ Çöpten: {str(tas)}")
        file = discord.File(img_buf, filename="cop.png")
        embed = discord.Embed(
            title="♻️ Çöpten Alındı!",
            description=(
                f"Aldığınız taş: **{str(tas)}**\n"
                f"Taş sayınız: **{len(el)}**\n\n"
                f"💡 Şimdi **Taş At** butonuna basıp atmak istediğiniz taşın **rengini** ve **sayısını** girin."
            ),
            color=0x95a5a6
        )
        embed.set_image(url="attachment://cop.png")
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

    # ── Taş at (renk+sayı ile) ───────────────────────────────────────────────
    async def tas_at_renk_sayi(self, interaction: discord.Interaction, masa_id: str, renk: str, sayi: int):
        masa = self.masalar.get(masa_id)
        if not masa:
            await interaction.response.send_message("❌ Masa bulunamadı.", ephemeral=True)
            return
        if masa.durum != GameState.PLAYING:
            await interaction.response.send_message("❌ Oyun başlamadı.", ephemeral=True)
            return
        if masa.siradaki_oyuncu_id() != interaction.user.id:
            await interaction.response.send_message("❌ Sıra sizde değil!", ephemeral=True)
            return
        if not masa.el_cekti.get(interaction.user.id):
            await interaction.response.send_message("❌ Önce taş çekin!", ephemeral=True)
            return

        # Eldeki taşları göster, hangisinin var mı kontrol et
        el = masa.oyuncu_elleri.get(interaction.user.id, [])
        eslesme = [(i, t) for i, t in enumerate(el) if not t.okey and t.renk == renk and t.sayi == sayi]
        if not eslesme:
            renk_emoji = COLOR_EMOJI.get(renk, "")
            renk_ad = COLOR_NAMES.get(renk, renk)
            mevcut = " | ".join(str(t) for t in el)
            await interaction.response.send_message(
                f"❌ Elinizde **{renk_emoji}{renk_ad} {sayi}** taşı yok!\n"
                f"**Eliniz:** {mevcut}",
                ephemeral=True
            )
            return

        atilan = masa.tas_at_by_renk_sayi(interaction.user.id, renk, sayi)
        if atilan is None:
            await interaction.response.send_message("❌ Taş atılamadı.", ephemeral=True)
            return

        sonraki_id = masa.siradaki_oyuncu_id()
        sonraki_ad = masa.oyuncu_adlari.get(sonraki_id, "?")

        channel = interaction.channel
        # Oyun kanalı varsa oraya gönder
        if masa.oyun_kanal_id and interaction.guild:
            oyun_kanali = interaction.guild.get_channel(masa.oyun_kanal_id)
            if oyun_kanali:
                channel = oyun_kanali

        await interaction.response.send_message(
            f"🗑️ **{interaction.user.display_name}** `{str(atilan)}` taşını attı.\n"
            f"🎴 Sıra: **{sonraki_ad}**",
            ephemeral=False
        )

        await self._mesaj_sayaci_artir(channel, masa_id)
        await self._bot_tur_kontrol(channel, masa_id)

    # ── Okey aç ─────────────────────────────────────────────────────────────
    async def okey_ac(self, interaction: discord.Interaction, masa_id: str):
        masa = self.masalar.get(masa_id)
        if not masa:
            await interaction.response.send_message("❌ Masa bulunamadı.", ephemeral=True)
            return
        if masa.durum != GameState.PLAYING:
            await interaction.response.send_message("❌ Oyun başlamadı.", ephemeral=True)
            return
        if masa.siradaki_oyuncu_id() != interaction.user.id:
            await interaction.response.send_message("❌ Sıra sizde değil!", ephemeral=True)
            return
        kazandi = masa.okey_ac(interaction.user.id)
        if kazandi:
            await interaction.response.send_message(
                f"🎉🏆 **{interaction.user.display_name} OKEY AÇTI! TEBRİKLER!** 🏆🎉"
            )
            channel = interaction.channel
            if masa.oyun_kanal_id and interaction.guild:
                oyun_kanali = interaction.guild.get_channel(masa.oyun_kanal_id)
                if oyun_kanali:
                    channel = oyun_kanali
            await self._oyun_bitti(channel, masa_id, interaction.user.id, interaction.guild)
        else:
            await interaction.response.send_message(
                "❌ Eliniz geçerli bir Okey kombinasyonu oluşturmuyor. Devam edin!",
                ephemeral=True
            )

    # ── Oyun bitti ──────────────────────────────────────────────────────────
    async def _oyun_bitti(self, channel, masa_id: str, kazanan_id: int, guild: Optional[discord.Guild] = None):
        masa = self.masalar.get(masa_id)
        if not masa:
            return
        masa.durum = GameState.FINISHED
        kazanan_ad = masa.oyuncu_adlari.get(kazanan_id, "Bot")
        gercek_oyuncular = [uid for uid in masa.oyuncular if uid > 0]

        await mac_bitti(kazanan_id, masa.oyuncular, masa.bahis, masa_id)

        embed = discord.Embed(
            title="🏆 Oyun Bitti!",
            description=f"🎊 **{kazanan_ad}** oyunu kazandı!",
            color=0xf1c40f
        )
        if masa.bahis > 0:
            kazanim = 200 + masa.bahis * (len(gercek_oyuncular) - 1)
            embed.add_field(name="💰 Bahis", value=f"{masa.bahis:,} 🪙", inline=True)
            embed.add_field(name="🎁 Kazanılan", value=f"{kazanim:,} 🪙", inline=True)
        else:
            embed.add_field(name="🎁 Kazanılan", value="200 🪙 + Puan", inline=True)
        embed.set_footer(text="Kanal 10 saniye içinde silinecek.")

        if channel:
            await channel.send(embed=embed)

        masa_kanal_id = masa.oyun_kanal_id
        del self.masalar[masa_id]

        # Kanalı sil
        if guild and masa_kanal_id:
            oyun_kanali = guild.get_channel(masa_kanal_id)
            if oyun_kanali:
                asyncio.create_task(self._kanal_sil_bekle(oyun_kanali))

    async def _kanal_sil_bekle(self, kanal: discord.TextChannel):
        await asyncio.sleep(10)
        try:
            await kanal.delete(reason="Okey oyunu bitti")
        except Exception:
            pass

    # ── Masadan ayrıl ───────────────────────────────────────────────────────
    async def masadan_ayril(self, interaction: discord.Interaction, masa_id: str):
        masa = self.masalar.get(masa_id)
        if not masa:
            await interaction.response.send_message("❌ Masa bulunamadı.", ephemeral=True)
            return
        if interaction.user.id not in masa.oyuncular:
            await interaction.response.send_message("❌ Bu masada değilsiniz.", ephemeral=True)
            return

        channel = interaction.channel
        if masa.oyun_kanal_id and interaction.guild:
            oyun_kanali = interaction.guild.get_channel(masa.oyun_kanal_id)
            if oyun_kanali:
                channel = oyun_kanali

        if masa.durum == GameState.PLAYING:
            await update_cip(interaction.user.id, -100)
            await interaction.response.send_message(
                "⚠️ Aktif maçtan ayrıldığınız için **100 🪙** ceza uygulandı.", ephemeral=True
            )
            masa.oyuncu_cikar(interaction.user.id)
            gercek_kalan = [u for u in masa.oyuncular if u > 0]
            if not gercek_kalan:
                await self._oyun_bitti(channel, masa_id, -1, interaction.guild)
                return
            if channel:
                await channel.send(
                    f"🚪 **{interaction.user.display_name}** masadan ayrıldı.\n"
                    f"🎴 Sıra: **{masa.oyuncu_adlari.get(masa.siradaki_oyuncu_id(), '?')}**"
                )
                await self._mesaj_sayaci_artir(channel, masa_id)
            await self._bot_tur_kontrol(channel, masa_id)
        else:
            masa.oyuncu_cikar(interaction.user.id)
            gercek_kalan = [u for u in masa.oyuncular if u > 0]
            if not gercek_kalan:
                if masa_id in self.masalar:
                    del self.masalar[masa_id]
                await interaction.response.send_message("✅ Masadan ayrıldınız. Masa kapatıldı.", ephemeral=True)
                return
            embed = self._masa_embed(masa)
            await interaction.response.edit_message(
                content=f"🚪 **{interaction.user.display_name}** masadan ayrıldı.",
                embed=embed
            )

    # ── Embed yardımcıları ───────────────────────────────────────────────────
    def _masa_embed(self, masa: OkeyGame) -> discord.Embed:
        gercek = len([u for u in masa.oyuncular if u > 0])
        oyuncu_listesi = "\n".join(
            f"{'🤖' if uid < 0 else '👤'} **{ad}**"
            for uid, ad in masa.oyuncu_adlari.items()
            if uid in masa.oyuncular
        )
        bos = masa.max_oyuncu - len(masa.oyuncular)
        bos_str = "\n".join(f"⬜ _{i+1}. kişi bekleniyor..._" for i in range(bos)) if bos else ""

        embed = discord.Embed(
            title=f"🎮 Okey Masası — `{masa.masa_id}`",
            description=(
                f"**Doluluk:** {gercek}/{masa.max_oyuncu}\n"
                f"**Bahis:** {'Yok' if masa.bahis == 0 else f'{masa.bahis:,} 🪙'}\n\n"
                f"**Oyuncular:**\n{oyuncu_listesi}\n{bos_str}"
            ),
            color=0x2ecc71
        )
        embed.set_footer(text="Katılmak için 'Masaya Katıl' butonuna basın!")
        return embed

    def _oyun_embed(self, masa: OkeyGame) -> discord.Embed:
        siradaki_id = masa.siradaki_oyuncu_id()
        oyuncu_listesi = "\n".join(
            f"{'🤖' if uid < 0 else '👤'} **{ad}**" + (" ⏳ **(SENİN SIRAN)**" if uid == siradaki_id else "")
            for uid, ad in masa.oyuncu_adlari.items()
            if uid in masa.oyuncular
        )
        embed = discord.Embed(
            title=f"🎲 Okey Devam Ediyor — `{masa.masa_id}`",
            description=(
                f"**Okey Taşı:** {self._okey_str(masa)}\n"
                f"**Talon:** {len(masa.talon)} taş kaldı\n\n"
                f"**Oyuncular:**\n{oyuncu_listesi}"
            ),
            color=0xf1c40f
        )
        if masa.cop_yigi:
            embed.add_field(name="♻️ Üstteki Çöp", value=f"`{str(masa.cop_yigi[-1])}`", inline=True)
        embed.add_field(name="🎴 Sıra", value=f"**{masa.oyuncu_adlari.get(siradaki_id, '?')}**", inline=True)
        embed.set_footer(
            text="El Gör → Talon'dan Çek VEYA Çöpten Al → Taş At | Her 2 mesajda panel yenilenir."
        )
        return embed

    def _okey_str(self, masa: OkeyGame) -> str:
        if not masa.okey_tas:
            return "?"
        renk_emoji = COLOR_EMOJI.get(masa.okey_tas.renk, "⬜")
        renk_ad = COLOR_NAMES.get(masa.okey_tas.renk, masa.okey_tas.renk)
        return f"{renk_emoji} **{renk_ad} {masa.okey_tas.sayi}**"

game_manager = GameManager()
