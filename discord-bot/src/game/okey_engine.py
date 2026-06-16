import random
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

COLORS = ["kirmizi", "sari", "mavi", "siyah"]
COLOR_NAMES = {"kirmizi": "Kırmızı", "sari": "Sarı", "mavi": "Mavi", "siyah": "Siyah"}
COLOR_EMOJI = {"kirmizi": "🔴", "sari": "🟡", "mavi": "🔵", "siyah": "⚫"}
COLOR_HEX = {"kirmizi": "#E74C3C", "sari": "#F1C40F", "mavi": "#3498DB", "siyah": "#2C3E50"}

class GameState(Enum):
    WAITING = "waiting"
    PLAYING = "playing"
    FINISHED = "finished"

@dataclass
class Tas:
    renk: str
    sayi: int
    okey: bool = False

    def __str__(self):
        if self.okey:
            return "🃏OKEY"
        return f"{COLOR_EMOJI[self.renk]}{self.sayi}"

    def __eq__(self, other):
        if not isinstance(other, Tas):
            return False
        return self.renk == other.renk and self.sayi == other.sayi and self.okey == other.okey

    def __hash__(self):
        return hash((self.renk, self.sayi, self.okey))

def create_okey_set() -> list[Tas]:
    tas_seti = []
    for _ in range(2):
        for renk in COLORS:
            for sayi in range(1, 14):
                tas_seti.append(Tas(renk=renk, sayi=sayi))
    # 2 joker
    tas_seti.append(Tas(renk="kirmizi", sayi=0, okey=True))
    tas_seti.append(Tas(renk="sari", sayi=0, okey=True))
    return tas_seti

def determine_okey_tas(goster_tas: Tas) -> Tas:
    if goster_tas.okey:
        return Tas(renk="kirmizi", sayi=1)
    next_sayi = goster_tas.sayi + 1
    if next_sayi > 13:
        next_sayi = 1
    return Tas(renk=goster_tas.renk, sayi=next_sayi)

def sort_hand(el: list[Tas], okey_tas: Optional[Tas] = None) -> list[Tas]:
    def sort_key(t: Tas):
        if t.okey:
            return (99, 99, "")
        renk_order = {"kirmizi": 0, "sari": 1, "mavi": 2, "siyah": 3}
        is_okey = 0
        if okey_tas and t.renk == okey_tas.renk and t.sayi == okey_tas.sayi:
            is_okey = 1
        return (renk_order.get(t.renk, 9), t.sayi, is_okey)
    return sorted(el, key=sort_key)

def check_winner(el: list[Tas], okey_tas: Optional[Tas]) -> bool:
    if len(el) < 14:
        return False
    hand = [t for t in el if not t.okey]
    jokers = [t for t in el if t.okey]
    okeys = []
    if okey_tas:
        okeys = [t for t in hand if t.renk == okey_tas.renk and t.sayi == okey_tas.sayi]
        hand = [t for t in hand if not (t.renk == okey_tas.renk and t.sayi == okey_tas.sayi)]
    total_jokers = len(jokers) + len(okeys)
    return _can_form_sets(hand, total_jokers)

def _can_form_sets(hand: list[Tas], jokers: int) -> bool:
    if not hand and jokers >= 0:
        return True
    if len(hand) + jokers < 3:
        return False
    hand = sorted(hand, key=lambda t: (t.renk, t.sayi))
    for i in range(len(hand)):
        for set_size in [3, 4]:
            grp = _try_group(hand, i, set_size, jokers)
            if grp is not None:
                remaining = hand[:i] + hand[i+set_size:] if grp == "group_exact" else None
                if remaining is not None:
                    if _can_form_sets(remaining, jokers - (set_size - len([h for h in hand[i:i+set_size]]))):
                        return True
    return jokers >= len(hand) // 3

def _try_group(hand, start, size, jokers):
    if start + size > len(hand):
        return None
    subset = hand[start:start+size]
    if all(t.renk == subset[0].renk and t.sayi == subset[0].sayi for t in subset):
        return "group_exact"
    return None

