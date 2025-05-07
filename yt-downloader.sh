#!/bin/bash

# Configuración de colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ASCII Art
echo -e "${YELLOW}"
cat << "EOF"
          __                .___.__          
 ___.__._/  |_            __| _/|  | ______  
<   |  |\   __\  ______  / __ | |  | \____ \ 
 \___  | |  |   /_____/ / /_/ | |  |_|  |_> >
 / ____| |__|           \____ | |____/   __/ 
 \/                          \/      |__|
EOF
echo -e "${NC}"

# Verificar dependencias
check_dependencies() {
    local missing=()
    command -v yt-dlp >/dev/null 2>&1 || missing+=("yt-dlp")
    command -v mkvmerge >/dev/null 2>&1 || missing+=("mkvtoolnix")
    command -v python3 >/dev/null 2>&1 || missing+=("python3")
    command -v zenity >/dev/null 2>&1 || missing+=("zenity (opcional)")

    if [ ${#missing[@]} -gt 0 ]; then
        echo -e "${RED}Error: Faltan dependencias:${NC} ${missing[*]}"
        exit 1
    fi
}

# Obtener URL mediante interfaz gráfica o terminal
get_url() {
    if [ -n "$DISPLAY" ] && command -v zenity >/dev/null 2>&1; then
        URL=$(zenity --entry \
            --title="Descargar contenido de YouTube" \
            --text="Ingrese la URL del video o lista de reproducción:" \
            --width=400 2>/dev/null)
    else
        echo -e "${BLUE}"
        read -p "Ingrese la URL del video/lista de YouTube: " URL
        echo -e "${NC}"
    fi

    if [ -z "$URL" ]; then
        echo -e "${RED}Error: No se proporcionó URL${NC}"
        exit 1
    fi
}

show_progress() {
    if [ -n "$DISPLAY" ] && command -v zenity >/dev/null 2>&1; then
        (
        echo "10" ; sleep 1
        echo "# Verificando dependencias..." ; check_dependencies
        echo "25" ; sleep 1
        echo "# Descargando contenido..." ; download_content
        echo "50" ; sleep 1
        echo "# Procesando subtítulos..." ; process_subtitles
        echo "75" ; sleep 1
        echo "# Generando archivo final..." ; create_final
        echo "100" ; sleep 1
        ) | zenity --progress \
          --title="Progreso de la descarga" \
          --percentage=0 \
          --auto-close
    else
        check_dependencies
        download_content
        process_subtitles
        create_final
    fi
}

download_content() {
    echo -e "${GREEN}Iniciando descarga...${NC}"
    yt-dlp -f "bestvideo+bestaudio" \
        --cookies-from-browser chrome:~/.config/google-chrome \
        --merge-output-format mkv \
        --convert-subs srt \
        --write-subs \
        --write-auto-subs \
        --sub-langs "es,en.*" \
        --output "./temp/%(title)s.%(ext)s" \
        "$URL"
}

process_subtitles() {
    DIR=./temp
    if [ ! -d "$DIR" ];
    then
    	mkdir $DIR
    fi
    EN_SUB=$(find ./temp -name '*.en.*.srt' | head -1)
    ES_SUB=$(find ./temp -name '*.es.*.srt' | head -1)
    VIDEO=$(find ./temp -name '*.mkv' | head -1)

    if [ -z "$ES_SUB" ] && [ -n "$EN_SUB" ]; then
        echo -e "${YELLOW}Traduciendo subtítulos al español...${NC}"
        python3 -c "
from googletrans import Translator
import sys

def translate_subs(input_file, output_file):
    translator = Translator()
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read().split('\n\n')
    
    translated = []
    for block in content:
        lines = block.split('\n')
        if len(lines) >= 3:
            try:
                translated_text = translator.translate('\n'.join(lines[2:]), src='en', dest='es').text
                translated.append('\n'.join(lines[:2] + [translated_text]))
            except:
                translated.append(block)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n\n'.join(translated))

translate_subs('$EN_SUB', './temp/subs_es.srt')"
        ES_SUB="./temp/subs_es.srt"
    fi
}

create_final() {
    if [ -n "$ES_SUB" ] && [ -n "$VIDEO" ]; then
        echo -e "${GREEN}Creando archivo final...${NC}"
        DIR=./FINAL
        if [ ! -d "$DIR" ];
        then
            mkdir $DIR
        fi
        mkvmerge -o "${DIR}/$(basename "$VIDEO")" \
            "$VIDEO" \
            --track-name 0:Español \
            --language 0:es \
            --default-track 0:true \
            "$ES_SUB"

        echo -e "${GREEN}Proceso completado!${NC}"
        echo -e "Video guardado en: ${BLUE}${DIR}${NC}"
    else
        echo -e "${YELLOW}Advertencia: No se encontraron subtítulos para incluir${NC}"
    fi

    # Limpieza
    rm -rf ./temp
}

# Ejecución principal
check_dependencies
get_url
show_progress