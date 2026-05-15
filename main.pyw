import sys
import re
import pyperclip
from pynput import keyboard, mouse
import tkinter as tk
from tkinter import messagebox
import time
import threading
import requests
import queue
from pathlib import Path


LOG_DOSYASI = Path(__file__).with_name("plankey.log")


def konsol_encoding_ayarla():
    """Terminal varsa UTF-8'e al; pythonw.exe altında sessizce geç."""
    for stream_adi in ("stdout", "stderr"):
        stream = getattr(sys, stream_adi, None)
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def log_yaz(*parcalar):
    """Konsol yokken de hata ayıklama için log dosyasına yaz."""
    mesaj = " ".join(str(parca) for parca in parcalar)
    stream = getattr(sys, "stdout", None)

    if stream:
        try:
            print(mesaj, file=stream, flush=True)
        except Exception:
            pass

    try:
        zaman = time.strftime("%Y-%m-%d %H:%M:%S")
        with LOG_DOSYASI.open("a", encoding="utf-8") as log:
            log.write(f"[{zaman}] {mesaj}\n")
    except Exception:
        pass


konsol_encoding_ayarla()


# --- AYARLAR ---
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_ADI = "gemma3:1b"  # Ana model - hızlı, GPU'ya sığıyor
TEXT_MODEL_CANDIDATES = [
    MODEL_ADI,
]

KISAYOL_METIN = keyboard.Key.f8  # Metin secimi icin kisayol
KISAYOL_CIKIS = keyboard.Key.f9  # Programi kapatmak icin kisayol


# Global değişkenler
root = None
gui_queue = queue.Queue()
kisayol_basildi = False
cikis_kisayolu_basildi = False
listener = None
klavye_kontrol = keyboard.Controller()
fare_kontrol = mouse.Controller()


def klavye_kisayolu(*tuslar):
    """Pynput ile güvenilir klavye kısayolu gönderir."""
    try:
        for tus in tuslar:
            klavye_kontrol.press(tus)
            time.sleep(0.02)
        for tus in reversed(tuslar):
            klavye_kontrol.release(tus)
            time.sleep(0.02)
        return True
    except Exception as e:
        log_yaz(f"Klavye kısayolu gönderilemedi: {e}")
        return False


# --- MENÜ SEÇENEKLERİ VE PROMPT'LAR ---
ISLEMLER = {
    # --- 📅 Sınav ve Ders Planlayıcı ---
    "📅 Sınav Çalışma Takvimi Oluştur": (
        "Sen profesyonel bir eğitim asistanısın. Seçili metinde belirtilen sınav konusunu, sınav tarihini ve "
        "adayın günlük ayırabileceği çalışma süresini analiz et. Kalan günlere mantıklı bir şekilde yayılmış, "
        "Pomodoro tekniğine uygun (25dk çalışma + 5dk mola) saat saat planlanmış detaylı bir takvim hazırla.\n\n"
        "KURAL - KESINLIKLE UYMAN GEREKEN FORMAT:\n"
        "- Yildiz (*) veya (**) KULLANMA\n"
        "- Markdown tablo (| sutun |) KULLANMA\n"
        "- # veya ## baslik KULLANMA\n"
        "- Her gunu buyuk harf ve tire ile ayir, ornek: --- PAZARTESI 12 MAYIS ---\n"
        "- Maddeleri satir basi tire (-) ile yaz\n"
        "- Saatleri açık yaz, ornek: 09:00-09:25 Konu: Turk Tarihi\n"
        "- Her gun arasina bos bir satir birak"
    ),
    "⏱️ Günlük Pomodoro Planı Yap": (
        "Seçili metindeki çalışma konularını veya notları analiz et. Bu konuları bugün çalışmak üzere "
        "25 dakikalık odaklanma ve 5 dakikalık mola periyotları (Pomodoro tekniği) şeklinde planla.\n\n"
        "KURAL - KESINLIKLE UYMAN GEREKEN FORMAT:\n"
        "- Yildiz (*) veya (**) KULLANMA\n"
        "- Markdown tablo (| sutun |) KULLANMA\n"
        "- # veya ## baslik KULLANMA\n"
        "- Saatleri açık yaz, ornek: 09:00-09:25 >> Konu Adı\n"
        "- Mola satirlarini açık yaz, ornek: 09:25-09:30 >> MOLA\n"
        "- Her pomodoro arasına bos satir birak\n"
        "- En sona toplam pomodoro sayisini yaz"
    ),
    "📊 Konu Analizi ve Dağılımı": (
        "Seçili metinde bahsedilen sınav veya ders içeriğini incele. Çalışılması gereken konuları "
        "stratejik önemlerine göre kategorize et. Taktikler ver.\n\n"
        "KURAL - KESINLIKLE UYMAN GEREKEN FORMAT:\n"
        "- Yildiz (*) veya (**) KULLANMA\n"
        "- Markdown tablo (| sutun |) KULLANMA\n"
        "- # veya ## baslik KULLANMA\n"
        "- Kategorileri buyuk harf ve tire ile ayir, ornek: === ONCELIKLI KONULAR ===\n"
        "- Maddeleri satir basi tire (-) veya numara ile yaz\n"
        "- Her kategori arasina bos satir birak"
    ),
}


