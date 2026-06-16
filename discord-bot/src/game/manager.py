import discord
import asyncio
import uuid
from typing import Optional
from src.game.okey_engine import OkeyGame, GameState
from src.economy.db import ensure_oyuncu, update_cip, mac_bitti
from src.ui.render import render_el, render_masa_durumu

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
        masa = OkeyGame(masa_id=masa_id, max_oyuncu=max_oyuncu, bahis=bahis)
        masa.kanal_id = interaction.channel_id
        masa.oyuncu_ekle(interaction.user.id, interaction.user.display_name)

        if bot_modu == True:
            masa.doldur_botlarla()
        elif bot_modu == "karisik":
            pass

        self.masalar[masa_id] = masa

        embed = self._masa_embed(masa)
        from src.ui.views import build_masa_view
        view = build_masa_view(masa_id)

        if bot_modu == True:
            await interaction.response.send_message(embed=embed, view=view)
            msg = await interaction.original_response()
            masa.mesaj_id = msg.id
            await asyncio.sleep(1)
            await self.masayi_baslat_otomatik(interaction.channel, masa_id)
        else:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed, view=view)
            try:
                msg = await interaction.original_response()
                masa.mesaj_id = msg.id
            except Exception:
                pass

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
            await interaction.response.send_message("❌ Zaten bu masadasınız.", ephemeral=True)
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

        embed = self._masa_embed(masa)
        await interaction.response.edit_message(embed=embed)

        if len(masa.oyuncular) >= masa.max_oyuncu:
            await asyncio.sleep(0.5)
            await self.masayi_baslat_otomatik(interaction.channel, masa_id)

    async def masayi_baslat(self, interaction: discord.Interaction, masa_id: str):
        masa = self.masalar.get(masa_id)
        if not masa:
            await interaction.response.send_message("❌ Masa bulunamadı.", ephemeral=True)
            return
        if interaction.user.id != masa.oyuncular[0] and interaction.user.id not in masa.oyuncular:
            await interaction.response.send_message("❌ Sadece masa kurucusu başlatabilir.", ephemeral=True)
            return
        if masa.durum != GameState.WAITING:
            await interaction.response.send_message("❌ Masa zaten başlamış.", ephemeral=True)
            return
        if len(masa.oyuncular) < 2:
            await interaction.response.send_message("❌ En az 2 oyuncu gerekli.", ephemeral=True)
            return

        if hasattr(interaction, '_bv_masa_id'):
            pass

        masa.oyunu_baslat()
        embed = self._oyun_embed(masa)
        from src.ui.views import build_masa_view
        view = build_masa_view(masa_id)
        await interaction.response.edit_message(embed=embed, view=view)
        await interaction.followup.send(
            f"🎲 **Oyun başladı!** Okey taşı: {self._okey_str(masa)}\n"
            f"🎴 İlk sıra: **{masa.oyuncu_adlari.get(masa.siradaki_oyuncu_id(), '?')}**",
        )
        await self._bot_tur_kontrol(interaction.channel, masa_id)

    async def masayi_baslat_otomatik(self, channel, masa_id: str):
        masa = self.masalar.get(masa_id)
        if not masa or masa.durum != GameState.WAITING:
            return
        masa.oyunu_baslat()
        embed = self._oyun_embed(masa)
        from src.ui.views import build_masa_view
        view = build_masa_view(masa_id)

        if masa.mesaj_id and channel:
            try:
                msg = await channel.fetch_message(masa.mesaj_id)
                await msg.edit(embed=embed, view=view)
            except Exception:
                pass

        if channel:
            await channel.send(
                f"🎲 **Oyun başladı!** Okey taşı: {self._okey_str(masa)}\n"
                f"🎴 İlk sıra: **{masa.oyuncu_adlari.get(masa.siradaki_oyuncu_id(), '?')}**"
            )
        await self._bot_tur_kontrol(channel, masa_id)

    async def _bot_tur_kontrol(self, channel, masa_id: str):
        masa = self.masalar.get(masa_id)
        if not masa or masa.durum != GameState.PLAYING:
            return
        siradaki = masa.siradaki_oyuncu_id()
        if siradaki in masa.bot_oyuncular:
            await asyncio.sleep(1.5)
            atilan = masa.bot_hamle_yap(siradaki)
            bot_ad = masa.oyuncu_adlari.get(siradaki, "Bot")
            if masa.durum == GameState.FINISHED:
                await self._oyun_bitti(channel, masa_id, siradaki)
                return
            if channel and atilan:
                await channel.send(f"🤖 **{bot_ad}** taş attı: `{str(atilan)}`")
            sonraki = masa.siradaki_oyuncu_id()
            if sonraki in masa.bot_oyuncular:
                await self._bot_tur_kontrol(channel, masa_id)
            else:
                if channel:
                    await channel.send(
                        f"🎴 Sıra: **{masa.oyuncu_adlari.get(sonraki, '?')}** — Taş çekin!"
                    )

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
        embed = discord.Embed(
            title="🀄 Elinizdeki Taşlar",
            description=f"Okey taşı: {self._okey_str(masa)}\nTaş sayınız: **{len(el)}**",
            color=0x2ecc71
        )
        embed.set_image(url="attachment://el.png")
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

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
        img_buf = render_el(el, masa.okey_tas, title="🀄 Perlenmiş Elinizdeki Taşlar")
        file = discord.File(img_buf, filename="per.png")
        embed = discord.Embed(title="🀄 Perlendi!", description="Taşlarınız otomatik sıralandı.", color=0x3498db)
        embed.set_image(url="attachment://per.png")
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

    async def talon_cek(self, interaction: discord.Interaction, masa_id: str):
        masa = self.masalar.get(masa_id)
        if not masa:
            await interaction.response.send_message("❌ Masa bulunamadı.", ephemeral=True)
            return
        if masa.durum != GameState.PLAYING:
            await interaction.response.send_message("❌ Oyun başlamadı.", ephemeral=True)
            return
        siradaki = masa.siradaki_oyuncu_id()
        if siradaki != interaction.user.id:
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
            title=f"🎴 Taş Çekildi!",
            description=f"Çektiğiniz taş: **{str(tas)}**\nŞimdi bir taş atın (Taş At butonuna basın).",
            color=0xf39c12
        )
        embed.set_image(url="attachment://cek.png")
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

    async def cop_cek(self, interaction: discord.Interaction, masa_id: str):
        masa = self.masalar.get(masa_id)
        if not masa:
            await interaction.response.send_message("❌ Masa bulunamadı.", ephemeral=True)
            return
        if masa.durum != GameState.PLAYING:
            await interaction.response.send_message("❌ Oyun başlamadı.", ephemeral=True)
            return
        siradaki = masa.siradaki_oyuncu_id()
        if siradaki != interaction.user.id:
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
        img_buf = render_el(el, masa.okey_tas, title=f"♻️ Çöpten alındı: {str(tas)}")
        file = discord.File(img_buf, filename="cop.png")
        embed = discord.Embed(
            title="♻️ Çöpten Alındı!",
            description=f"Aldığınız taş: **{str(tas)}**\nŞimdi bir taş atın.",
            color=0x95a5a6
        )
        embed.set_image(url="attachment://cop.png")
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

    async def tas_at(self, interaction: discord.Interaction, masa_id: str, index: int):
        masa = self.masalar.get(masa_id)
        if not masa:
            await interaction.response.send_message("❌ Masa bulunamadı.", ephemeral=True)
            return
        if masa.durum != GameState.PLAYING:
            await interaction.response.send_message("❌ Oyun başlamadı.", ephemeral=True)
            return
        siradaki = masa.siradaki_oyuncu_id()
        if siradaki != interaction.user.id:
            await interaction.response.send_message("❌ Sıra sizde değil!", ephemeral=True)
            return
        if not masa.el_cekti.get(interaction.user.id):
            await interaction.response.send_message("❌ Önce taş çekin!", ephemeral=True)
            return
        atilan = masa.tas_at(interaction.user.id, index)
        if atilan is None:
            await interaction.response.send_message("❌ Geçersiz taş numarası.", ephemeral=True)
            return

        sonraki_id = masa.siradaki_oyuncu_id()
        sonraki_ad = masa.oyuncu_adlari.get(sonraki_id, "?")

        await interaction.response.send_message(
            f"🗑️ **{interaction.user.display_name}** `{str(atilan)}` taşını attı.\n"
            f"🎴 Sıra: **{sonraki_ad}**",
            ephemeral=False
        )

        channel = interaction.channel
        await self._bot_tur_kontrol(channel, masa_id)

    async def okey_ac(self, interaction: discord.Interaction, masa_id: str):
        masa = self.masalar.get(masa_id)
        if not masa:
            await interaction.response.send_message("❌ Masa bulunamadı.", ephemeral=True)
            return
        if masa.durum != GameState.PLAYING:
            await interaction.response.send_message("❌ Oyun başlamadı.", ephemeral=True)
            return
        siradaki = masa.siradaki_oyuncu_id()
        if siradaki != interaction.user.id:
            await interaction.response.send_message("❌ Sıra sizde değil!", ephemeral=True)
            return
        kazandi = masa.okey_ac(interaction.user.id)
        if kazandi:
            await interaction.response.send_message(
                f"🎉🏆 **{interaction.user.display_name} OKEY AÇTI! TEBRİKLER!** 🏆🎉"
            )
            await self._oyun_bitti(interaction.channel, masa_id, interaction.user.id)
        else:
            await interaction.response.send_message(
                "❌ Eliniz geçerli bir Okey kombinasyonu oluşturmuyor. Devam edin!",
                ephemeral=True
            )

    async def _oyun_bitti(self, channel, masa_id: str, kazanan_id: int):
        masa = self.masalar.get(masa_id)
        if not masa:
            return
        masa.durum = GameState.FINISHED
        kazanan_ad = masa.oyuncu_adlari.get(kazanan_id, "Bot")
        gercek_oyuncular = [uid for uid in masa.oyuncular if uid > 0]

        await mac_bitti(kazanan_id, masa.oyuncular, masa.bahis, masa_id)

        embed = discord.Embed(
            title="🏆 Oyun Bitti!",
            description=f"**{kazanan_ad}** oyunu kazandı!",
            color=0xf1c40f
        )
        if masa.bahis > 0:
            embed.add_field(name="💰 Bahis", value=f"{masa.bahis:,} 🪙", inline=True)
            kazanim = 200 + masa.bahis * (len(gercek_oyuncular) - 1)
            embed.add_field(name="🎁 Kazanılan", value=f"{kazanim:,} 🪙", inline=True)

        if channel:
            await channel.send(embed=embed)

        del self.masalar[masa_id]

    async def masadan_ayril(self, interaction: discord.Interaction, masa_id: str):
        masa = self.masalar.get(masa_id)
        if not masa:
            await interaction.response.send_message("❌ Masa bulunamadı.", ephemeral=True)
            return
        if interaction.user.id not in masa.oyuncular:
            await interaction.response.send_message("❌ Bu masada değilsiniz.", ephemeral=True)
            return
        if masa.durum == GameState.PLAYING:
            await update_cip(interaction.user.id, -100)
            await interaction.response.send_message(
                "⚠️ Aktif maçtan ayrıldığınız için **100 🪙** ceza uygulandı.",
                ephemeral=True
            )
            siradaki = masa.siradaki_oyuncu_id()
            masa.oyuncu_cikar(interaction.user.id)
            if len([u for u in masa.oyuncular if u > 0]) < 1:
                del self.masalar[masa_id]
                return
            elif len(masa.oyuncular) < 2:
                del self.masalar[masa_id]
                if interaction.channel:
                    await interaction.channel.send("⚠️ Yeterli oyuncu kalmadığı için masa kapatıldı.")
                return
            if interaction.channel:
                await interaction.channel.send(
                    f"🚪 **{interaction.user.display_name}** masadan ayrıldı.\n"
                    f"🎴 Sıra: **{masa.oyuncu_adlari.get(masa.siradaki_oyuncu_id(), '?')}**"
                )
        else:
            masa.oyuncu_cikar(interaction.user.id)
            if not masa.oyuncular:
                del self.masalar[masa_id]
                await interaction.response.send_message("✅ Masadan ayrıldınız. Masa kapatıldı.", ephemeral=True)
                return
            embed = self._masa_embed(masa)
            await interaction.response.edit_message(embed=embed)

    def _masa_embed(self, masa: OkeyGame) -> discord.Embed:
        oyuncu_listesi = "\n".join(
            f"{'🤖' if uid < 0 else '👤'} {ad}"
            for uid, ad in masa.oyuncu_adlari.items()
        )
        embed = discord.Embed(
            title="🎮 Okey Masası Kuruldu!",
            description=(
                f"**Masa ID:** `{masa.masa_id}`\n"
                f"**Doluluk:** {masa.doluluk}\n"
                f"**Bahis:** {'Yok' if masa.bahis == 0 else f'{masa.bahis:,} 🪙'}\n\n"
                f"**Oyuncular:**\n{oyuncu_listesi or 'Yok'}"
            ),
            color=0x2ecc71
        )
        embed.set_footer(text="Masaya katılmak için 'Masaya Katıl' butonuna basın!")
        return embed

    def _oyun_embed(self, masa: OkeyGame) -> discord.Embed:
        oyuncu_listesi = "\n".join(
            f"{'🤖' if uid < 0 else '👤'} {ad}"
            + (" ⏳" if uid == masa.siradaki_oyuncu_id() else "")
            for uid, ad in masa.oyuncu_adlari.items()
        )
        embed = discord.Embed(
            title="🎲 Okey Oyunu Devam Ediyor",
            description=(
                f"**Masa:** `{masa.masa_id}`\n"
                f"**Okey Taşı:** {self._okey_str(masa)}\n"
                f"**Talon:** {len(masa.talon)} taş\n\n"
                f"**Oyuncular:**\n{oyuncu_listesi}"
            ),
            color=0xf1c40f
        )
        if masa.cop_yigi:
            embed.add_field(name="♻️ Üst Çöp", value=str(masa.cop_yigi[-1]), inline=True)
        embed.set_footer(text="El görmek için 'El Gör', Taş çekmek için 'Talon'dan Çek' butonuna basın.")
        return embed

    def _okey_str(self, masa: OkeyGame) -> str:
        if not masa.okey_tas:
            return "?"
        renk_emoji = {"kirmizi": "🔴", "sari": "🟡", "mavi": "🔵", "siyah": "⚫"}.get(masa.okey_tas.renk, "⬜")
        return f"{renk_emoji} **{masa.okey_tas.sayi}**"

game_manager = GameManager()
