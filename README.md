# Modern Ekran Kaydedici Pro (Aptoza) 🎥

Aptoza, Python ve CustomTkinter kullanılarak geliştirilmiş, modern arayüze sahip kapsamlı bir ekran kayıt ve video düzenleme aracıdır. Standart ekran kaydının ötesine geçerek; tuş vuruşlarını gösterme, fare vurgulama, ses ve webcam entegrasyonu gibi özellikle eğitim/tutorial videoları çekenler için optimize edilmiştir.

## ✨ Özellikler

* **Gelişmiş Ekran Kaydı:** Tam ekran veya belirli bir alanı seçerek kayıt yapabilme.
* **Ses & Webcam Entegrasyonu:** Mikrofon, sistem sesi veya her ikisini birden kaydetme. İstenilen köşeye webcam görüntüsü ekleme.
* **Eğitim Odaklı Araçlar:** * Ekranda basılan tuşları (Keystrokes) anlık olarak gösterme. Fare imlecini renkli bir hale ile vurgulama.
* **Dahili Video Düzenleyici:** FFmpeg gücüyle videoları kırpma, birleştirme ve format dönüştürme (MP4, AVI, MKV, WebM).
* **Zamanlanmış Kayıt:** Belirli bir saatte otomatik kayıt başlatma ve bitirme.
* **Performans Takibi:** Ekranda anlık FPS sayacı ve SQLite veritabanı ile geçmiş kayıtların tutulması.

## 🛠️ Gereksinimler

Bu uygulamanın video birleştirme ve düzenleme özelliklerinin düzgün çalışması için sisteminizde **FFmpeg**'in yüklü ve sistem ortam değişkenlerine (PATH) eklenmiş olması **zorunludur**.
* [FFmpeg İndir ve Kur](https://ffmpeg.org/download.html)

## 🚀 Kurulum

1. Depoyu bilgisayarınıza klonlayın:
   ```bash
   git clone [https://github.com/KULLANICI_ADIN/aptoza-screen-recorder.git](https://github.com/KULLANICI_ADIN/aptoza-screen-recorder.git)
   cd aptoza-screen-recorder
## Gerekli Python Kütüphanelerinin Kurulumu
```bash
pip install -r requirements.txt