def get_available_text_model():
    """Metin işlemede kullanılabilir modeli seçer."""
    preferred_models = []
    for model in TEXT_MODEL_CANDIDATES:
        if model and model not in preferred_models:
            preferred_models.append(model)

    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code != 200:
            return MODEL_ADI

        models = response.json().get("models", [])
        installed_lower = {m.get("name", "").lower(): m.get("name", "") for m in models}

        for candidate in preferred_models:
            candidate_lower = candidate.lower()
            if candidate_lower in installed_lower:
                return installed_lower[candidate_lower]

            candidate_base = candidate_lower.split(":")[0]
            for installed_name_lower, installed_name in installed_lower.items():
                if installed_name_lower.startswith(candidate_base + ":"):
                    return installed_name
    except Exception:
        pass

    return MODEL_ADI


def ollama_cevap_al(prompt):
    """Ollama API'den cevap al."""
    try:
        aktif_model = get_available_text_model()
        payload = {
            "model": aktif_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
            },
        }

        response = requests.post(OLLAMA_URL, json=payload, timeout=120)

        if response.status_code == 200:
            result = response.json()
            return result.get("response", "").strip()

        err_msg = (
            f"Ollama API Hatası: {response.status_code}\n"
            f"Model: {aktif_model}\n"
            f"Cevap: {response.text}\n\n"
            f"Model yüklü değilse şu komutu çalıştırın:\n"
            f"ollama pull {MODEL_ADI}"
        )
        log_yaz(f"❌ {err_msg}")
        gui_queue.put((messagebox.showerror, ("API Hatası", err_msg)))
        return None

    except requests.exceptions.ConnectionError:
        err_msg = (
            "Ollama'ya bağlanılamadı.\n"
            "Programın çalıştığından emin olun!\n"
            "(http://localhost:11434)"
        )
        log_yaz(f"❌ {err_msg}")
        gui_queue.put((messagebox.showerror, ("Bağlantı Hatası", err_msg)))
        return None
    except requests.exceptions.Timeout:
        err_msg = "Ollama zaman aşımına uğradı. Model meşgul olabilir; biraz sonra tekrar deneyin."
        log_yaz(f"❌ {err_msg}")
        gui_queue.put((messagebox.showerror, ("Zaman Aşımı", err_msg)))
        return None
    except Exception as e:
        err_msg = f"Beklenmeyen Hata: {e}"
        log_yaz(f"❌ {err_msg}")
        gui_queue.put((messagebox.showerror, ("Hata", err_msg)))
        return None


def strip_code_fence(text):
    if not text:
        return text
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = lines[1:] if lines else []
        while lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def markdown_temizle(text):
    """Markdown sembollerini temiz okunabilir metne dönüştürür."""
    if not text:
        return text
    satirlar = text.splitlines()
    temiz = []
    for satir in satirlar:
        # Tablo satirlarini atla
        if re.match(r'^\s*\|', satir) or re.match(r'^\s*[-|]+\s*$', satir):
            continue
        # ## Basliklar -> buyuk harf
        satir = re.sub(r'^#{1,6}\s+', '', satir)
        # **kalin** -> normal
        satir = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', satir)
        # __kalin__ -> normal
        satir = re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', satir)
        # `kod` -> normal
        satir = re.sub(r'`([^`]*)`', r'\1', satir)
        # > alcinti
        satir = re.sub(r'^\s*>+\s?', '', satir)
        temiz.append(satir)
    # Uc veya daha fazla bos satiri ikiye indir
    sonuc = re.sub(r'\n{3,}', '\n\n', '\n'.join(temiz))
    return sonuc.strip()


