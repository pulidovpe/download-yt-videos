#!/usr/bin/env python3
import shutil
import time
import json
import requests
import os
import re
import subprocess
import sys
import tempfile
import json
import requests
import chardet
from itertools import chain
from deep_translator import GoogleTranslator
from pathlib import Path
from tqdm import tqdm
from colorama import Fore, Back, Style, init
from langdetect import detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException

# Inicializar colores
init(autoreset=True)

# Configuración
TEMP_DIR = Path(os.getcwd()) / "tmp"  # Usar una carpeta "tmp" en el directorio de ejecución
TEMP_DIR.mkdir(exist_ok=True)  # Crear la carpeta si no existe
FINAL_DIR = Path.cwd() / "Descargas_YT"

class Translator:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://translate.googleapis.com/translate_a/single"
        self.fallback_url = "https://clients5.google.com/translate_a/t"
        
    def translate(self, text, src='en', dest='es'):
        params = {
            'client': 'gtx',
            'sl': src,
            'tl': dest,
            'dt': 't',
            'q': text
        }
        
        try:
            # Intentar con el endpoint principal
            response = self.session.get(self.base_url, params=params, timeout=10)
            if response.status_code == 200:
                translated = json.loads(response.text)[0][0][0]
                return translated
                
            # Fallback a endpoint alternativo
            response = self.session.get(self.fallback_url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()[0]
                
        except Exception as e:
            print(Fore.YELLOW + f"Error de traducción: {str(e)}")
        
        return text  # Fallback a texto original

class YouTubeDownloader:
    def __init__(self):
        self.video_path = None
        self.subs_path = None
        self.setup_dirs()
        self.translator = Translator()
        self.print_ascii_art()

    def print_ascii_art(self):
        print(Fore.CYAN + r"""
          __                .___.__          
 ___.__._/  |_            __| _/|  | ______  
<   |  |\   __\  ______  / __ | |  | \____ \ 
 \___  | |  |   /_____/ / /_/ | |  |_|  |_> >
 / ____| |__|           \____ | |____/   __/ 
 \/                          \/      |__|
        """)

    def setup_dirs(self):
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        FINAL_DIR.mkdir(parents=True, exist_ok=True)  # Crea directorio si no existe
        print(Fore.CYAN + f"\nDirectorio de salida: {FINAL_DIR.resolve()}")

    def get_url(self):
        print(Fore.YELLOW + "\n🡆  Ingrese la URL de YouTube (video/lista):")
        url = input(Fore.WHITE + ">>> ").strip()
        if not url.startswith(('http://', 'https://')):
            print(Fore.RED + "✘ Error: URL inválida")
            sys.exit(1)
        return url

    def get_playlist_range(self, range_input):
        """
        Procesa el rango de videos ingresado por el usuario.

        :param range_input: Rango especificado (ejemplo: '1-5' o '3')
        :return: Tupla (start, end) con el rango de videos o (None, None) si no hay rango.
        """
        if not range_input:
            return None, None  # Sin rango, descarga todo

        try:
            if '-' in range_input:
                start, end = range_input.split('-')
                return int(start), int(end) if end else None
            else:
                start = int(range_input)
                return start, start  # Un solo video
        except ValueError:
            print(Fore.RED + "✘ Formato de rango inválido. Usa un formato como '1-5' o '3'.")
            sys.exit(1)

    def find_files(self, video_path):
        video_stem = video_path.stem
        print(Fore.CYAN + f"🔍 Procesando subtítulos para: {video_stem}")

        # Buscar subtítulos en español usando el nuevo método
        sub_path = self.collect_spanish_subs(video_stem)
        if sub_path:
            return sub_path

        # Si no hay subtítulos en español, buscar en inglés y traducir
        en_subs = list(TEMP_DIR.glob(f'{video_stem}.en.srt')) + \
                list(TEMP_DIR.glob(f'{video_stem}.en.*.srt'))

        if en_subs:
            print(Fore.YELLOW + "⚠ Subtítulos en español no encontrados, traduciendo desde inglés...")
            return self.translate_subs(en_subs[0], target_language="es")

        # Intentar descarga alternativa si no hay subtítulos
        print(Fore.YELLOW + "⚠ No se encontraron subtítulos, intentando descarga alternativa...")
        try:
            subprocess.run([
                'yt-dlp',
                '--skip-download',
                '--write-auto-sub',
                '--sub-langs', 'en',
                '-o', str(TEMP_DIR / f'{video_stem}.%(ext)s'),
                '--', video_path.name.split('_', 1)[1]
            ], check=True)
            
            new_subs = list(TEMP_DIR.glob(f'{video_stem}.en.*.srt'))
            if new_subs:
                return self.translate_subs(new_subs[0], target_language="es")
        except subprocess.CalledProcessError as e:
            print(Fore.RED + f"✘ Error en descarga alternativa: {str(e)}")

        return None

    def process_videos(self):
        """Nuevo método para manejar múltiples videos"""
        video_files = sorted(TEMP_DIR.glob('*.mkv'), key=os.path.getmtime)  # Orden por fecha de descarga
        
        for idx, video_path in enumerate(video_files, 1):
            print(Fore.MAGENTA + f"\nProcesando video {idx}/{len(video_files)}:")
            print(Fore.WHITE + f"Archivo: {video_path.name}")
            
            self.video_path = video_path
            subs_path = self.find_files(video_path)
            
            if subs_path:
                # Traducir subtítulos antes de mezclarlos
                translated_path = self.translate_subs(subs_path, target_language="es")
                if translated_path:
                    self.mux_subtitles(video_path, translated_path, idx)
                else:
                    print(f"✘ Traducción fallida para subtítulos de {video_path.name}")
            else:
                print(f"✘ No se encontraron subtítulos para: {video_path.name}")
                # Si no hay subtítulos, copiar el video directamente
                final_path = FINAL_DIR / video_path.name
                shutil.copy(video_path, final_path)
                print(Fore.YELLOW + f"⚠ Video copiado sin subtítulos: {final_path.name}")
    
    def translate_subs(self, sub_path, target_language="es"):
        """
        Traduce un archivo de subtítulos a otro idioma utilizando deep-translator.

        :param sub_path: Ruta al archivo de subtítulos.
        :param target_language: Idioma objetivo para la traducción (por defecto: "es").
        :return: Ruta del archivo traducido o None si ocurre un error.
        """
        try:
            # Detectar codificación del archivo
            with open(sub_path, "rb") as file:
                raw_data = file.read()
                detected = chardet.detect(raw_data)
                encoding = detected["encoding"]
                print(f"📂 Codificación detectada para {sub_path.name}: {encoding}")

            # Leer subtítulos con la codificación detectada
            with open(sub_path, "r", encoding=encoding) as file:
                subtitles = file.readlines()

            # Configurar traductor
            translator = GoogleTranslator(source="auto", target=target_language)

            # Traducir subtítulos línea por línea
            translated_subtitles = []
            total_lines = len(subtitles)
            for idx, line in enumerate(subtitles, start=1):
                if line.strip():  # Traducir líneas no vacías
                    try:
                        # Mostrar progreso
                        print(f"Traduciendo línea {idx}/{total_lines}...", end="\r")
                        translated_line = translator.translate(line.strip())
                        translated_subtitles.append(translated_line + "\n")
                    except Exception as e:
                        print(f"\n⚠ Error al traducir línea {idx}: {line.strip()[:50]}... | {e}")
                        translated_subtitles.append(line)  # Mantener línea original en caso de error
                else:
                    translated_subtitles.append(line)

            print("\n✔ Traducción completa.")

            # Guardar subtítulos traducidos
            translated_path = sub_path.with_suffix(f".{target_language}.srt")
            with open(translated_path, "w", encoding="utf-8") as file:
                file.writelines(translated_subtitles)

            print(f"✔ Subtítulos traducidos guardados en: {translated_path}")
            return translated_path

        except UnicodeDecodeError as e:
            print(f"✘ Error de codificación en {sub_path.name}: {e}")
            return None
        except Exception as e:
            print(f"✘ Error inesperado al traducir subtítulos {sub_path.name}: {e}")
            return None

    def mux_subtitles(self, video_path, subs_path, idx):
        """
        Combina el video con los subtítulos en un nuevo archivo.
        """
        import subprocess

        print(f"🎞 Procesando archivo de video: {video_path.name}")
        output_path = video_path.parent / f"{video_path.stem}_muxed{video_path.suffix}"

        # Asegurarnos de que subs_list sea una lista de tuplas
        if isinstance(subs_path, PosixPath):
            # Convertir un único subtítulo en una lista de tuplas
            subs_list = [(subs_path, "español")]
        elif isinstance(subs_path, list):
            # Validar que la lista esté en el formato correcto
            subs_list = [(path, "español") for path in subs_path]
        else:
            raise ValueError(f"Formato de subs_path no reconocido: {subs_path}")

        # Construcción del comando ffmpeg
        cmd = ["ffmpeg", "-i", str(video_path)]
        for i, (sub_path, label) in enumerate(subs_list):
            cmd.extend(["-sub_charenc", "UTF-8", "-i", str(sub_path)])
        cmd.extend(["-map", "0:v", "-map", "0:a", "-map", f"{i + 1}:s", "-c", "copy", str(output_path)])

        try:
            print(f"▶ Ejecutando ffmpeg: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)
            print(f"✔ Archivo combinado creado: {output_path}")
        except subprocess.CalledProcessError as e:
            print(f"❌ Error al combinar el video con subtítulos: {e}")

    def clean_up(self):
        for f in TEMP_DIR.glob('*'):
            try:
                f.unlink()
            except:
                pass

    def check_dependencies(self):
        deps = {
            'yt-dlp': ['yt-dlp', '--version'],
            'mkvmerge': ['mkvmerge', '-V'],
            'ffmpeg': ['ffmpeg', '-version']
        }
        
        missing = []
        for name, cmd in deps.items():
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                missing.append(name)
                
        if missing:
            print(Fore.RED + "✘ Faltan dependencias:")
            for dep in missing:
                print(f" - {dep}")
            print("\nInstale con:")
            print("sudo dnf install mkvtoolnix ffmpeg")
            print("pip install yt-dlp googletrans==4.0.0-rc1")
            sys.exit(1)
        
        print(Fore.YELLOW + "⚠ Asegúrate de:")
        print("- Tener Chrome cerrado durante la descarga")
        print("- Usar un perfil válido en ~/.config/google-chrome")

    def handle_playlist_range(self, range_input):
        """Procesa el input de rango y devuelve (start, end)"""
        if not range_input:
            return None, None
            
        try:
            if '-' in range_input:
                parts = range_input.split('-')
                start = int(parts[0]) if parts[0] else 1
                end = int(parts[1]) if len(parts) > 1 and parts[1] else None
                return start, end
            else:
                return int(range_input), int(range_input)
        except ValueError:
            print(Fore.RED + "✘ Formato de rango inválido")
            sys.exit(1)

    def extract_video_title(self, line):
        """Extrae el título del video de la línea de log con mejor manejo de errores"""
        try:
            # Buscar el título entre comillas después de "Downloading item"
            match = re.search(r'Downloading item \d+ of playlist "(.+?)"', line)
            return match.group(1).strip()[:35] + "..." if match else f"Video_{int(time.time())}"
        except Exception as e:
            print(Fore.YELLOW + f"⚠ Error extrayendo título: {str(e)}")
            return "Video_Desconocido"

    def run(self):
        self.setup_dirs()
        self.check_dependencies()
        url = self.get_url()

        # Obtener rango de descarga
        print(Fore.YELLOW + "\n🡆 ¿Deseas descargar un rango específico de videos? (ejemplo: 1-5, 3, 7-)")
        print(Fore.YELLOW + "Presiona Enter para descargar toda la lista.")
        range_input = input(Fore.WHITE + ">>> ").strip()
        start, end = self.handle_playlist_range(range_input)

        try:
            # Configurar comando yt-dlp
            cmd = [
                'yt-dlp',
                '--newline',  # Crucial para el procesamiento de líneas
                '--console-title',  # Mejora la salida de progreso
                '--cookies-from-browser', 'chrome',
                '-f', 'bestvideo+bestaudio',
                '--merge-output-format', 'mkv',
                '--write-subs',
                '--write-auto-subs',
                '--sub-langs', 'en.*,es.*',
                '--convert-subs', 'srt',
                '--embed-subs',
                '--ignore-errors',
                '--yes-playlist',
                '-o', str(TEMP_DIR / '%(playlist_index)03d_%(title)s.%(ext)s'),
                url
            ]

            # Agregar parámetros de rango
            if start or end:
                cmd += ['--playlist-start', str(start), '--playlist-end', str(end) if end else '9999']

            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=1,
                    universal_newlines=True,
                    text=True  # Asegurar salida como texto
                )
                
                # Captura números decimales o enteros
                progress_pattern = re.compile(r'\[(?:download)\]\s+(\d{1,3}(?:\.\d+)?)%')  
                current_pbar = None
                video_count = 0
                title = "Inicializando..."

                for line in iter(process.stdout.readline, ''):
                    line = line.strip()
                    #print(line)  # Debug: Verifica el contenido de la línea
                    
                    # Detectar nuevo video
                    if '[download]' in line and 'of' in line and 'at' in line:
                        video_count += 1
                        current_pbar = tqdm(
                            total=100,
                            desc=f"{Fore.BLUE}📥 Video {video_count}: {title[:35]}",
                            bar_format="{desc}: {percentage:3.0f}% |{bar:50}| {n_fmt}/{total_fmt}",
                            leave=False
                        )

                    # Actualizar el progreso
                    match = progress_pattern.search(line)
                    if match and current_pbar:
                        progress = float(match.group(1))
                        current_pbar.n = progress
                        current_pbar.refresh()

                        # Si el progreso alcanza el 100%, cierra la barra
                        if progress >= 100.0:
                            current_pbar.close()
                            current_pbar = None

                # Cierra cualquier barra restante al final del proceso
                if current_pbar:
                    current_pbar.close()

            except Exception as e:
                print(Fore.RED + f"Error: {str(e)}")

        except subprocess.CalledProcessError as e:
            print(Fore.RED + f"\n✘ Error en descarga: {str(e)}")
            sys.exit(1)

        # Procesar videos descargados
        print(Fore.GREEN + "\n✅ Descarga completada. Procesando videos...")
        self.process_videos()
        self.clean_up()
        print(Fore.CYAN + "\n✨ Proceso finalizado correctamente")

    def detect_language(self, sub_path):
        """
        Detecta el idioma de un archivo de subtítulos.
        :param sub_path: Ruta del archivo de subtítulos.
        :return: Código del idioma detectado (ejemplo: 'es', 'en') o None si ocurre un error.
        """
        try:
            with open(sub_path, "r", encoding="utf-8") as file:
                content = file.read()

            # Usa deep-translator para detectar el idioma (basado en el contenido)
            translator = GoogleTranslator(source='auto', target='es')
            detected_lang = translator.detect(content)
            print(f"🔍 Idioma detectado para {sub_path.name}: {detected_lang}")
            return detected_lang

        except Exception as e:
            print(f"✘ Error al detectar idioma en {sub_path.name}: {e}")
            return None
    
    def process_existing_videos(self, folder_path):
        """
        Procesa videos y subtítulos existentes en una carpeta:
        1. Detecta si los subtítulos están en español.
        2. Traduce subtítulos al español si no lo están.
        3. Inserta los subtítulos como predeterminados en los videos.

        :param folder_path: Ruta de la carpeta con los videos y subtítulos.
        """
        folder = Path(folder_path)
        if not folder.is_dir():
            print(Fore.RED + "✘ La ruta proporcionada no es una carpeta válida.")
            return

        # Buscar archivos de video y subtítulos
        video_files = sorted(chain(
            folder.glob('*.mkv'),
            folder.glob('*.mp4'),
            folder.glob('*.avi'),
            folder.glob('*.mov'),
        ))
        subtitle_files = sorted(folder.glob('*.srt'))

        if not video_files or not subtitle_files:
            print(Fore.RED + "✘ No se encontraron videos o subtítulos en la carpeta.")
            return

        print(Fore.CYAN + f"📁 Procesando carpeta: {folder.resolve()}")

        # Convertir subtítulos a UTF-8 o validar si ya están en UTF-8
        utf8_subtitles = []
        for subtitle_file in subtitle_files:
            if self.is_utf8(subtitle_file):
                # Si ya está en UTF-8, agregarlo directamente
                print(Fore.GREEN + f"✔ {subtitle_file.name} ya está en UTF-8.")
                utf8_subtitles.append(subtitle_file)
            else:
                # Intentar convertirlo a UTF-8
                utf8_sub_path = self.convert_srt_to_utf8(subtitle_file)
                if utf8_sub_path:
                    utf8_subtitles.append(utf8_sub_path)
                else:
                    print(Fore.RED + f"✘ No se pudo convertir {subtitle_file.name} a UTF-8. Omitiendo.")

        for video_file in video_files:
            # Encontrar subtítulo correspondiente (mismo nombre base) en la lista de UTF-8
            base_name = video_file.stem
            subtitle_file = next((s for s in utf8_subtitles if s.stem.startswith(base_name)), None)

            if not subtitle_file:
                print(Fore.YELLOW + f"⚠ No se encontró subtítulo UTF-8 para: {video_file.name}")
                continue

            print(Fore.CYAN + f"✔ Procesando: {video_file.name} con {subtitle_file.name}")

            # Detectar idioma del subtítulo
            try:
                print(f"🔍 Detectando idioma para {subtitle_file.name}...")
                with open(subtitle_file, "r", encoding="utf-8") as file:
                    sample_text = ''.join(file.readlines()[:10])  # Usar las primeras 10 líneas como muestra
                detected_language = detect(sample_text)
                print(f"🗣 Idioma detectado: {detected_language}")

                if detected_language == "es":
                    print(f"✔ {subtitle_file.name} ya está en español. Usando directamente.")
                    translated_path = subtitle_file  # Usar el subtítulo existente
                else:
                    response = input(Fore.CYAN + "\n¿Deseas traducir el subtitulo? (s/n): ").strip().lower()
                    if response in ('s', 'si', 'sí'):
                        # Traducir subtítulos
                        translated_path = self.translate_subs(subtitle_file, target_language="es")
                        if not translated_path:
                            print(Fore.RED + f"✘ Error al traducir subtítulos para: {video_file.name}")
                            continue
                    else:
                        translated_path = subtitle_file  # Usar el subtítulo existente

            except LangDetectException as e:
                print(Fore.RED + f"✘ Error al detectar idioma de {subtitle_file.name}: {e}")
                continue
            except Exception as e:
                print(Fore.RED + f"✘ Error inesperado: {e}")
                continue

            # Insertar subtítulos en el video
            output_path = folder / f"translated_{video_file.name}"
            cmd = [
                'mkvmerge',
                '-o', str(output_path.resolve()),
                str(video_file.resolve()),
                '--track-name', '0:Español',
                '--language', '0:es',
                '--default-track', '0:true',
                str(translated_path.resolve())
            ]

            try:
                subprocess.run(cmd, check=True)
                print(Fore.GREEN + f"✅ Subtítulo insertado en: {output_path.name}")
            except subprocess.CalledProcessError as e:
                print(Fore.RED + f"✘ Error al insertar subtítulos en: {video_file.name}")
                print(Fore.RED + str(e))
                continue

        print(Fore.GREEN + "\n✔ Todos los videos procesados.")

    def collect_spanish_subs(self, video_path):
        """
        Busca y devuelve la ruta del archivo de subtítulos en español correspondiente al video.
        """
        from pathlib import Path

        # Asegurarse de que video_path sea un objeto Path
        video_path = Path(video_path) if isinstance(video_path, str) else video_path

        # Construir la ruta esperada para los subtítulos
        stem = video_path.stem  # Esto ahora funciona porque video_path es un Path
        subs_file = TEMP_DIR / f"{stem}.es.srt"

        if subs_file.exists():
            print(f"✔ Subtítulos encontrados: {subs_file}")
            return subs_file
        else:
            print(f"⚠ No se encontraron subtítulos para: {video_path.name}")
            return None

    def cleanup_temp_files(self):
        """Elimina los archivos en la carpeta temporal si el usuario lo confirma."""
        response = input(Fore.CYAN + "\n¿Deseas eliminar los archivos temporales? (s/n): ").strip().lower()
        if response in ('s', 'si', 'sí'):
            if TEMP_DIR.exists():
                print("🧹 Limpiando archivos temporales...")
                shutil.rmtree(TEMP_DIR)
                print("✔ Archivos temporales eliminados.")
            else:
                print("No hay archivos temporales para limpiar.")
        else:
            print(Fore.YELLOW + "⚠ Los archivos temporales no fueron eliminados.")

    def is_utf8(self, file_path):
        """
        Verifica si un archivo está codificado en UTF-8.

        :param file_path: Ruta del archivo.
        :return: True si está en UTF-8, False en caso contrario.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                file.read()  # Intentar leer el archivo completo
            return True
        except UnicodeDecodeError:
            return False

    def convert_srt_to_utf8(self, srt_path):
        """
        Convierte un archivo .srt a UTF-8 si no está ya en esta codificación.

        :param srt_path: Ruta al archivo .srt.
        :return: Ruta al archivo convertido o None si ocurre un error.
        """
        try:
            # Detectar la codificación del archivo
            with open(srt_path, "rb") as file:
                raw_data = file.read()
                detected = chardet.detect(raw_data)
                encoding = detected["encoding"]
                print(f"📂 Codificación detectada para {srt_path.name}: {encoding}")

            # Si ya está en UTF-8, no es necesario convertir
            if encoding.lower() == "utf-8":
                print(f"✔ {srt_path.name} ya está en UTF-8. No se necesita conversión.")
                return srt_path

            # Leer el archivo con la codificación detectada
            with open(srt_path, "r", encoding=encoding) as file:
                content = file.read()

            # Guardar el archivo en UTF-8
            utf8_path = srt_path.with_suffix(".utf8.srt")
            with open(utf8_path, "w", encoding="utf-8") as file:
                file.write(content)

            print(f"✔ Archivo convertido a UTF-8: {utf8_path.name}")
            return utf8_path

        except Exception as e:
            print(f"✘ Error al convertir {srt_path.name} a UTF-8: {e}")
            return None

if __name__ == "__main__":
    try:
        downloader = YouTubeDownloader()
        while True:
            # Menú interactivo
            print(Fore.CYAN + "\n🡆 Selecciona una opción:")
            print(Fore.YELLOW + "1. Descargar videos y subtítulos desde YouTube.")
            print(Fore.YELLOW + "2. Procesar videos y subtítulos existentes en una carpeta.")
            print(Fore.YELLOW + "3. Traducir subtítulos existentes en una carpeta.")
            print(Fore.YELLOW + "4. Recodificar subtítulos existentes en una carpeta a UTF-8.")
            print(Fore.YELLOW + "5. Salir.")

            choice = input(Fore.WHITE + ">>> ").strip()

            if choice == "1":
                print(Fore.CYAN + "\n🡆 Iniciando descarga de videos...")
                downloader.run()
            elif choice == "2":
                print(Fore.CYAN + "\n🡆 Proporciona la carpeta con videos y subtítulos:")
                folder_path = input(Fore.WHITE + ">>> ").strip()
                downloader.process_existing_videos(folder_path)
            elif choice == "3":
                subs_folder = Path(input("📂 Ingresa la ruta de la carpeta con subtítulos: "))
                for sub_file in subs_folder.glob("*.srt"):
                    translated_path = downloader.translate_subs(sub_file)
                    if translated_path:
                        print(f"✔ Subtítulos traducidos: {translated_path}")
                    else:
                        print(f"✘ No se pudo traducir subtítulos: {sub_file.name}")
                break
            elif choice == "4":
                folder_path = input("📂 Ingresa la ruta de la carpeta con subtítulos: ")
                folder = Path(folder_path)
                if not folder.is_dir():
                    print(Fore.RED + "✘ La ruta proporcionada no es una carpeta válida.")
                else:
                    print(Fore.CYAN + f"📁 Procesando carpeta: {folder.resolve()}")
                    srt_files = list(folder.glob("*.srt"))
                    if not srt_files:
                        print(Fore.RED + "✘ No se encontraron archivos .srt en la carpeta.")
                    else:
                        for srt_file in srt_files:
                            downloader.convert_srt_to_utf8(srt_file)
            elif choice == "5":
                print(Fore.GREEN + "\n✔ Gracias por usar el programa. ¡Hasta pronto!")
                break
            else:
                print(Fore.RED + "✘ Opción inválida. Por favor selecciona 1, 2, 3 o 4.")
        
        # Preguntar si eliminar archivos temporales
        downloader.cleanup_temp_files()

    except KeyboardInterrupt:
        print(Fore.RED + "\n✘ Operación cancelada por el usuario")
        sys.exit(130)