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
from pathlib import Path
from tqdm import tqdm
from colorama import Fore, Back, Style, init

# Inicializar colores
init(autoreset=True)

# Configuración
TEMP_DIR = Path(tempfile.gettempdir()) / "yt_downloader"
FINAL_DIR = Path.cwd() / "Descargas_YT"
#FINAL_DIR = Path.home() / "Videos" / "YT_Downloads"

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
        all_subs = list(TEMP_DIR.glob(f'{video_stem}*.srt'))
        
        # Buscar subtítulos en español primero
        es_subs = list(TEMP_DIR.glob(f'{video_stem}.es.srt')) + \
                list(TEMP_DIR.glob(f'{video_stem}.es.*.srt'))
        
        if es_subs:
            sub_path = es_subs[0]
            print(Fore.CYAN + f"✔ Subtítulos en español encontrados: {sub_path.name}")
            return sub_path

        # Si no hay en español, buscar en inglés y traducir
        en_subs = list(TEMP_DIR.glob(f'{video_stem}.en.srt')) + \
                list(TEMP_DIR.glob(f'{video_stem}.en.*.srt'))
        
        if en_subs:
            print(Fore.YELLOW + "⚠ Subtítulos en español no encontrados, traduciendo desde inglés...")
            return self.translate_subs(en_subs[0])

        # Si no hay subtítulos, intentar descargar automáticos
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
            
            # Buscar nuevos subtítulos y traducir
            new_subs = list(TEMP_DIR.glob(f'{video_stem}.en.*.srt'))
            if new_subs:
                return self.translate_subs(new_subs[0])
        
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
                self.mux_subtitles(video_path, subs_path, idx)
            else:
                # Si no hay subtítulos, copiar el video directamente
                final_path = FINAL_DIR / video_path.name
                shutil.copy(video_path, final_path)
                print(Fore.YELLOW + f"⚠ Video copiado sin subtítulos: {final_path.name}")
    
    def translate_subs(self, sub_path):
        translated_path = TEMP_DIR / "subs_es.srt"
        
        try:
            with open(sub_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            translated = []
            blocks = content.split('\n\n')
            
            for block in tqdm(blocks, desc=Fore.MAGENTA + "Traduciendo subtítulos",
                             bar_format="{desc}: {percentage:3.0f}% │{bar:50}{r_bar} │ Tiempo: {elapsed}"):
                if not block.strip():
                    continue
                    
                lines = block.split('\n')
                if len(lines) >= 3:
                    text = '\n'.join(lines[2:])
                    try:
                        translated_text = self.translator.translate(
                            text, src='en', dest='es'
                        ).text
                        translated.append('\n'.join(lines[:2] + [translated_text]))
                    except:
                        translated.append(block)
                else:
                    translated.append(block)
                    
            with open(translated_path, 'w', encoding='utf-8') as f:
                f.write('\n\n'.join(translated))
                
            return translated_path
            
        except Exception as e:
            print(Fore.RED + f"✘ Error en traducción: {str(e)}")
            return None

    def mux_subtitles(self, video_path, subs_path, index):
        try:
            base_name = f"{index:03d}_{video_path.name.split('_', 1)[1]}"
            output_path = FINAL_DIR / base_name
            
            if not subs_path:
                shutil.copy(video_path, output_path)
                print(Fore.YELLOW + f"⚠ Copiado sin subtítulos: {base_name}")
                return

            # Orden CORRECTO de parámetros para mkvmerge
            cmd = [
                'mkvmerge',
                '-o', str(output_path),
                str(video_path),  # 1. Archivo de video
                '--language', '0:spa',  # 2. Metadatos PARA EL SIGUIENTE ARCHIVO
                '--track-name', '0:Español',
                '--default-track', '0:yes',
                str(subs_path)  # 3. Archivo de subtítulos (hereda los metadatos anteriores)
            ]
            
            subprocess.run(cmd, check=True)
            print(Fore.GREEN + f"✅ Video finalizado: {base_name}")
            
        except subprocess.CalledProcessError as e:
            print(Fore.RED + f"✘ Error en mezcla: {str(e)}")
            shutil.copy(video_path, output_path)
            print(Fore.YELLOW + f"⚠ Copiado sin subtítulos: {base_name}")

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

if __name__ == "__main__":
    try:
        downloader = YouTubeDownloader()
        downloader.run()
    except KeyboardInterrupt:
        print(Fore.RED + "\n✘ Operación cancelada por el usuario")
        sys.exit(130)