def secili_metni_kopyala(max_deneme=4):
    sentinel = f"__AI_ASISTAN__{time.time_ns()}__"
    onceki_pano = None
    pano_okunabildi = False

    try:
        onceki_pano = pyperclip.paste()
        pano_okunabildi = True
    except Exception:
        pass

    try:
        pyperclip.copy(sentinel)
    except Exception:
        pass

    for _ in range(max_deneme):
        klavye_kisayolu(keyboard.Key.ctrl, "c")
        time.sleep(0.2)
        metin = pyperclip.paste()
        if metin and metin.strip() and metin != sentinel:
            return metin

    if pano_okunabildi:
        try:
            pyperclip.copy(onceki_pano)
        except Exception:
            pass

    return ""


PENCERE_MODUNDA_ACILACAKLAR = (
    "Sınav Çalışma Takvimi Oluştur",
    "Günlük Pomodoro Planı Yap",
    "Konu Analizi ve Dağılımı",
)


def pencere_modunda_gosterilsin_mi(komut_adi):
    return any(anahtar in komut_adi for anahtar in PENCERE_MODUNDA_ACILACAKLAR)


def sonuc_penceresi_goster(baslik, icerik):
    pencere = tk.Toplevel(root)
    pencere.title(baslik)
    pencere.geometry("780x520")
    pencere.minsize(520, 320)
    pencere.attributes("-topmost", True)
    pencere.protocol("WM_DELETE_WINDOW", pencere.destroy)

    frame = tk.Frame(pencere, bg="#1f1f1f")
    frame.pack(fill="both", expand=True, padx=10, pady=10)

    text_alani = tk.Text(
        frame,
        wrap="word",
        bg="#2b2b2b",
        fg="white",
        insertbackground="white",
        font=("Segoe UI", 10),
        padx=10,
        pady=10,
    )
    kaydirma = tk.Scrollbar(frame, command=text_alani.yview)
    text_alani.configure(yscrollcommand=kaydirma.set)

    text_alani.pack(side="left", fill="both", expand=True)
    kaydirma.pack(side="right", fill="y")

    text_alani.insert("1.0", icerik)
    text_alani.config(state="disabled")

    alt_frame = tk.Frame(pencere, bg="#1f1f1f")
    alt_frame.pack(fill="x", padx=10, pady=(0, 10))

    def panoya_kopyala():
        pyperclip.copy(icerik)

    tk.Button(
        alt_frame,
        text="Panoya Kopyala",
        command=panoya_kopyala,
        bg="#3d3d3d",
        fg="white",
        activebackground="#4d4d4d",
        activeforeground="white",
        relief="flat",
        padx=12,
        pady=6,
    ).pack(side="left")

    tk.Button(
        alt_frame,
        text="Kapat",
        command=pencere.destroy,
        bg="#3d3d3d",
        fg="white",
        activebackground="#4d4d4d",
        activeforeground="white",
        relief="flat",
        padx=12,
        pady=6,
    ).pack(side="right")

    pencere.focus_force()
    pencere.lift()


def islemi_yap(komut_adi, secili_metin):
    prompt_emri = ISLEMLER[komut_adi]
    full_prompt = f"{prompt_emri}:\n\n'{secili_metin}'"

    log_yaz(f"🤖 İşlem: {komut_adi}")
    log_yaz("⏳ Ollama ile işleniyor...")

    sonuc = ollama_cevap_al(full_prompt)
    if not sonuc:
        log_yaz("❌ Sonuç alınamadı.")
        return

    sonuc = strip_code_fence(sonuc)
    sonuc = markdown_temizle(sonuc)
    if sonuc.startswith("'") and sonuc.endswith("'"):
        sonuc = sonuc[1:-1]

    if pencere_modunda_gosterilsin_mi(komut_adi):
        gui_queue.put((sonuc_penceresi_goster, (komut_adi, sonuc)))
        log_yaz("✅ Sonuç ayrı pencerede gösterildi.")
        return

    time.sleep(0.2)
    pyperclip.copy(sonuc)
    time.sleep(0.1)
    klavye_kisayolu(keyboard.Key.ctrl, "v")
    log_yaz("✅ İşlem tamamlandı!")


