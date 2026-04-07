
import customtkinter as ctk
from tkinter import filedialog, messagebox, colorchooser
import tkinter as tk
import cv2
import numpy as np
import mss
import threading
import time
import datetime
import os
import sqlite3
from PIL import Image, ImageTk, ImageDraw, ImageFont
import json
from pynput import keyboard, mouse
import pyautogui
import sounddevice as sd
import soundfile as sf
from scipy.io import wavfile
import subprocess
from collections import deque
import schedule

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Renk sabitleri
BG_DARK = "#1a1a2e"
BG_MID = "#16213e"
ACCENT = "#0db3d0"
BTN_RED = "#dd1728"
BTN_GREEN = "#06d086"
BTN_BLUE = "#4361ee"
BTN_ORANGE = "#f77f00"
BTN_TEAL = "#2a9d8f"
TEXT_DIM = "#b4b4b4"


class ScreenRecorderPro:
    def __init__(self, root):
        self.root = root
        self.root.title("Aptoza")
        self.root.geometry("1000x800")
        self.root.configure(fg_color=BG_DARK)

        # Temel değişkenler
        self.is_recording = False
        self.is_paused = False
        self.recording_thread = None
        self.output_file = None
        self.video_writer = None
        self.start_time = None
        self.elapsed_time = 0
        self.fps = 30
        self.quality = 80
        self.record_mode = "fullscreen"
        self.selected_area = None

        # Ses özellikleri
        self.audio_enabled = True
        self.audio_source = "microphone"
        self.audio_thread = None
        self.sample_rate = 44100
        self.audio_file = None
        self.temp_video_file = None
        self.audio_done_event = threading.Event()

        # Webcam özellikleri
        self.webcam_enabled = False
        self.webcam_position = "bottom-right"
        self.webcam_size = 0.2
        self.webcam = None
        self.webcam_index = 0

        # Fare imleci vurgulama
        self.cursor_highlight = False
        self.cursor_color = "#008a00"
        self.cursor_size = 30
        self.mouse_pos = (0, 0)

        # Tuş basımları
        self.show_keystrokes = False
        self.keystroke_history = deque(maxlen=5)
        self.last_keystroke_time = 0

        # Video format
        self.video_format = "mp4"
        self.codec_map = {
            "mp4": "avc1",
            "avi": "XVID",
            "mkv": "XVID",
            "webm": "VP80"
        }

        # Watermark
        self.watermark_enabled = False
        self.watermark_text = " "
        self.watermark_image_path = None
        self.watermark_position = "bottom-right"
        self.watermark_opacity = 0.7

        # FPS sayacı
        self.show_fps_counter = False
        self.fps_history = deque(maxlen=30)
        self.actual_fps = 0

        # Zamanlayıcı
        self.scheduled_recording = False
        self.schedule_time = None
        self.schedule_duration = None

        # Gerçek FPS takibi (video/ses uzunluk uyumu için)
        self.video_frame_count = 0
        self.actual_record_fps = None
        self.video_record_start_time = None

        # ✅ FFmpeg kontrolü
        self.check_ffmpeg()

        # Veritabanı oluştur
        self.setup_database()

        # Ayarları yükle
        self.load_settings()

        # Hotkey listener
        self.setup_hotkeys()

        # Mouse listener
        self.setup_mouse_listener()

        # UI oluştur
        self.create_ui()

        # Önizleme güncelleme
        self.update_preview()

        # Ses seviyesi güncelleme
        self.update_audio_level()

        # Zamanlayıcı kontrolü
        self.check_schedule()

    # ------------------------------------------------------------------ #
    # Yardımcı: Bölüm çerçevesi
    # ------------------------------------------------------------------ #
    def _make_section(self, parent, title):
        outer = ctk.CTkFrame(parent, fg_color=BG_MID, corner_radius=8)
        outer.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(
            outer, text=title,
            font=("Segoe UI", 11, "bold"),
            text_color=ACCENT, fg_color="transparent"
        ).pack(anchor="w", padx=15, pady=(10, 4))
        return outer

    # ------------------------------------------------------------------ #
    # Sistem / Altyapı
    # ------------------------------------------------------------------ #
    def check_ffmpeg(self):
        try:
            result = subprocess.run(['ffmpeg', '-version'],
                                    capture_output=True, text=True)
            if result.returncode != 0:
                messagebox.showwarning(
                    "Uyarı",
                    "FFmpeg yüklü değil veya PATH'te yok!\n"
                    "Video düzenleme özellikleri çalışmayabilir.\n"
                    "https://ffmpeg.org/download.html adresinden indirebilirsiniz."
                )
                return False
            return True
        except:
            messagebox.showwarning("Uyarı", "FFmpeg bulunamadı!")
            return False

    def setup_database(self):
        self.conn = sqlite3.connect('screen_recorder_pro.db')
        self.cursor = self.conn.cursor()

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                filepath TEXT NOT NULL,
                duration INTEGER,
                filesize INTEGER,
                resolution TEXT,
                fps INTEGER,
                format TEXT,
                has_audio INTEGER,
                has_webcam INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        self.conn.commit()

    def load_settings(self):
        self.cursor.execute('SELECT key, value FROM settings')
        settings = dict(self.cursor.fetchall())

        if 'fps' in settings: self.fps = int(settings['fps'])
        if 'quality' in settings: self.quality = int(settings['quality'])
        if 'save_directory' in settings:
            self.save_directory = settings['save_directory']
        else:
            self.save_directory = os.path.expanduser("~/Videos/ScreenRecorderPro")
            os.makedirs(self.save_directory, exist_ok=True)
        if 'video_format' in settings: self.video_format = settings['video_format']
        if 'watermark_text' in settings: self.watermark_text = settings['watermark_text']

    def save_settings(self):
        settings = {
            'fps': str(self.fps),
            'quality': str(self.quality),
            'save_directory': self.save_directory,
            'video_format': self.video_format,
            'watermark_text': self.watermark_text
        }
        for key, value in settings.items():
            self.cursor.execute(
                'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
                (key, value)
            )
        self.conn.commit()

    def setup_hotkeys(self):
        def on_press(key):
            try:
                if key == keyboard.Key.f9:
                    self.toggle_recording()
                elif key == keyboard.Key.f10:
                    self.take_screenshot()
                elif key == keyboard.Key.f11 and self.is_recording:
                    self.toggle_pause()

                if self.show_keystrokes and self.is_recording:
                    key_name = self.get_key_name(key)
                    if key_name:
                        self.keystroke_history.append({'key': key_name, 'time': time.time()})
            except:
                pass

        self.hotkey_listener = keyboard.Listener(on_press=on_press)
        self.hotkey_listener.start()

    def get_key_name(self, key):
        try:
            if hasattr(key, 'char') and key.char:
                return key.char.upper()
            elif hasattr(key, 'name'):
                return key.name.upper()
        except:
            pass
        return None

    def setup_mouse_listener(self):
        def on_move(x, y):
            self.mouse_pos = (x, y)
        self.mouse_listener = mouse.Listener(on_move=on_move)
        self.mouse_listener.start()

    def get_audio_devices(self):
        devices = sd.query_devices()
        input_devices = []
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                input_devices.append({
                    'index': i,
                    'name': device['name'],
                    'channels': device['max_input_channels']
                })
        return input_devices

    # ✅ Ses verileri RAM'de birikmiyor, doğrudan diske yazılıyor.
    def record_audio(self):
        self.audio_done_event.clear()
        try:
            device_info = sd.query_devices(kind='input')
            channels = min(2, device_info['max_input_channels'])
            if channels < 1: channels = 1
        except Exception:
            channels = 1

        try:
            with sf.SoundFile(self.audio_file, mode='x', samplerate=self.sample_rate,
                              channels=channels, subtype='PCM_16') as wav_file:
                def callback(indata, frames, time_info, status):
                    if status:
                        print(f"Ses kaydı durumu: {status}")
                    if self.is_recording and not self.is_paused:
                        wav_file.write(indata)  # Disk'e anlık yaz

                with sd.InputStream(samplerate=self.sample_rate, channels=channels,
                                    dtype='float32', callback=callback, blocksize=1024):
                    while self.is_recording:
                        sd.sleep(50)
        except Exception as e:
            print(f"Ses kaydı hatası: {e}")
            self.audio_file = None
        finally:
            self.audio_done_event.set()

    # ✅ Gerçek kayıt FPS'i kullanılarak video/ses uzunluk uyumsuzluğu giderildi.
    def merge_audio_video(self, video_file, audio_file, output_file, actual_fps=None):
        try:
            # Gerçek FPS biliniyorsa FFmpeg'e bildir; aksi hâlde video header'ından okur.
            # Bu, VideoWriter'ın hedef FPS ile gerçek yakalama FPS'i arasındaki
            # farktan kaynaklanan video hızlanması sorununu çözer.
            input_fps = actual_fps if (actual_fps and actual_fps > 0) else None

            cmd = ['ffmpeg', '-y']
            if input_fps:
                cmd += ['-r', f'{input_fps:.6f}']   # giriş videosunun gerçek FPS'i
            cmd += [
                '-i', video_file,
                '-i', audio_file,
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23',
                '-r', str(self.fps),                  # çıkış FPS'i hedef değerde
                '-c:a', 'aac', '-b:a', '192k',
                '-map', '0:v:0', '-map', '1:a:0',
                output_file
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"FFmpeg stderr: {result.stderr}")
                raise Exception(result.stderr)

            if os.path.exists(video_file): os.remove(video_file)
            if os.path.exists(audio_file): os.remove(audio_file)
            return True
        except subprocess.TimeoutExpired:
            print("FFmpeg zaman aşımına uğradı!")
            return False
        except Exception as e:
            print(f"Video birleştirme hatası: {e}")
            return False

    # ------------------------------------------------------------------ #
    # UI Oluşturma
    # ------------------------------------------------------------------ #
    def create_ui(self):
        self.tabview = ctk.CTkTabview(self.root, fg_color=BG_MID,
            segmented_button_fg_color=BG_DARK, segmented_button_selected_color=BTN_BLUE,
            segmented_button_selected_hover_color="#3050dd", segmented_button_unselected_hover_color="#2a2a4e",
            text_color="white", corner_radius=8)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        self.tabview.add("📹 Kayıt")
        self.tabview.add("⚙️ Ayarlar")
        self.tabview.add("✂️ Video Düzenle")

        self.tabview.tab("📹 Kayıt").configure(fg_color=BG_DARK)
        self.tabview.tab("⚙️ Ayarlar").configure(fg_color=BG_DARK)
        self.tabview.tab("✂️ Video Düzenle").configure(fg_color=BG_DARK)

        self.create_main_tab(self.tabview.tab("📹 Kayıt"))
        self.create_advanced_tab(self.tabview.tab("⚙️ Ayarlar"))
        self.create_editor_tab(self.tabview.tab("✂️ Video Düzenle"))

    def create_main_tab(self, parent):
        title_frame = ctk.CTkFrame(parent, fg_color="transparent")
        title_frame.pack(fill="x", pady=(10, 20))
        ctk.CTkLabel(title_frame, text="", font=("Segoe UI", 20, "bold"), text_color=ACCENT, fg_color="transparent").pack(side="left")

        preview_frame = ctk.CTkFrame(parent, fg_color=BG_MID, corner_radius=8)
        preview_frame.pack(fill="both", expand=True, pady=(0, 15), padx=10)
        self.preview_label = tk.Label(preview_frame, bg=BG_MID, text="Önizleme", font=("Segoe UI", 11), fg=TEXT_DIM)
        self.preview_label.pack(fill="both", expand=True, padx=8, pady=8)

        status_frame = ctk.CTkFrame(parent, fg_color=BG_MID, corner_radius=8, height=45)
        status_frame.pack(fill="x", pady=(0, 15), padx=10)
        status_frame.pack_propagate(False)
        self.status_label = ctk.CTkLabel(status_frame, text="⚫ Hazır", font=("Segoe UI", 10), text_color=TEXT_DIM, fg_color="transparent", anchor="w")
        self.status_label.pack(side="left", fill="both", expand=True, padx=12)
        self.timer_label = ctk.CTkLabel(status_frame, text="00:00:00", font=("Segoe UI", 13, "bold"), text_color=ACCENT, fg_color="transparent")
        self.timer_label.pack(side="right", padx=12)

        control_frame = ctk.CTkFrame(parent, fg_color="transparent")
        control_frame.pack(fill="x", pady=(0, 15), padx=10)
        self.record_btn = ctk.CTkButton(control_frame, text="● Kayıt Başlat", fg_color=BTN_RED, hover_color="#b90111", text_color="white", font=("Segoe UI", 10, "bold"), corner_radius=6, width=130, command=self.toggle_recording)
        self.record_btn.pack(side="left", padx=4)
        self.pause_btn = ctk.CTkButton(control_frame, text="⏸ Duraklat", fg_color=BTN_ORANGE, hover_color="#d46a00", text_color="white", font=("Segoe UI", 10, "bold"), corner_radius=6, width=110, state="disabled", command=self.toggle_pause)
        self.pause_btn.pack(side="left", padx=4)
        ctk.CTkButton(control_frame, text="📷 Screenshot", fg_color=BTN_GREEN, hover_color="#04d98e", text_color=BG_DARK, font=("Segoe UI", 10, "bold"), corner_radius=6, width=120, command=self.take_screenshot).pack(side="left", padx=4)
        ctk.CTkButton(control_frame, text="⚙ Ayarlar", fg_color=BTN_BLUE, hover_color="#0027d5", text_color="white", font=("Segoe UI", 10, "bold"), corner_radius=6, width=100, command=self.open_settings).pack(side="left", padx=4)

        options_frame = ctk.CTkFrame(parent, fg_color=BG_MID, corner_radius=8)
        options_frame.pack(fill="x", padx=10, pady=(0, 10))
        mode_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        mode_frame.pack(side="left", fill="both", expand=True, padx=5, pady=10)
        ctk.CTkLabel(mode_frame, text="Kayıt Modu:", font=("Segoe UI", 9, "bold"), text_color=ACCENT, fg_color="transparent").pack(anchor="w", padx=10)
        self.mode_var = tk.StringVar(value="fullscreen")
        for text, value in [("🖥 Tam Ekran", "fullscreen"), ("⬚ Alan Seç", "area")]:
            ctk.CTkRadioButton(mode_frame, text=text, variable=self.mode_var, value=value, font=("Segoe UI", 9), text_color="white", fg_color=BTN_BLUE, hover_color="#3050dd", command=self.change_record_mode).pack(anchor="w", padx=20)

        audio_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        audio_frame.pack(side="left", fill="both", expand=True, padx=5, pady=10)
        self.audio_var = tk.BooleanVar(value=self.audio_enabled)
        ctk.CTkCheckBox(audio_frame, text="🎤 Ses Kaydı", variable=self.audio_var, font=("Segoe UI", 9, "bold"), text_color=ACCENT, fg_color=BTN_BLUE, hover_color="#3050dd", command=self.toggle_audio).pack(anchor="w", padx=10)
        self.audio_source_var = tk.StringVar(value=self.audio_source)
        for text, value in [("🎤 Mikrofon", "microphone"), ("🔊 Sistem", "system"), ("🎵 Her İkisi", "both")]:
            ctk.CTkRadioButton(audio_frame, text=text, variable=self.audio_source_var, value=value, font=("Segoe UI", 10), text_color="white", fg_color=BTN_BLUE, hover_color="#3050dd", command=self.change_audio_source).pack(anchor="w", padx=20)

        hotkey_frame = ctk.CTkFrame(parent, fg_color="transparent")
        hotkey_frame.pack(fill="x", padx=10, pady=(10, 0))
        ctk.CTkLabel(hotkey_frame, text=" F9: Kayıt |  F10: Screenshot |  F11: Duraklat", font=("Segoe UI", 10), text_color="white", fg_color="transparent").pack()

    def create_advanced_tab(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color=BG_DARK, corner_radius=0)
        scroll.pack(fill="both", expand=True)
        self.create_webcam_section(scroll)
        self.create_cursor_section(scroll)
        self.create_keystroke_section(scroll)
        self.create_format_section(scroll)
        self.create_watermark_section(scroll)
        self.create_misc_section(scroll)

    def create_webcam_section(self, parent):
        section = self._make_section(parent, "📹 Webcam Ayarları")
        self.webcam_var = tk.BooleanVar(value=self.webcam_enabled)
        ctk.CTkCheckBox(section, text="Webcam Overlay Aktif", variable=self.webcam_var, font=("Segoe UI", 10), text_color="white", fg_color=BTN_BLUE, hover_color="#3050dd", command=self.toggle_webcam).pack(anchor="w", padx=15, pady=5)
        pos_frame = ctk.CTkFrame(section, fg_color="transparent")
        pos_frame.pack(fill="x", padx=15, pady=5)
        ctk.CTkLabel(pos_frame, text="Konum: ", font=("Segoe UI", 9), text_color="white", fg_color="transparent").pack(side="left", padx=5)
        self.webcam_pos_var = tk.StringVar(value=self.webcam_position)
        for text, value in [("↖ Sol Üst", "top-left"), ("↗ Sağ Üst", "top-right"), ("↙ Sol Alt", "bottom-left"), ("↘ Sağ Alt", "bottom-right")]:
            ctk.CTkRadioButton(pos_frame, text=text, variable=self.webcam_pos_var, value=value, font=("Segoe UI", 10), text_color="white", fg_color=BTN_BLUE, hover_color="#3050dd").pack(side="left", padx=3)
        size_frame = ctk.CTkFrame(section, fg_color="transparent")
        size_frame.pack(fill="x", padx=15, pady=(5, 15))
        ctk.CTkLabel(size_frame, text="Boyut (Ekranın %): ", font=("Segoe UI", 9), text_color="white", fg_color="transparent").pack(side="left", padx=5)
        self.webcam_size_var = tk.IntVar(value=int(self.webcam_size * 100))
        ctk.CTkSlider(size_frame, from_=10, to=40, variable=self.webcam_size_var, fg_color=BG_DARK, progress_color=BTN_BLUE, button_color=ACCENT, button_hover_color="#00b8d4", orientation="horizontal").pack(side="left", fill="x", expand=True, padx=5)

    def create_cursor_section(self, parent):
        section = self._make_section(parent, "🖱️ Fare İmleci Vurgulama")
        self.cursor_var = tk.BooleanVar(value=self.cursor_highlight)
        ctk.CTkCheckBox(section, text="Fare İmlecini Vurgula", variable=self.cursor_var, font=("Segoe UI", 10), text_color="white", fg_color=BTN_BLUE, hover_color="#3050dd", command=self.toggle_cursor_highlight).pack(anchor="w", padx=15, pady=5)
        color_frame = ctk.CTkFrame(section, fg_color="transparent")
        color_frame.pack(fill="x", padx=15, pady=5)
        ctk.CTkLabel(color_frame, text="Vurgu Rengi: ", font=("Segoe UI", 9), text_color="white", fg_color="transparent").pack(side="left", padx=5)
        ctk.CTkButton(color_frame, text="Renk Seç", font=("Segoe UI", 9), fg_color=self.cursor_color, hover_color="#017001", text_color="white", corner_radius=6, width=90, command=self.choose_cursor_color).pack(side="left", padx=5)
        size_frame = ctk.CTkFrame(section, fg_color="transparent")
        size_frame.pack(fill="x", padx=15, pady=(5, 15))
        ctk.CTkLabel(size_frame, text="Vurgu Boyutu: ", font=("Segoe UI", 9), text_color="white", fg_color="transparent").pack(side="left", padx=5)
        self.cursor_size_var = tk.IntVar(value=self.cursor_size)
        ctk.CTkSlider(size_frame, from_=20, to=60, variable=self.cursor_size_var, fg_color=BG_DARK, progress_color=BTN_BLUE, button_color=ACCENT, button_hover_color="#00b8d4", orientation="horizontal").pack(side="left", fill="x", expand=True, padx=5)

    def create_keystroke_section(self, parent):
        section = self._make_section(parent, "⌨️ Tuş Basımlarını Göster")
        self.keystroke_var = tk.BooleanVar(value=self.show_keystrokes)
        ctk.CTkCheckBox(section, text="Basılan Tuşları Göster", variable=self.keystroke_var, font=("Segoe UI", 10), text_color="white", fg_color=BTN_BLUE, hover_color="#3050dd", command=self.toggle_keystrokes).pack(anchor="w", padx=15, pady=5)
        ctk.CTkLabel(section, text="Tutorial ve eğitim videolarında yararlıdır", font=("Segoe UI", 8), text_color=TEXT_DIM, fg_color="transparent").pack(anchor="w", padx=15, pady=(0, 12))

    def create_format_section(self, parent):
        section = self._make_section(parent, "🎬 Video Formatı")
        self.format_var = tk.StringVar(value=self.video_format)
        for text, value in [("MP4 (H.264)", "mp4"), ("AVI (XVID)", "avi"), ("MKV (X264)", "mkv"), ("WebM (VP8)", "webm")]:
            ctk.CTkRadioButton(section, text=text, variable=self.format_var, value=value, font=("Segoe UI", 9), text_color="white", fg_color=BTN_BLUE, hover_color="#3050dd", command=self.change_format).pack(anchor="w", padx=15, pady=2)
        ctk.CTkFrame(section, fg_color="transparent", height=8).pack()

    def create_watermark_section(self, parent):
        section = self._make_section(parent, "💧 Watermark")
        self.watermark_var = tk.BooleanVar(value=self.watermark_enabled)
        ctk.CTkCheckBox(section, text="Watermark Ekle", variable=self.watermark_var, font=("Segoe UI", 10), text_color="white", fg_color=BTN_BLUE, hover_color="#3050dd", command=self.toggle_watermark).pack(anchor="w", padx=15, pady=5)
        text_frame = ctk.CTkFrame(section, fg_color="transparent")
        text_frame.pack(fill="x", padx=15, pady=5)
        ctk.CTkLabel(text_frame, text="Metin: ", font=("Segoe UI", 9), text_color="white", fg_color="transparent").pack(side="left", padx=5)
        self.watermark_entry = ctk.CTkEntry(text_frame, font=("Segoe UI", 9), fg_color=BG_DARK, text_color="white", border_color=BTN_BLUE, corner_radius=6)
        self.watermark_entry.insert(0, self.watermark_text)
        self.watermark_entry.pack(side="left", fill="x", expand=True, padx=5)
        img_frame = ctk.CTkFrame(section, fg_color="transparent")
        img_frame.pack(fill="x", padx=15, pady=5)
        ctk.CTkButton(img_frame, text="📁 Logo Seç", font=("Segoe UI", 9), fg_color=BTN_BLUE, hover_color="#3050dd", text_color="white", corner_radius=6, width=100, command=self.choose_watermark_image).pack(side="left", padx=5)
        pos_frame = ctk.CTkFrame(section, fg_color="transparent")
        pos_frame.pack(fill="x", padx=15, pady=(5, 12))
        ctk.CTkLabel(pos_frame, text="Konum: ", font=("Segoe UI", 9), text_color="white", fg_color="transparent").pack(side="left", padx=5)
        self.watermark_pos_var = tk.StringVar(value=self.watermark_position)
        for text, value in [("↖", "top-left"), ("↗", "top-right"), ("↙", "bottom-left"), ("↘", "bottom-right")]:
            ctk.CTkRadioButton(pos_frame, text=text, variable=self.watermark_pos_var, value=value, font=("Segoe UI", 9), text_color="white", fg_color=BTN_BLUE, hover_color="#3050dd").pack(side="left", padx=3)

    def create_misc_section(self, parent):
        section = self._make_section(parent, "🔧 Diğer Özellikler")
        self.fps_counter_var = tk.BooleanVar(value=self.show_fps_counter)
        ctk.CTkCheckBox(section, text="FPS Sayacını Göster", variable=self.fps_counter_var, font=("Segoe UI", 10), text_color="white", fg_color=BTN_BLUE, hover_color="#3050dd", command=self.toggle_fps_counter).pack(anchor="w", padx=15, pady=5)
        scheduler_frame = ctk.CTkFrame(section, fg_color="transparent")
        scheduler_frame.pack(fill="x", padx=15, pady=10)
        ctk.CTkLabel(scheduler_frame, text="⏰ Otomatik Kayıt Zamanlayıcı: ", font=("Segoe UI", 10, "bold"), text_color="white", fg_color="transparent").pack(anchor="w", pady=5)
        ctk.CTkButton(scheduler_frame, text="Zamanlayıcı Ayarla", font=("Segoe UI", 9), fg_color=BTN_ORANGE, hover_color="#ac5600", text_color="white", corner_radius=6, width=160, command=self.open_scheduler).pack(anchor="w", padx=20, pady=5)
        ctk.CTkFrame(section, fg_color="transparent", height=8).pack()

    def create_editor_tab(self, parent):
        ctk.CTkLabel(parent, text="✂️ Video Düzenleyici", font=("Segoe UI", 16, "bold"), text_color=ACCENT, fg_color="transparent").pack(pady=20)
        select_frame = ctk.CTkFrame(parent, fg_color=BG_MID, corner_radius=8)
        select_frame.pack(fill="x", padx=20, pady=10)
        inner_sel = ctk.CTkFrame(select_frame, fg_color="transparent")
        inner_sel.pack(fill="x", padx=20, pady=15)
        ctk.CTkLabel(inner_sel, text="Video Dosyası: ", font=("Segoe UI", 10), text_color="white", fg_color="transparent").pack(side="left", padx=5)
        self.editor_file_entry = ctk.CTkEntry(inner_sel, font=("Segoe UI", 10), fg_color=BG_DARK, text_color="white", border_color=BTN_BLUE, corner_radius=6)
        self.editor_file_entry.pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkButton(inner_sel, text="📂 Seç", font=("Segoe UI", 9), fg_color=BTN_BLUE, hover_color="#3050dd", text_color="white", corner_radius=6, width=80, command=self.select_video_for_edit).pack(side="left", padx=5)
        options_frame = ctk.CTkFrame(parent, fg_color=BG_MID, corner_radius=8)
        options_frame.pack(fill="both", expand=True, padx=20, pady=10)
        inner_opt = ctk.CTkFrame(options_frame, fg_color="transparent")
        inner_opt.pack(fill="both", expand=True, padx=20, pady=15)
        ctk.CTkButton(inner_opt, text="✂️ Video Kırp (Başlangıç/Bitiş)", font=("Segoe UI", 11, "bold"), fg_color=BTN_RED, hover_color="#fb3a4a", text_color="white", corner_radius=8, height=50, command=self.trim_video).pack(fill="x", pady=5)
        ctk.CTkButton(inner_opt, text="🔗 Videoları Birleştir", font=("Segoe UI", 11, "bold"), fg_color=BTN_TEAL, hover_color="#00d4bb", text_color="white", corner_radius=8, height=50, command=self.merge_videos).pack(fill="x", pady=5)
        ctk.CTkButton(inner_opt, text="🔄 Format Dönüştür", font=("Segoe UI", 11, "bold"), fg_color=BTN_ORANGE, hover_color="#fe9329", text_color="white", corner_radius=8, height=50, command=self.convert_format).pack(fill="x", pady=5)
        ctk.CTkLabel(parent, text="💡 İpucu: FFmpeg yüklü olmalıdır", font=("Segoe UI", 11), text_color="white", fg_color="transparent").pack(pady=10)

    # ------------------------------------------------------------------ #
    # Callback metodları
    # ------------------------------------------------------------------ #
    def toggle_audio(self): self.audio_enabled = self.audio_var.get()
    def change_audio_source(self): self.audio_source = self.audio_source_var.get()
    def toggle_webcam(self):
        # Sadece kullanıcının seçimini kaydet, kamerayı şimdi açmaya çalışma.
        # Kamera kayıt başladığında (start_recording) açılacak.
        self.webcam_enabled = self.webcam_var.get()
    def toggle_cursor_highlight(self): self.cursor_highlight = self.cursor_var.get()
    def choose_cursor_color(self):
        color = colorchooser.askcolor(initialcolor=self.cursor_color)
        if color[1]: self.cursor_color = color[1]
    def toggle_keystrokes(self): self.show_keystrokes = self.keystroke_var.get()
    def change_format(self): self.video_format = self.format_var.get()
    def toggle_watermark(self): self.watermark_enabled = self.watermark_var.get()
    def choose_watermark_image(self):
        filepath = filedialog.askopenfilename(title="Logo Seç", filetypes=[("Image files", "*.png *.jpg *.jpeg")])
        if filepath: self.watermark_image_path = filepath; messagebox.showinfo("Başarılı", f"Logo seçildi: {os.path.basename(filepath)}")
    def toggle_fps_counter(self): self.show_fps_counter = self.fps_counter_var.get()

    def open_scheduler(self):
        scheduler_window = ctk.CTkToplevel(self.root)
        scheduler_window.title("Otomatik Kayıt Zamanlayıcı")
        scheduler_window.geometry("400x400")
        scheduler_window.configure(fg_color=BG_DARK)
        scheduler_window.transient(self.root)
        ctk.CTkLabel(scheduler_window, text="⏰ Kayıt Zamanlayıcısı", font=("Segoe UI", 14, "bold"), text_color=ACCENT, fg_color="transparent").pack(pady=20)
        time_frame = ctk.CTkFrame(scheduler_window, fg_color=BG_MID, corner_radius=8)
        time_frame.pack(fill="x", padx=20, pady=10)
        inner_t = ctk.CTkFrame(time_frame, fg_color="transparent")
        inner_t.pack(fill="x", padx=20, pady=15)
        ctk.CTkLabel(inner_t, text="Başlangıç Saati (HH:MM): ", font=("Segoe UI", 10), text_color="white", fg_color="transparent").pack(anchor="w", pady=5)
        time_entry = ctk.CTkEntry(inner_t, font=("Segoe UI", 10), fg_color=BG_DARK, text_color="white", border_color=BTN_BLUE, corner_radius=6)
        time_entry.insert(0, "14:30"); time_entry.pack(fill="x", pady=5)
        duration_frame = ctk.CTkFrame(scheduler_window, fg_color=BG_MID, corner_radius=8)
        duration_frame.pack(fill="x", padx=20, pady=10)
        inner_d = ctk.CTkFrame(duration_frame, fg_color="transparent")
        inner_d.pack(fill="x", padx=20, pady=15)
        ctk.CTkLabel(inner_d, text="Kayıt Süresi (dakika): ", font=("Segoe UI", 10), text_color="white", fg_color="transparent").pack(anchor="w", pady=5)
        duration_entry = ctk.CTkEntry(inner_d, font=("Segoe UI", 10), fg_color=BG_DARK, text_color="white", border_color=BTN_BLUE, corner_radius=6)
        duration_entry.insert(0, "30"); duration_entry.pack(fill="x", pady=5)
        def set_schedule():
            try:
                time_str = time_entry.get(); duration = int(duration_entry.get())
                self.schedule_time = time_str; self.schedule_duration = duration; self.scheduled_recording = True
                messagebox.showinfo("Başarılı", f"Kayıt {time_str} saatinde {duration} dakika sürecek şekilde zamanlandı!"); scheduler_window.destroy()
            except: messagebox.showerror("Hata", "Geçersiz format!")
        ctk.CTkButton(scheduler_window, text="✓ Zamanla", font=("Segoe UI", 11, "bold"), fg_color=BTN_GREEN, hover_color="#04d98e", text_color=BG_DARK, corner_radius=8, width=140, height=40, command=set_schedule).pack(pady=20)

    def check_schedule(self):
        if self.scheduled_recording and self.schedule_time:
            current_time = datetime.datetime.now().strftime("%H:%M")
            if current_time == self.schedule_time and not self.is_recording:
                self.start_recording()
                if self.schedule_duration: self.root.after(self.schedule_duration * 60 * 1000, self.stop_recording)
                self.scheduled_recording = False
        self.root.after(30000, self.check_schedule)

    def select_video_for_edit(self):
        filepath = filedialog.askopenfilename(title="Video Seç", filetypes=[("Video files", "*.mp4 *.avi *.mkv *.webm")])
        if filepath: self.editor_file_entry.delete(0, tk.END); self.editor_file_entry.insert(0, filepath)

    def trim_video(self):
        video_path = self.editor_file_entry.get()
        if not video_path or not os.path.exists(video_path): messagebox.showerror("Hata", "Lütfen geçerli bir video dosyası seçin!"); return
        trim_window = ctk.CTkToplevel(self.root); trim_window.title("Video Kırp"); trim_window.geometry("400x280"); trim_window.configure(fg_color=BG_DARK)
        ctk.CTkLabel(trim_window, text="✂️ Video Kırpma", font=("Segoe UI", 14, "bold"), text_color=ACCENT, fg_color="transparent").pack(pady=20)
        start_frame = ctk.CTkFrame(trim_window, fg_color=BG_MID, corner_radius=8); start_frame.pack(fill="x", padx=20, pady=5)
        inner_s = ctk.CTkFrame(start_frame, fg_color="transparent"); inner_s.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(inner_s, text="Başlangıç (saniye): ", font=("Segoe UI", 10), text_color="white", fg_color="transparent").pack(side="left", padx=5)
        start_entry = ctk.CTkEntry(inner_s, font=("Segoe UI", 10), fg_color=BG_DARK, text_color="white", border_color=BTN_BLUE, corner_radius=6, width=80); start_entry.insert(0, "0"); start_entry.pack(side="left", padx=5)
        end_frame = ctk.CTkFrame(trim_window, fg_color=BG_MID, corner_radius=8); end_frame.pack(fill="x", padx=20, pady=5)
        inner_e = ctk.CTkFrame(end_frame, fg_color="transparent"); inner_e.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(inner_e, text="Bitiş (saniye): ", font=("Segoe UI", 10), text_color="white", fg_color="transparent").pack(side="left", padx=5)
        end_entry = ctk.CTkEntry(inner_e, font=("Segoe UI", 10), fg_color=BG_DARK, text_color="white", border_color=BTN_BLUE, corner_radius=6, width=80); end_entry.insert(0, "30"); end_entry.pack(side="left", padx=5)
        def do_trim():
            try:
                start_time = int(start_entry.get()); end_time = int(end_entry.get())
                if start_time >= end_time: messagebox.showerror("Hata", "Bitiş zamanı başlangıçtan büyük olmalı!"); return
                output_path = video_path.rsplit('.', 1)[0] + "_kirpilmis.mp4"
                cmd = ['ffmpeg', '-i', video_path, '-ss', str(start_time), '-t', str(end_time - start_time), '-c:v', 'libx264', '-c:a', 'aac', '-y', output_path]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0: raise Exception(result.stderr)
                messagebox.showinfo("Başarılı", f"Video kırpıldı!\n{output_path}"); trim_window.destroy()
            except Exception as e: messagebox.showerror("Hata", f"Video kırpma hatası: {e}")
        ctk.CTkButton(trim_window, text="✂️ Kırp", font=("Segoe UI", 11, "bold"), fg_color=BTN_RED, hover_color="#c0303d", text_color="white", corner_radius=8, width=130, height=38, command=do_trim).pack(pady=20)

    def merge_videos(self):
        filepaths = filedialog.askopenfilenames(title="Birleştirilecek Videoları Seçin", filetypes=[("Video files", "*.mp4 *.avi *.mkv")])
        if len(filepaths) < 2: messagebox.showwarning("Uyarı", "En az 2 video seçmelisiniz!"); return
        list_file = os.path.join(self.save_directory, "merge_list.txt")
        with open(list_file, 'w', encoding='utf-8') as f:
            for filepath in filepaths: f.write(f"file '{filepath.replace(chr(92), '/')}'\n")
        output_path = os.path.join(self.save_directory, "birlestirilmis_video.mp4")
        try:
            cmd = ['ffmpeg', '-f', 'concat', '-safe', '0', '-i', list_file, '-c:v', 'libx264', '-c:a', 'aac', '-y', output_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0: raise Exception(result.stderr)
            os.remove(list_file); messagebox.showinfo("Başarılı", f"Videolar birleştirildi!\n{output_path}")
        except Exception as e: messagebox.showerror("Hata", f"Birleştirme hatası: {e}")

    def convert_format(self):
        video_path = self.editor_file_entry.get()
        if not video_path or not os.path.exists(video_path): messagebox.showerror("Hata", "Lütfen geçerli bir video dosyası seçin!"); return
        format_window = ctk.CTkToplevel(self.root); format_window.title("Format Dönüştür"); format_window.geometry("300x300"); format_window.configure(fg_color=BG_DARK)
        ctk.CTkLabel(format_window, text="🔄 Hedef Format", font=("Segoe UI", 14, "bold"), text_color=ACCENT, fg_color="transparent").pack(pady=20)
        format_var = tk.StringVar(value="mp4")
        for text, value in [("MP4", "mp4"), ("AVI", "avi"), ("MKV", "mkv"), ("WebM", "webm")]:
            ctk.CTkRadioButton(format_window, text=text, variable=format_var, value=value, font=("Segoe UI", 10), text_color="white", fg_color=BTN_BLUE, hover_color="#3050dd").pack(anchor="w", padx=40, pady=3)
        def do_convert():
            target_format = format_var.get(); output_path = video_path.rsplit('.', 1)[0] + f"_converted.{target_format}"
            try:
                cmd = ['ffmpeg', '-i', video_path, '-c:v', 'libx264', '-c:a', 'aac', '-y', output_path]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0: raise Exception(result.stderr)
                messagebox.showinfo("Başarılı", f"Video dönüştürüldü!\n{output_path}"); format_window.destroy()
            except Exception as e: messagebox.showerror("Hata", f"Dönüştürme hatası: {e}")
        ctk.CTkButton(format_window, text="🔄 Dönüştür", font=("Segoe UI", 11, "bold"), fg_color=BTN_ORANGE, hover_color="#d96d00", text_color="white", corner_radius=8, width=130, height=38, command=do_convert).pack(pady=20)

    def update_audio_level(self):
        if self.is_recording and self.audio_enabled and not self.is_paused: pass
        self.root.after(50, self.update_audio_level)

    def change_record_mode(self):
        self.record_mode = self.mode_var.get()
        if self.record_mode == "area": self.select_area()

    def select_area(self):
        messagebox.showinfo("Alan Seçimi", "Kaydedilecek alanı seçmek için:\n\n1. Farenizle sol üst köşeden başlayın\n2. Sağ alt köşeye kadar sürükleyin\n3. Bırakın\n\nİptal için ESC tuşuna basın")
        self.area_window = tk.Toplevel(self.root)
        self.area_window.attributes('-fullscreen', True)
        self.area_window.attributes('-alpha', 0.3)
        self.area_window.configure(bg='black')
        self.canvas = tk.Canvas(self.area_window, cursor="cross", bg='black', highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.rect = None; self.start_x = None; self.start_y = None
        def on_mouse_down(event): self.start_x = event.x; self.start_y = event.y
        def on_mouse_move(event):
            if self.start_x is not None:
                if self.rect: self.canvas.delete(self.rect)
                self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, event.x, event.y, outline='red', width=2)
        def on_mouse_up(event):
            if self.start_x is not None:
                x1, y1 = min(self.start_x, event.x), min(self.start_y, event.y)
                x2, y2 = max(self.start_x, event.x), max(self.start_y, event.y)
                self.selected_area = (x1, y1, x2 - x1, y2 - y1); self.area_window.destroy()
        def on_escape(event): self.area_window.destroy(); self.mode_var.set("fullscreen")
        self.canvas.bind('<ButtonPress-1>', on_mouse_down)
        self.canvas.bind('<B1-Motion>', on_mouse_move)
        self.canvas.bind('<ButtonRelease-1>', on_mouse_up)
        self.area_window.bind('<Escape>', on_escape)

    # ------------------------------------------------------------------ #
    # Kayıt Başlat/Durdur
    # ------------------------------------------------------------------ #
    def toggle_recording(self):
        if not self.is_recording: self.start_recording()
        else: self.stop_recording()

    def start_recording(self):
        self.is_recording = True
        self.is_paused = False
        self.start_time = time.time()
        self.elapsed_time = 0
        self.audio_done_event.clear()
        self.video_frame_count = 0
        self.actual_record_fps = None

        if self.webcam_enabled:
            try: self.webcam = cv2.VideoCapture(self.webcam_index)
            except: self.webcam_enabled = False

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        extension = f".{self.video_format}"

        if self.audio_enabled:
            self.temp_video_file = os.path.join(self.save_directory, f"temp_video_{timestamp}{extension}")
            self.output_file = os.path.join(self.save_directory, f"kayit_{timestamp}{extension}")
            self.audio_file = os.path.join(self.save_directory, f"temp_audio_{timestamp}.wav")
        else:
            self.output_file = os.path.join(self.save_directory, f"kayit_{timestamp}{extension}")
            self.temp_video_file = None
            self.audio_file = None

        self.record_btn.configure(text="⏹ Kaydı Durdur", fg_color=BTN_TEAL)
        self.pause_btn.configure(state="normal")
        self.status_label.configure(text="🔴 Kayıt Yapılıyor...", text_color=BTN_RED)

        self.recording_thread = threading.Thread(target=self.record_screen, daemon=True)
        self.recording_thread.start()
        if self.audio_enabled:
            self.audio_thread = threading.Thread(target=self.record_audio, daemon=True)
            self.audio_thread.start()

        self.update_timer()

    # ✅ DÜZELTİLDİ: Thread bekleme süreleri uzun kayıtlar için artırıldı.
    def stop_recording(self):
        self.is_recording = False
        self.record_btn.configure(text="● Kayıt Başlat", fg_color=BTN_RED)
        self.pause_btn.configure(state="disabled", text="⏸ Duraklat")
        self.status_label.configure(text="⚙ Video işleniyor...", text_color=BTN_ORANGE)

        if self.webcam:
            self.webcam.release()
            self.webcam = None

        def finalize():
            # ✅ Uzun kayıtlar için thread ve event bekleme süreleri artırıldı
            if self.recording_thread and self.recording_thread.is_alive():
                self.recording_thread.join(timeout=30)
            if self.audio_enabled and self.audio_thread and self.audio_thread.is_alive():
                self.audio_thread.join(timeout=30)

            if self.audio_enabled:
                self.audio_done_event.wait(timeout=60)

            if self.audio_enabled and self.audio_file and self.temp_video_file:
                if os.path.exists(self.audio_file) and os.path.exists(self.temp_video_file):
                    merge_success = self.merge_audio_video(self.temp_video_file, self.audio_file, self.output_file, actual_fps=self.actual_record_fps)
                    if not merge_success:
                        if os.path.exists(self.temp_video_file):
                            try: os.rename(self.temp_video_file, self.output_file)
                            except: pass
                        self.root.after(0, lambda: messagebox.showwarning("Uyarı", "Ses birleştirme başarısız. Video sesiz kaydedildi."))
                else:
                    if self.temp_video_file and os.path.exists(self.temp_video_file):
                        try: os.rename(self.temp_video_file, self.output_file)
                        except: pass

            self.root.after(0, self._on_recording_finished)

        threading.Thread(target=finalize, daemon=True).start()

    def _on_recording_finished(self):
        self.status_label.configure(text="⚫ Hazır", text_color=TEXT_DIM)
        if self.output_file and os.path.exists(self.output_file):
            filesize = os.path.getsize(self.output_file)
            self.cursor.execute('''
                INSERT INTO recordings (filename, filepath, duration, filesize, fps, format, has_audio, has_webcam)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (os.path.basename(self.output_file), self.output_file, int(self.elapsed_time), filesize, self.fps, self.video_format, 1 if self.audio_enabled else 0, 1 if self.webcam_enabled else 0))
            self.conn.commit()
            messagebox.showinfo("Başarılı", f"Kayıt tamamlandı!\n{self.output_file}")
        else:
            messagebox.showwarning("Uyarı", "Kayıt dosyası oluşturulamadı veya bulunamadı.")

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_btn.configure(text="▶ Devam Et")
            self.status_label.configure(text="⏸ Duraklatıldı", text_color=BTN_ORANGE)
        else:
            self.pause_btn.configure(text="⏸ Duraklat")
            self.status_label.configure(text="🔴 Kayıt Yapılıyor...", text_color=BTN_RED)

    # ------------------------------------------------------------------ #
    # Ekran kayıt motoru
    # ------------------------------------------------------------------ #
    
    def record_screen(self):
        try:
            with mss.mss() as sct:
                if self.record_mode == "fullscreen":
                    monitor = sct.monitors[1]
                elif self.record_mode == "area" and self.selected_area:
                    monitor = {'top': self.selected_area[1], 'left': self.selected_area[0], 'width': self.selected_area[2], 'height': self.selected_area[3]}
                else:
                    monitor = sct.monitors[1]

                codec = self.codec_map.get(self.video_format, "mp4v")
                fourcc = cv2.VideoWriter_fourcc(*codec)
                video_output = self.temp_video_file if self.audio_enabled else self.output_file

                self.video_writer = cv2.VideoWriter(video_output, fourcc, self.fps, (monitor['width'], monitor['height']))

                if not self.video_writer.isOpened():
                    print(f"Codec '{codec}' açılamadı, mp4v deneniyor...")
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                    self.video_writer = cv2.VideoWriter(video_output, fourcc, self.fps, (monitor['width'], monitor['height']))

                if not self.video_writer.isOpened():
                    print("VideoWriter açılamadı! Kayıt durduruluyor.")
                    self.is_recording = False
                    return

                frame_time = 1.0 / self.fps
                next_frame_time = time.perf_counter()
                frame_count = 0
                fps_start_time = time.perf_counter()

                # Gercek sure ve frame sayisi takibi
                self.video_frame_count = 0
                self.video_record_start_time = time.perf_counter()
                total_paused_time = 0.0
                pause_start = None

                while self.is_recording:
                    now = time.perf_counter()
                    if not self.is_paused:
                        if pause_start is not None:
                            total_paused_time += now - pause_start
                            pause_start = None

                        if now >= next_frame_time:
                            screenshot = sct.grab(monitor)
                            frame = np.array(screenshot)
                            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                            if self.webcam_enabled and self.webcam and self.webcam.isOpened():
                                ret, webcam_frame = self.webcam.read()
                                if ret: frame = self.add_webcam_overlay(frame, webcam_frame)
                            if self.cursor_highlight: frame = self.add_cursor_highlight(frame, monitor)
                            if self.show_keystrokes: frame = self.add_keystroke_display(frame)
                            if self.watermark_enabled: frame = self.add_watermark(frame)
                            if self.show_fps_counter: frame = self.add_fps_counter(frame)

                            self.video_writer.write(frame)
                            self.video_frame_count += 1

                            next_frame_time += frame_time
                            if now - next_frame_time > 1.0:
                                next_frame_time = now + frame_time

                            frame_count += 1
                            elapsed = now - fps_start_time
                            if elapsed >= 1.0:
                                self.actual_fps = frame_count / elapsed
                                self.fps_history.append(self.actual_fps)
                                frame_count = 0
                                fps_start_time = now
                        else:
                            sleep_time = next_frame_time - time.perf_counter()
                            if sleep_time > 0: time.sleep(sleep_time * 0.9)
                    else:
                        if pause_start is None:
                            pause_start = now
                        next_frame_time = time.perf_counter() + frame_time
                        time.sleep(0.05)

                # Gercek kayit suresini hesapla (duraklama sureleri haric)
                video_record_end_time = time.perf_counter()
                real_elapsed = (video_record_end_time - self.video_record_start_time) - total_paused_time
                if self.video_frame_count > 0 and real_elapsed > 0:
                    self.actual_record_fps = self.video_frame_count / real_elapsed
                else:
                    self.actual_record_fps = float(self.fps)
        except Exception as e:
            print(f"Ekran kaydı sırasında hata: {e}")
        finally:
            if self.video_writer and self.video_writer.isOpened():
                self.video_writer.release()

    # Overlay yardımcı metodları
    def add_webcam_overlay(self, frame, webcam_frame):
        h, w = frame.shape[:2]
        size = int(min(w, h) * (self.webcam_size_var.get() / 100))
        webcam_resized = cv2.resize(webcam_frame, (size, size))
        position = self.webcam_pos_var.get()
        margin = 20
        if position == "top-left": y1, y2, x1, x2 = margin, margin + size, margin, margin + size
        elif position == "top-right": y1, y2, x1, x2 = margin, margin + size, w - size - margin, w - margin
        elif position == "bottom-left": y1, y2, x1, x2 = h - size - margin, h - margin, margin, margin + size
        else: y1, y2, x1, x2 = h - size - margin, h - margin, w - size - margin, w - margin
        frame[y1:y2, x1:x2] = webcam_resized
        return frame

    def add_cursor_highlight(self, frame, monitor):
        mouse_x = self.mouse_pos[0] - monitor['left']
        mouse_y = self.mouse_pos[1] - monitor['top']
        if 0 <= mouse_x < monitor['width'] and 0 <= mouse_y < monitor['height']:
            size = self.cursor_size_var.get()
            color = tuple(int(self.cursor_color.lstrip('#')[i:i+2], 16) for i in (4, 2, 0))
            cv2.circle(frame, (mouse_x, mouse_y), size, color, 3)
        return frame

    def add_keystroke_display(self, frame):
        current_time = time.time()
        h, w = frame.shape[:2]
        recent_keys = [k for k in self.keystroke_history if current_time - k['time'] < 3.0]
        if recent_keys:
            text = " + ".join([k['key'] for k in recent_keys[-3:]])
            font = cv2.FONT_HERSHEY_SIMPLEX; font_scale = 1.5; thickness = 3
            (text_w, text_h), _ = cv2.getTextSize(text, font, font_scale, thickness)
            x, y = (w - text_w) // 2, h - 50
            cv2.rectangle(frame, (x - 10, y - text_h - 10), (x + text_w + 10, y + 10), (0, 0, 0), -1)
            cv2.rectangle(frame, (x - 10, y - text_h - 10), (x + text_w + 10, y + 10), (0, 255, 255), 2)
            cv2.putText(frame, text, (x, y), font, font_scale, (255, 255, 255), thickness)
        return frame

    def add_watermark(self, frame):
        text = self.watermark_entry.get()
        if not text: return frame
        h, w = frame.shape[:2]; position = self.watermark_pos_var.get()
        pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)
        try: font = ImageFont.truetype("arial.ttf", 30)
        except: font = ImageFont.load_default()
        margin = 20; text_bbox = draw.textbbox((0, 0), text, font=font)
        text_w, text_h = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
        if position == "top-left": text_pos = (margin, margin)
        elif position == "top-right": text_pos = (w - text_w - margin, margin)
        elif position == "bottom-left": text_pos = (margin, h - text_h - margin)
        else: text_pos = (w - text_w - margin, h - text_h - margin)
        draw.text(text_pos, text, font=font, fill=(255, 255, 255, 200))
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    def add_fps_counter(self, frame):
        if self.fps_history:
            avg_fps = sum(self.fps_history) / len(self.fps_history)
            cv2.putText(frame, f"FPS: {avg_fps:.1f}", (frame.shape[1] - 150, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        return frame

    def update_timer(self):
        if self.is_recording:
            if not self.is_paused: self.elapsed_time = time.time() - self.start_time
            hours = int(self.elapsed_time // 3600); minutes = int((self.elapsed_time % 3600) // 60); seconds = int(self.elapsed_time % 60)
            self.timer_label.configure(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            self.root.after(100, self.update_timer)
        else:
            self.timer_label.configure(text="00:00:00")

    def take_screenshot(self):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"; filepath = os.path.join(self.save_directory, filename)
        if self.record_mode == "fullscreen": screenshot = pyautogui.screenshot()
        elif self.record_mode == "area" and self.selected_area: screenshot = pyautogui.screenshot(region=self.selected_area)
        else: screenshot = pyautogui.screenshot()
        screenshot.save(filepath)
        filesize = os.path.getsize(filepath)
        self.cursor.execute('INSERT INTO recordings (filename, filepath, filesize) VALUES (?, ?, ?)', (filename, filepath, filesize))
        self.conn.commit()
        messagebox.showinfo("Başarılı", f"Ekran görüntüsü kaydedildi!\n{filepath}")

    def open_settings(self):
        settings_window = ctk.CTkToplevel(self.root)
        settings_window.title("Ayarlar"); settings_window.geometry("500x560"); settings_window.configure(fg_color=BG_DARK)
        settings_window.transient(self.root); settings_window.grab_set()
        ctk.CTkLabel(settings_window, text="⚙ Ayarlar", font=("Segoe UI", 16, "bold"), text_color=ACCENT, fg_color="transparent").pack(pady=20)
        content = ctk.CTkFrame(settings_window, fg_color=BG_MID, corner_radius=10)
        content.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        inner = ctk.CTkFrame(content, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=20, pady=15)
        fps_frame = ctk.CTkFrame(inner, fg_color="transparent")
        fps_frame.pack(fill="x", pady=10)
        fps_val_label = ctk.CTkLabel(fps_frame, text=f"FPS: {self.fps}", font=("Segoe UI", 10), text_color="white", fg_color="transparent")
        fps_val_label.pack(anchor="w", pady=(0, 6))
        fps_scale = ctk.CTkSlider(fps_frame, from_=15, to=60, fg_color=BG_DARK, progress_color=BTN_BLUE, button_color=ACCENT, button_hover_color="#00b8d4", orientation="horizontal", command=lambda v: fps_val_label.configure(text=f"FPS: {int(v)}"))
        fps_scale.set(self.fps); fps_scale.pack(fill="x")
        quality_frame = ctk.CTkFrame(inner, fg_color="transparent")
        quality_frame.pack(fill="x", pady=10)
        quality_val_label = ctk.CTkLabel(quality_frame, text=f"Kalite: {self.quality}%", font=("Segoe UI", 10), text_color="white", fg_color="transparent")
        quality_val_label.pack(anchor="w", pady=(0, 6))
        quality_scale = ctk.CTkSlider(quality_frame, from_=50, to=100, fg_color=BG_DARK, progress_color=BTN_BLUE, button_color=ACCENT, button_hover_color="#00b8d4", orientation="horizontal", command=lambda v: quality_val_label.configure(text=f"Kalite: {int(v)}%"))
        quality_scale.set(self.quality); quality_scale.pack(fill="x")
        dir_frame = ctk.CTkFrame(inner, fg_color="transparent")
        dir_frame.pack(fill="x", pady=10)
        ctk.CTkLabel(dir_frame, text="Kayıt Dizini:", font=("Segoe UI", 10), text_color="white", fg_color="transparent").pack(anchor="w", pady=(0, 6))
        dir_entry = ctk.CTkEntry(dir_frame, font=("Segoe UI", 9), fg_color=BG_DARK, text_color="white", border_color=BTN_BLUE, corner_radius=6)
        dir_entry.insert(0, self.save_directory); dir_entry.pack(fill="x", pady=(0, 8))
        def browse_directory():
            directory = filedialog.askdirectory(initialdir=self.save_directory)
            if directory: dir_entry.delete(0, tk.END); dir_entry.insert(0, directory)
        ctk.CTkButton(dir_frame, text="📁 Gözat", font=("Segoe UI", 9), fg_color=BTN_BLUE, hover_color="#3050dd", text_color="white", corner_radius=6, width=90, command=browse_directory).pack()
        def save_settings_and_close():
            self.fps = int(fps_scale.get()); self.quality = int(quality_scale.get()); self.save_directory = dir_entry.get()
            os.makedirs(self.save_directory, exist_ok=True); self.save_settings(); settings_window.destroy()
            messagebox.showinfo("Başarılı", "Ayarlar kaydedildi!")
        ctk.CTkButton(settings_window, text="💾 Kaydet", font=("Segoe UI", 11, "bold"), fg_color=BTN_GREEN, hover_color="#04d98e", text_color=BG_DARK, corner_radius=8, width=140, height=40, command=save_settings_and_close).pack(pady=10)

    def update_preview(self):
        if not self.is_recording:
            try:
                with mss.mss() as sct:
                    monitor = sct.monitors[1]
                    screenshot = sct.grab(monitor)
                    img = Image.frombytes('RGB', screenshot.size, screenshot.rgb)
                    preview_width = 840; preview_height = int(preview_width * img.height / img.width)
                    img = img.resize((preview_width, preview_height), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.preview_label.configure(image=photo); self.preview_label.image = photo
            except: pass
        self.root.after(1000, self.update_preview)

    def on_closing(self):
        if self.is_recording:
            if messagebox.askokcancel("Çıkış", "Kayıt devam ediyor. Çıkmak istiyor musunuz?"):
                self.stop_recording(); self.conn.close(); self.hotkey_listener.stop(); self.mouse_listener.stop(); self.root.destroy()
        else:
            self.conn.close(); self.hotkey_listener.stop(); self.mouse_listener.stop(); self.root.destroy()

def main():
    root = ctk.CTk()
    app = ScreenRecorderPro(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
