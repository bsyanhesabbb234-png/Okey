import discord
from discord.ui import View, Button, Modal, TextInput
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.bot import OkeyBot

ADMIN_ID = 1513128919182606378
IZLEYICI_ROL_ID = 1513129008554971256

class LobiView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="4 Kişilik Masa Kur", style=discord.ButtonStyle.primary, emoji="👥", custom_id="lobi_4kisi", row=0)
    async def dort_kisi(self, interaction: discord.Interaction, button: Button):
        from src.game.manager import game_manager
        await game_manager.masa_kur(interaction, max_oyuncu=4, bot_modu=False)

    @discord.ui.button(label="Botlara Karşı Oyna", style=discord.ButtonStyle.success, emoji="🤖", custom_id="lobi_botlar", row=0)
    async def bot_modu(self, interaction: discord.Interaction, button: Button):
        from src.game.manager import game_manager
        await game_manager.masa_kur(interaction, max_oyuncu=4, bot_modu=True)

    @discord.ui.button(label="Karışık Masa", style=discord.ButtonStyle.secondary, emoji="🎲", custom_id="lobi_karisik", row=0)
    async def karisik_masa(self, interaction: discord.Interaction, button: Button):
        from src.game.manager import game_manager
        await game_manager.masa_kur(interaction, max_oyuncu=4, bot_modu="karisik")

    @discord.ui.button(label="Bahisli VIP Masa", style=discord.ButtonStyle.danger, emoji="💰", custom_id="lobi_vip", row=1)
    async def vip_masa(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(VIPMasaModal())

    @discord.ui.button(label="Profilim & Sıralama", style=discord.ButtonStyle.secondary, emoji="📊", custom_id="lobi_profil", row=1)
    async def profil_bak(self, interaction: discord.Interaction, button: Button):
        from src.economy.db import ensure_oyuncu, get_liderlik
        from src.ui.render import render_profil
        oyuncu = await ensure_oyuncu(interaction.user.id, interaction.user.display_name)
        img_buf = render_profil(oyuncu)
        lider_tam = await get_liderlik("cip", 10)
        siralam = next((i+1 for i, o in enumerate(lider_tam) if o["user_id"] == interaction.user.id), "10+")
        lider_top3 = lider_tam[:3]

        toplam = oyuncu.get("toplam_mac", 0)
        galibiyet = oyuncu.get("galibiyet", 0)
        yenilgi = oyuncu.get("yenilgi", 0)
        oran = f"%{(galibiyet/toplam*100):.1f}" if toplam > 0 else "%0"
        cip = oyuncu.get("cip", 0)
        seviye = oyuncu.get("seviye", 1)

        seviye_ad = _seviye_adi(seviye)

        embed = discord.Embed(
            title=f"🎮 KAHVEHANE OKEY - OYUNCU PROFİLİ",
            color=0x2ecc71
        )
        embed.add_field(name="👤 Oyuncu", value=f"`{interaction.user.display_name}`", inline=True)
        embed.add_field(name="🏆 Lig / Seviye", value=f"{seviye_ad} ✨", inline=True)
        embed.add_field(name="🪙 Mevcut Çip", value=f"{cip:,} 🪙 *(VIP masalara girmek için kullanılır)*", inline=False)

        istat = (
            f"├ 🟢 Galibiyet: **{galibiyet}** Oyun\n"
            f"├ 🟡 Beraberlik: **0** Oyun\n"
            f"└ 🔴 Mağlubiyet: **{yenilgi}** Oyun\n"
            f"📈 Kazanma Oranı: **{oran}**"
        )
        embed.add_field(name="📊 İstatistikler:", value=istat, inline=False)
        embed.add_field(
            name="🏅 Sunucu Sıralaması",
            value=f"**#{siralam}. Sırada** *(Top 10 listesinde yer alıyorsun!)*",
            inline=False
        )

        if lider_top3:
            madalya = ["1️⃣", "2️⃣", "3️⃣"]
            lider_str = "\n".join(
                f"{madalya[i]} {o.get('ad','?')} - {o.get('cip',0):,} Çip {'🏆' if i==0 else '⭐' if i==1 else '✨'}"
                for i, o in enumerate(lider_top3)
            )
            embed.add_field(name="👑 TOP 3 LİDERLİK TABLOSU (SIRALAMA)", value=lider_str, inline=False)

        embed.set_image(url="attachment://profil.png")
        embed.set_footer(text="Kahvehane Okey Salonu • Kazanmaya devam et!")
        file = discord.File(img_buf, filename="profil.png")
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

def _seviye_adi(seviye: int) -> str:
    if seviye < 5:    return "🌱 Acemi Okeyci"
    if seviye < 10:   return "🎯 Çaylak Okeyci"
    if seviye < 20:   return "⚡ Usta Okeyci"
    if seviye < 35:   return "🔥 Uzman Okeyci"
    if seviye < 50:   return "💎 Elit Okeyci"
    return "👑 Efsane Okeyci"

class VIPMasaModal(Modal, title="💰 VIP Masa — Bahis Belirle"):
    bahis = TextInput(
        label="Bahis Miktarı (Çip)",
        placeholder="Örn: 500",
        min_length=1,
        max_length=10,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            miktar = int(self.bahis.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ Geçersiz miktar. Sayı girin.", ephemeral=True)
            return
        if miktar <= 0:
            await interaction.response.send_message("❌ Bahis 0'dan büyük olmalı.", ephemeral=True)
            return
        from src.economy.db import ensure_oyuncu
        from src.game.manager import game_manager
        oyuncu = await ensure_oyuncu(interaction.user.id, interaction.user.display_name)
        if oyuncu.get("cip", 0) < miktar:
            await interaction.response.send_message(
                f"❌ Yeterli çipiniz yok! Mevcut: **{oyuncu.get('cip', 0):,}** 🪙", ephemeral=True
            )
            return
        await game_manager.masa_kur(interaction, max_oyuncu=4, bot_modu=False, bahis=miktar)


class TasAtModal(Modal, title="🗑️ Hangi Taşı Atmak İstiyorsunuz?"):
    def __init__(self, masa_id: str):
        super().__init__()
        self.masa_id = masa_id

    renk_input = TextInput(
        label="Taşın Rengi",
        placeholder="kirmizi / sari / mavi / siyah",
        min_length=1,
        max_length=10,
        required=True
    )
    sayi_input = TextInput(
        label="Taşın Sayısı (1-13)",
        placeholder="Örn: 7",
        min_length=1,
        max_length=2,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        from src.game.okey_engine import COLOR_INPUT_MAP
        renk_raw = self.renk_input.value.strip().lower()
        renk = COLOR_INPUT_MAP.get(renk_raw)
        if not renk:
            await interaction.response.send_message(
                "❌ Geçersiz renk! `kirmizi`, `sari`, `mavi` veya `siyah` yazın.", ephemeral=True
            )
            return
        try:
            sayi = int(self.sayi_input.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ Geçersiz sayı. 1-13 arası bir sayı girin.", ephemeral=True)
            return
        if sayi < 1 or sayi > 13:
            await interaction.response.send_message("❌ Sayı 1 ile 13 arasında olmalı.", ephemeral=True)
            return
        from src.game.manager import game_manager
        await game_manager.tas_at_renk_sayi(interaction, self.masa_id, renk, sayi)


def build_masa_view(masa_id: str) -> View:
    view = View(timeout=None)

    async def katil_cb(interaction: discord.Interaction):
        from src.game.manager import game_manager
        await game_manager.masaya_katil(interaction, masa_id)

    async def per_cb(interaction: discord.Interaction):
        from src.game.manager import game_manager
        await game_manager.per_diz(interaction, masa_id)

    async def el_cb(interaction: discord.Interaction):
        from src.game.manager import game_manager
        await game_manager.el_goster(interaction, masa_id)

    async def talon_cb(interaction: discord.Interaction):
        from src.game.manager import game_manager
        await game_manager.talon_cek(interaction, masa_id)

    async def cop_cb(interaction: discord.Interaction):
        from src.game.manager import game_manager
        await game_manager.cop_cek(interaction, masa_id)

    async def at_cb(interaction: discord.Interaction):
        await interaction.response.send_modal(TasAtModal(masa_id))

    async def okey_cb(interaction: discord.Interaction):
        from src.game.manager import game_manager
        await game_manager.okey_ac(interaction, masa_id)

    async def baslat_cb(interaction: discord.Interaction):
        from src.game.manager import game_manager
        await game_manager.masayi_baslat(interaction, masa_id)

    async def ayril_cb(interaction: discord.Interaction):
        from src.game.manager import game_manager
        await game_manager.masadan_ayril(interaction, masa_id)

    b1 = Button(label="Masaya Katıl", style=discord.ButtonStyle.success, emoji="✅", custom_id=f"katil_{masa_id}", row=0)
    b1.callback = katil_cb
    b2 = Button(label="Perleri Diz", style=discord.ButtonStyle.secondary, emoji="🀄", custom_id=f"per_{masa_id}", row=0)
    b2.callback = per_cb
    b3 = Button(label="El Gör", style=discord.ButtonStyle.primary, emoji="👁️", custom_id=f"el_{masa_id}", row=0)
    b3.callback = el_cb
    b4 = Button(label="Talon'dan Çek", style=discord.ButtonStyle.primary, emoji="🎴", custom_id=f"talon_{masa_id}", row=1)
    b4.callback = talon_cb
    b5 = Button(label="Çöpten Al", style=discord.ButtonStyle.secondary, emoji="♻️", custom_id=f"cop_{masa_id}", row=1)
    b5.callback = cop_cb
    b6 = Button(label="Taş At", style=discord.ButtonStyle.danger, emoji="🗑️", custom_id=f"at_{masa_id}", row=1)
    b6.callback = at_cb
    b7 = Button(label="OKEY AÇ! 🏆", style=discord.ButtonStyle.success, emoji="🎉", custom_id=f"okey_{masa_id}", row=2)
    b7.callback = okey_cb
    b8 = Button(label="Masayı Başlat", style=discord.ButtonStyle.primary, emoji="▶️", custom_id=f"baslat_{masa_id}", row=2)
    b8.callback = baslat_cb
    b9 = Button(label="Masadan Ayrıl", style=discord.ButtonStyle.danger, emoji="🚪", custom_id=f"ayril_{masa_id}", row=2)
    b9.callback = ayril_cb

    for b in [b1, b2, b3, b4, b5, b6, b7, b8, b9]:
        view.add_item(b)

    return view