@dataclass
class OkeyGame:
    masa_id: str
    oyuncular: list[int] = field(default_factory=list)
    oyuncu_elleri: dict[int, list[Tas]] = field(default_factory=dict)
    oyuncu_adlari: dict[int, str] = field(default_factory=dict)
    talon: list[Tas] = field(default_factory=list)
    cop_yigi: list[Tas] = field(default_factory=list)
    goster_tas: Optional[Tas] = None
    okey_tas: Optional[Tas] = None
    siradaki_oyuncu: int = 0
    durum: GameState = GameState.WAITING
    bahis: int = 0
    max_oyuncu: int = 4
    sifreli: bool = False
    sifre: str = ""
    kanal_id: Optional[int] = None
    mesaj_id: Optional[int] = None
    izleyiciler: list[int] = field(default_factory=list)
    bot_oyuncular: set[int] = field(default_factory=set)
    el_cekti: dict[int, bool] = field(default_factory=dict)

    def oyuncu_ekle(self, user_id: int, ad: str) -> bool:
        if user_id in self.oyuncular:
            return False
        if len(self.oyuncular) >= self.max_oyuncu:
            return False
        self.oyuncular.append(user_id)
        self.oyuncu_adlari[user_id] = ad
        self.el_cekti[user_id] = False
        return True

    def oyuncu_cikar(self, user_id: int) -> bool:
        if user_id not in self.oyuncular:
            return False
        self.oyuncular.remove(user_id)
        if user_id in self.oyuncu_elleri:
            self.talon.extend(self.oyuncu_elleri.pop(user_id))
            random.shuffle(self.talon)
        return True

    def doldur_botlarla(self):
        bot_ids = [-1, -2, -3, -4]
        bot_adlari = ["🤖 Bot Ahmet", "🤖 Bot Mehmet", "🤖 Bot Ayşe", "🤖 Bot Fatma"]
        for i, (bid, bad) in enumerate(zip(bot_ids, bot_adlari)):
            if len(self.oyuncular) >= self.max_oyuncu:
                break
            if bid not in self.oyuncular:
                self.oyuncular.append(bid)
                self.oyuncu_adlari[bid] = bad
                self.bot_oyuncular.add(bid)
                self.el_cekti[bid] = False

    def oyunu_baslat(self):
        if len(self.oyuncular) < 2:
            return False
        tas_seti = create_okey_set()
        random.shuffle(tas_seti)
        self.goster_tas = tas_seti.pop()
        self.okey_tas = determine_okey_tas(self.goster_tas)
        for oyuncu in self.oyuncular:
            self.oyuncu_elleri[oyuncu] = sort_hand(tas_seti[:14], self.okey_tas)
            tas_seti = tas_seti[14:]
        self.talon = tas_seti
        random.shuffle(self.talon)
        self.cop_yigi = []
        self.siradaki_oyuncu = 0
        self.durum = GameState.PLAYING
        return True

    def siradaki_oyuncu_id(self) -> Optional[int]:
        if not self.oyuncular:
            return None
        return self.oyuncular[self.siradaki_oyuncu % len(self.oyuncular)]

    def tas_cek(self, user_id: int) -> Optional[Tas]:
        if not self.talon:
            return None
        if self.siradaki_oyuncu_id() != user_id:
            return None
        if self.el_cekti.get(user_id):
            return None
        tas = self.talon.pop(0)
        self.oyuncu_elleri[user_id].append(tas)
        self.oyuncu_elleri[user_id] = sort_hand(self.oyuncu_elleri[user_id], self.okey_tas)
        self.el_cekti[user_id] = True
        return tas

    def cop_cek(self, user_id: int) -> Optional[Tas]:
        if not self.cop_yigi:
            return None
        if self.siradaki_oyuncu_id() != user_id:
            return None
        if self.el_cekti.get(user_id):
            return None
        tas = self.cop_yigi.pop()
        self.oyuncu_elleri[user_id].append(tas)
        self.oyuncu_elleri[user_id] = sort_hand(self.oyuncu_elleri[user_id], self.okey_tas)
        self.el_cekti[user_id] = True
        return tas

    def tas_at(self, user_id: int, tas_index: int) -> Optional[Tas]:
        if self.siradaki_oyuncu_id() != user_id:
            return None
        if not self.el_cekti.get(user_id):
            return None
        el = self.oyuncu_elleri.get(user_id, [])
        if tas_index < 0 or tas_index >= len(el):
            return None
        tas = el.pop(tas_index)
        self.cop_yigi.append(tas)
        self.el_cekti[user_id] = False
        self.siradaki_oyuncu = (self.siradaki_oyuncu + 1) % len(self.oyuncular)
        return tas

    def okey_ac(self, user_id: int) -> bool:
        if self.siradaki_oyuncu_id() != user_id:
            return False
        if not self.el_cekti.get(user_id):
            return False
        el = self.oyuncu_elleri.get(user_id, [])
        if check_winner(el, self.okey_tas):
            self.durum = GameState.FINISHED
            return True
        return False

    def peri_diz(self, user_id: int):
        if user_id not in self.oyuncu_elleri:
            return
        self.oyuncu_elleri[user_id] = sort_hand(self.oyuncu_elleri[user_id], self.okey_tas)

    def bot_hamle_yap(self, bot_id: int) -> Optional[Tas]:
        if self.siradaki_oyuncu_id() != bot_id:
            return None
        if not self.el_cekti.get(bot_id):
            if self.talon:
                self.tas_cek(bot_id)
            else:
                return None
        el = self.oyuncu_elleri.get(bot_id, [])
        if not el:
            return None
        if check_winner(el, self.okey_tas):
            self.durum = GameState.FINISHED
            return None
        atilacak_index = self._bot_en_kotu_tas(bot_id)
        return self.tas_at(bot_id, atilacak_index)

    def _bot_en_kotu_tas(self, bot_id: int) -> int:
        el = self.oyuncu_elleri.get(bot_id, [])
        if not el:
            return 0
        for i, tas in enumerate(el):
            if tas.okey:
                continue
            if self.okey_tas and tas.renk == self.okey_tas.renk and tas.sayi == self.okey_tas.sayi:
                continue
            puan = 0
            for j, diger in enumerate(el):
                if i == j:
                    continue
                if diger.renk == tas.renk and abs(diger.sayi - tas.sayi) <= 2:
                    puan += 1
                if diger.sayi == tas.sayi:
                    puan += 1
            if puan == 0:
                return i
        return len(el) - 1

    def el_str(self, user_id: int) -> str:
        el = self.oyuncu_elleri.get(user_id, [])
        if not el:
            return "Boş el"
        return " ".join([f"`{i+1}:{str(t)}`" for i, t in enumerate(el)])

    @property
    def doluluk(self) -> str:
        return f"{len(self.oyuncular)}/{self.max_oyuncu}"