def process_queue():
    """Kuyruktaki GUI işlemlerini ana thread'de çalıştırır."""
    try:
        while True:
            try:
                task = gui_queue.get_nowait()
            except queue.Empty:
                break
            func, args = task
            try:
                func(*args)
            except Exception as e:
                log_yaz(f"GUI işlemi çalıştırılamadı: {e}")
            finally:
                gui_queue.task_done()
    finally:
        if root:
            root.after(100, process_queue)


def menu_goster():
    """Metni kopyalar ve menüyü gösterir (ana thread)."""
    secili_metin = secili_metni_kopyala()
    if not secili_metin.strip():
        gui_queue.put(
            (
                messagebox.showwarning,
                (
                    "Seçim Bulunamadı",
                    "Lütfen önce metin seçin, sonra F8 ile menüyü açın.",
                ),
            )
        )
        return

    menu = tk.Menu(
        root,
        tearoff=0,
        bg="#2b2b2b",
        fg="white",
        activebackground="#4a4a4a",
        activeforeground="white",
        font=("Segoe UI", 10),
    )

    def komut_olustur(k_adi, s_metin):
        def komut_calistir():
            threading.Thread(
                target=islemi_yap, args=(k_adi, s_metin), daemon=True
            ).start()

        return komut_calistir

    for baslik in ISLEMLER.keys():
        menu.add_command(label=baslik, command=komut_olustur(baslik, secili_metin))

    menu.add_separator()
    menu.add_command(label="PlanKey'i Kapat (F9)", command=cikis_onayi_goster)
    menu.add_command(label="❌ İptal", command=lambda: None)

    try:
        x, y = fare_kontrol.position
        menu.tk_popup(x, y)
    finally:
        menu.grab_release()


def on_press(key):
    global kisayol_basildi, cikis_kisayolu_basildi
    try:
        if key == KISAYOL_METIN and not kisayol_basildi:
            kisayol_basildi = True
            gui_queue.put((menu_goster, ()))
        elif key == KISAYOL_CIKIS and not cikis_kisayolu_basildi:
            cikis_kisayolu_basildi = True
            gui_queue.put((cikis_onayi_goster, ()))
    except AttributeError:
        pass


def on_release(key):
    global kisayol_basildi, cikis_kisayolu_basildi
    try:
        if key == KISAYOL_METIN:
            kisayol_basildi = False
        elif key == KISAYOL_CIKIS:
            cikis_kisayolu_basildi = False
    except AttributeError:
        pass


def uygulamayi_kapat():
    global listener
    log_yaz("PlanKey kapatılıyor...")
    if listener:
        listener.stop()
        listener = None
    if root:
        root.quit()
        root.destroy()


def cikis_onayi_goster():
    if messagebox.askyesno("PlanKey", "PlanKey kapatılsın mı?"):
        uygulamayi_kapat()


if __name__ == "__main__":
    log_yaz("=" * 60)
    log_yaz("🤖 PlanKey - Metin İşleme")
    log_yaz("=" * 60)
    aktif_text_model = get_available_text_model()
    log_yaz(f"📦 Metin İşleme (F8): {aktif_text_model}")
    log_yaz()
    log_yaz("🔧 Kullanım:")
    log_yaz("   F8 - Metin seç ve AI işlemleri yap")
    log_yaz("   F9 - PlanKey'i kapat")
    log_yaz()
    log_yaz("⚠️ Programı F9 ile kapatabilirsiniz.")
    log_yaz("=" * 60)

    try:
        test_response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if test_response.status_code == 200:
            log_yaz("✅ Ollama bağlantısı başarılı!")
        else:
            log_yaz("⚠️ Ollama'ya bağlanılamadı, servisi kontrol edin!")
    except Exception:
        log_yaz("⚠️ Ollama çalışmıyor olabilir! 'ollama serve' ile başlatın.")

    log_yaz()

    try:
        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()
    except Exception as e:
        log_yaz(f"Klavye dinleyicisi başlatılamadı: {e}")
        messagebox.showerror(
            "PlanKey",
            "Klavye dinleyicisi başlatılamadı.\n"
            "Programı yönetici olarak çalıştırmayı deneyin veya güvenlik izinlerini kontrol edin.",
        )
        raise

    root = tk.Tk()
    root.withdraw()
    root.after(100, process_queue)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        log_yaz("Kapatılıyor...")
