#!/usr/bin/env python3
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
        
    def translate(self, text, src='en', dest='es'):
        params = {
            'client': 'gtx',
            'sl': src,
            'tl': dest,
            'dt': 't',
            'q': text
        }
        
        try:
            response = self.session.get(self.base_url, params=params)
            if response.status_code == 200:
                translated = json.loads(response.text)[0][0][0]
                return type('obj', (object,), {'text': translated})
        except Exception as e:
            print(Fore.YELLOW + f"Error de traducción: {str(e)}")
        
        return type('obj', (object,), {'text': text})

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

    def get_playlist_range(self):
        """
        Solicita al usuario un rango de videos para descargar de una lista de reproducción.
        Devuelve el rango como una cadena o None si no se especifica.
        """
        print(Fore.YELLOW + "\n🡆 ¿Deseas descargar un rango específico de videos? (ejemplo: 1-5, 3, 7-)")
        print(Fore.WHITE + "Presiona Enter para descargar toda la lista.")
        range_input = input(">>> ").strip()

        if range_input:
            # Validar formato del rango
            if not re.match(r'^\d+(-\d+)?(-)?$', range_input):
                print(Fore.RED + "✘ Error: Rango inválido. Usa un formato como 1-5, 3, o 7-.")
                sys.exit(1)
            return range_input
        return None

    def download_content(self, url):
        # Obtener rango del usuario (si aplica)
        playlist_range = self.get_playlist_range()
        
        cmd = [
            'yt-dlp',
            '-f', 'bestvideo+bestaudio',
            '--merge-output-format', 'mkv',
            '--convert-subs', 'srt',
            '--write-subs',
            '--write-auto-subs',
            '--sub-langs', 'es',
            '--embed-subs',
            '--ignore-errors',
            '--yes-playlist',
            '-o', str(TEMP_DIR / '%(playlist_index)s_%(title)s.%(ext)s'),  # Incluye índice único
            url
        ]

        # Agregar el rango de la lista si fue proporcionado
        if playlist_range:
            cmd.extend(['--playlist-items', playlist_range])

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )

            current_pbar = None
            stdout_lines = []
            video_count = 0

            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                stdout_lines.append(line.strip())

                # Detectar nuevo video
                if '[download] Destination:' in line:
                    filename = line.split('Destination: ')[1].strip()
                    title = Path(filename).stem[:40]  # Limitar título
                    video_count += 1

                    # Cerrar barra anterior
                    if current_pbar:
                        current_pbar.close()

                    # Crear nueva barra
                    current_pbar = tqdm(
                        total=100,
                        desc=f"{Fore.BLUE}📺 [{video_count}] {title}...",
                        bar_format="{l_bar}{bar:50}{r_bar}",
                        leave=False
                    )

                # Actualizar progreso
                elif '[download]' in line and '%' in line:
                    match = re.search(r'(\d+\.?\d*)%', line)
                    if match and current_pbar:
                        progress = float(match.group(1))
                        current_pbar.n = progress
                        current_pbar.refresh()

            # Cerrar última barra
            if current_pbar:
                current_pbar.close()

            # Verificar errores
            exit_code = process.wait()
            if exit_code != 0:
                raise subprocess.CalledProcessError(exit_code, cmd)

        except subprocess.CalledProcessError as e:
            print(Fore.RED + f"✘ Error en descarga: {str(e)}")
            sys.exit(1)

    def find_files(self):
        video_files = list(TEMP_DIR.glob('*.mkv'))
        all_subs = list(TEMP_DIR.glob('*.srt'))
        
        if not video_files:
            print(Fore.RED + "✘ No se encontró el video descargado")
            sys.exit(1)
            
        self.video_path = video_files[0]
        
        # Clasificar subtítulos
        subs_priority = [
            ('es', False),    # ES manual
            ('en', False),    # EN manual
            ('es', True),     # ES auto
            ('en', True)      # EN auto
        ]
        
        for lang, auto in subs_priority:
            pattern = f'*.{"auto" if auto else ""}{lang}*.srt'
            subs = list(TEMP_DIR.glob(pattern))
            if subs:
                self.subs_path = subs[0]
                print(Fore.CYAN + f"✔ Subtítulos encontrados: {self.subs_path.name}")
                if auto:
                    print(Fore.YELLOW + f"⚠ Usando subtítulos autogenerados en {lang.upper()}")
                return
        
        # Si no hay subtítulos, intentar descargar autogenerados
        print(Fore.YELLOW + "⚠ No se encontraron subtítulos, intentando descarga alternativa...")
        try:
            subprocess.run([
                'yt-dlp',
                '--skip-download',
                '--write-auto-sub',
                '--sub-langs', 'en',
                '-o', str(TEMP_DIR / '%(title)s.%(ext)s'),
                self.url
            ], check=True)
            
            auto_subs = list(TEMP_DIR.glob('*.en.*.srt'))
            if auto_subs:
                self.subs_path = auto_subs[0]
                return
        except Exception as e:
            print(Fore.RED + f"✘ Error en descarga alternativa: {str(e)}")
        
        print(Fore.RED + "✘ No se encontraron subtítulos disponibles")
        sys.exit(1)

    def translate_subs(self, sub_path):
        translated_path = TEMP_DIR / "subs_es.srt"
        
        try:
            with open(sub_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            translated = []
            blocks = content.split('\n\n')
            
            for block in tqdm(blocks, desc=Fore.MAGENTA + "Traduciendo subtítulos",
                             bar_format="{l_bar}{bar:50}{r_bar}"):
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

    def mux_subtitles(self):
        if not self.subs_path:
            print(Fore.YELLOW + "⚠  Sin subtítulos para incluir")
            return
            
        output_path = FINAL_DIR / self.video_path.name
        cmd = [
            'mkvmerge',
            '-o', str(output_path),
            str(self.video_path),
            '--track-name', '0:Español',
            '--language', '0:es',
            '--default-track', '0:true',
            str(self.subs_path)
        ]
        
        try:
            subprocess.run(cmd, check=True)
            print(Fore.GREEN + f"\n✅  Video final creado en: {output_path}")
        except subprocess.CalledProcessError as e:
            print(Fore.RED + f"✘ Error al mezclar subtítulos: {str(e)}")

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

    def run(self):
        self.check_dependencies()
        url = self.get_url()
        self.download_content(url)
        self.find_files()
        self.mux_subtitles()
        self.clean_up()

if __name__ == "__main__":
    try:
        downloader = YouTubeDownloader()
        downloader.run()
    except KeyboardInterrupt:
        print(Fore.RED + "\n✘ Operación cancelada por el usuario")
        sys.exit(130)