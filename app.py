from flask import Flask, render_template, send_from_directory, request, redirect, url_for
from werkzeug.utils import secure_filename
import json
import os
import shutil
import threading
import time
from datetime import datetime

app = Flask(__name__)

cerrojo_stats = threading.Lock()
ARCHIVO_STATS = 'stats.json'
ARCHIVO_EXPIRACIONES = 'expiraciones.json'
CARPETA_INFORMES = 'informes_diarios'
CARPETA_VIDEOS_RAIZ = os.path.join('static', 'videos')

# EXTENSIONES PERMITIDAS (Videos y Fotos)
EXT_VIDEOS = ('.mp4', '.mov')
EXT_FOTOS = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
EXT_MEDIA = EXT_VIDEOS + EXT_FOTOS

for carpeta in [CARPETA_INFORMES, CARPETA_VIDEOS_RAIZ]:
    if not os.path.exists(carpeta): os.makedirs(carpeta)

# --- SISTEMA DE AUTODESTRUCCIÓN ---
def cargar_expiraciones():
    if os.path.exists(ARCHIVO_EXPIRACIONES):
        with open(ARCHIVO_EXPIRACIONES, 'r') as f:
            try: return json.load(f)
            except: return {}
    return {}

def guardar_expiraciones(data):
    with open(ARCHIVO_EXPIRACIONES, 'w') as f: json.dump(data, f)

def limpiar_expirados():
    exp = cargar_expiraciones()
    ahora = time.time()
    modificado = False
    rutas_a_borrar = []

    for ruta, info in exp.items():
        limite_val = str(info.get('limite', '0'))
        segundos_limite = 0
        if limite_val.endswith('m'): segundos_limite = int(limite_val.replace('m', '')) * 60
        elif limite_val.endswith('h'): segundos_limite = int(limite_val.replace('h', '')) * 3600
        else: segundos_limite = int(limite_val) * 3600

        if segundos_limite > 0:
            fecha_creacion = info.get('creacion', 0)
            if ahora > fecha_creacion + segundos_limite:
                rutas_a_borrar.append(ruta)

    for ruta in rutas_a_borrar:
        ruta_fisica = os.path.join(CARPETA_VIDEOS_RAIZ, ruta)
        if os.path.exists(ruta_fisica):
            try:
                if os.path.isdir(ruta_fisica): shutil.rmtree(ruta_fisica) 
                else: os.remove(ruta_fisica) 
            except Exception as e: print(f"Error auto-borrando {ruta}: {e}")
        del exp[ruta]
        modificado = True

    if modificado: guardar_expiraciones(exp)

@app.before_request
def vigilante_de_tiempo():
    limpiar_expirados()

# --- ESTADÍSTICAS ---
def obtener_fecha_hoy(): return datetime.now().strftime("%Y-%m-%d")

def cargar_estadisticas():
    hoy = obtener_fecha_hoy()
    stats_default = {"fecha": hoy, "descargas": {}}
    if os.path.exists(ARCHIVO_STATS):
        with open(ARCHIVO_STATS, 'r') as f:
            try: data = json.load(f)
            except: data = stats_default
            if data.get("fecha") != hoy and "fecha" in data:
                generar_informe(data)
                return stats_default
            if "fecha" not in data: data = {"fecha": hoy, "descargas": data}
            return data
    return stats_default

def generar_informe(data_vieja):
    fecha_ayer = data_vieja.get("fecha", "Desconocida")
    descargas = data_vieja.get("descargas", {})
    ruta = os.path.join(CARPETA_INFORMES, f"informe_{fecha_ayer}.txt")
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write(f"=== INFORME VIP ===\nFecha: {fecha_ayer}\n\n")
        total = sum(descargas.values())
        for video, cantidad in descargas.items(): f.write(f"- {video}: {cantidad} descargas\n")
        f.write(f"\nTOTAL: {total} DESCARGAS\n")

def guardar_estadisticas(data):
    with open(ARCHIVO_STATS, 'w') as f: json.dump(data, f)

# --- ESCÁNER JERÁRQUICO Y RENOMBRAMIENTO ---
def obtener_siguiente_numero():
    max_num = 0
    for root, dirs, files in os.walk(CARPETA_VIDEOS_RAIZ):
        for file in files:
            nombre, ext = os.path.splitext(file)
            if nombre.lower().startswith('video_'):
                partes = nombre.split('_')
                if len(partes) >= 2:
                    try:
                        num = int(partes[1])
                        if num > max_num:
                            max_num = num
                    except ValueError:
                        pass
    return max_num + 1

def escanear_contenido_carpeta(subcarpeta_relativa=''):
    ruta_fisica = os.path.join(CARPETA_VIDEOS_RAIZ, subcarpeta_relativa)
    if not os.path.commonprefix([os.path.abspath(ruta_fisica), os.path.abspath(CARPETA_VIDEOS_RAIZ)]) == os.path.abspath(CARPETA_VIDEOS_RAIZ):
        ruta_fisica = CARPETA_VIDEOS_RAIZ
        subcarpeta_relativa = ''

    contenido = {"carpetas": [], "videos": []}
    if not os.path.exists(ruta_fisica): return contenido

    exp = cargar_expiraciones() 

    for item in os.listdir(ruta_fisica):
        ruta_completa_item = os.path.join(ruta_fisica, item)
        ruta_web_relativa = os.path.join(subcarpeta_relativa, item).replace('\\', '/')
        
        info_exp = exp.get(ruta_web_relativa, {})
        limite_val = str(info_exp.get('limite', '0'))
        fecha_creacion = info_exp.get('creacion', 0)
        segundos_limite = 0
        if limite_val.endswith('m'): segundos_limite = int(limite_val.replace('m', '')) * 60
        elif limite_val.endswith('h'): segundos_limite = int(limite_val.replace('h', '')) * 3600
        else: segundos_limite = int(limite_val) * 3600 if int(limite_val) > 0 else 0

        timestamp_exp = fecha_creacion + segundos_limite if segundos_limite > 0 else 0

        if os.path.isdir(ruta_completa_item):
            contenido["carpetas"].append({"nombre": item, "ruta_relativa": ruta_web_relativa, "timestamp_exp": timestamp_exp, "total_segundos": segundos_limite})
        elif item.lower().endswith(EXT_MEDIA):
            tipo_media = 'foto' if item.lower().endswith(EXT_FOTOS) else 'video'
            titulo_limpio = item.rsplit('.', 1)[0].replace('_', ' ')
            contenido["videos"].append({"archivo": item, "ruta_completa_descarga": ruta_web_relativa, "titulo": titulo_limpio, "timestamp_exp": timestamp_exp, "total_segundos": segundos_limite, "tipo": tipo_media})
    return contenido

def obtener_todo_el_catalogo_flat():
    videos = []
    id_counter = 1
    for root, dirs, files in os.walk(CARPETA_VIDEOS_RAIZ):
        for file in files:
            if file.lower().endswith(EXT_MEDIA):
                tipo_media = 'foto' if file.lower().endswith(EXT_FOTOS) else 'video'
                ruta_relativa = os.path.relpath(os.path.join(root, file), CARPETA_VIDEOS_RAIZ).replace('\\', '/')
                carpeta_madre = os.path.basename(root) if root != CARPETA_VIDEOS_RAIZ else "General"
                titulo_limpio = file.rsplit('.', 1)[0].replace('_', ' ')
                videos.append({"id": id_counter, "carpeta": carpeta_madre, "archivo": file, "ruta_relativa": ruta_relativa, "titulo": titulo_limpio, "tipo": tipo_media})
                id_counter += 1
    return videos

def obtener_lista_carpetas_flat():
    carpetas = []
    for root, dirs, files in os.walk(CARPETA_VIDEOS_RAIZ):
        if root != CARPETA_VIDEOS_RAIZ: carpetas.append(os.path.relpath(root, CARPETA_VIDEOS_RAIZ).replace('\\', '/'))
    return carpetas

# --- RUTAS PÚBLICAS Y ADMIN STATS ---
@app.route('/')
def index():
    carpeta_actual = request.args.get('carpeta', default='')
    contenido = escanear_contenido_carpeta(carpeta_actual)
    return render_template('index.html', carpetas=contenido["carpetas"], videos=contenido["videos"], carpeta_actual=carpeta_actual)

@app.route('/ver/<path:ruta_video>')
def ver_video(ruta_video):
    titulo_limpio = os.path.basename(ruta_video).rsplit('.', 1)[0].replace('_', ' ')
    tipo_media = 'foto' if ruta_video.lower().endswith(EXT_FOTOS) else 'video'
    video_seleccionado = {"titulo": titulo_limpio, "archivo": os.path.basename(ruta_video), "ruta_relativa": ruta_video, "tipo": tipo_media}
    return render_template('reproductor.html', video=video_seleccionado)

# --- AQUÍ ESTÁ EL TRUCO DE LA HORA PARA LA GALERÍA ---
@app.route('/download/<path:filename>')
def download_video(filename):
    nombre_limpio_archivo = os.path.basename(filename)
    ruta_fisica = os.path.join(CARPETA_VIDEOS_RAIZ, filename)
    
    # Actualiza la fecha del archivo a "AHORA" para que salga de primero en la galería
    if os.path.exists(ruta_fisica):
        os.utime(ruta_fisica, None)
        
    with cerrojo_stats:
        data = cargar_estadisticas()
        descargas = data["descargas"]
        descargas[nombre_limpio_archivo] = descargas.get(nombre_limpio_archivo, 0) + 1
        data["descargas"] = descargas
        guardar_estadisticas(data)
        
    return send_from_directory(CARPETA_VIDEOS_RAIZ, filename, as_attachment=True)

@app.route('/admin-stats')
def panel_admin_stats():
    with cerrojo_stats: data = cargar_estadisticas()
    descargas = data["descargas"]
    fecha_hoy = data["fecha"]
    catalogo_flat = obtener_todo_el_catalogo_flat()
    datos_completos = []
    for v in catalogo_flat:
        datos_completos.append({"titulo": v['titulo'], "carpeta": v['carpeta'], "archivo": v['archivo'], "descargas": descargas.get(v['archivo'], 0)})
    return render_template('admin.html', videos=datos_completos, fecha=fecha_hoy)

# --- RUTAS DEL EDITOR ---
@app.route('/editor-visual')
def editor_visual():
    subcarpeta_a_ver = request.args.get('carpeta', default='')
    contenido = escanear_contenido_carpeta(subcarpeta_a_ver)
    todas_las_carpetas = obtener_lista_carpetas_flat()
    return render_template('editor.html', carpetas=contenido["carpetas"], videos=contenido["videos"], carpeta_actual=subcarpeta_a_ver, todas_las_carpetas=todas_las_carpetas)

@app.route('/admin/crear-carpeta', methods=['POST'])
def crear_carpeta():
    carpeta_padre_actual = request.form.get('carpeta_actual', '')
    nueva_carpeta_nombre = request.form.get('nombre_carpeta')
    tiempo_limite = request.form.get('tiempo_limite', '0')

    if nueva_carpeta_nombre:
        nombre_seguro = secure_filename(nueva_carpeta_nombre)
        ruta_relativa = os.path.join(carpeta_padre_actual, nombre_seguro).replace('\\', '/')
        ruta_fisica_final = os.path.join(CARPETA_VIDEOS_RAIZ, carpeta_padre_actual, nombre_seguro)
        
        if not os.path.exists(ruta_fisica_final):
            os.makedirs(ruta_fisica_final)
            if tiempo_limite != '0':
                exp = cargar_expiraciones()
                exp[ruta_relativa] = {"tipo": "carpeta", "limite": tiempo_limite, "creacion": time.time()}
                guardar_expiraciones(exp)
    return redirect(url_for('editor_visual', carpeta=carpeta_padre_actual))

@app.route('/admin/subir-video', methods=['POST'])
def subir_video():
    carpeta_actual = request.form.get('carpeta_actual', '')
    video_file = request.files.get('video_file')
    tiempo_limite = request.form.get('tiempo_limite', '0')
    
    if video_file and video_file.filename.lower().endswith(EXT_MEDIA):
        ext_original = os.path.splitext(video_file.filename)[1].lower()
        ext_final = ext_original if ext_original in EXT_MEDIA else '.mp4'
        
        siguiente_num = obtener_siguiente_numero()
        nombre_archivo_seguro = f"video_{siguiente_num}{ext_final}"
        
        ruta_relativa = os.path.join(carpeta_actual, nombre_archivo_seguro).replace('\\', '/')
        ruta_fisica_guardado = os.path.join(CARPETA_VIDEOS_RAIZ, carpeta_actual, nombre_archivo_seguro)
        
        video_file.save(ruta_fisica_guardado)

        if tiempo_limite != '0':
            exp = cargar_expiraciones()
            exp[ruta_relativa] = {"tipo": "archivo", "limite": tiempo_limite, "creacion": time.time()}
            guardar_expiraciones(exp)
        
    return redirect(url_for('editor_visual', carpeta=carpeta_actual))

@app.route('/admin/mover-video', methods=['POST'])
def mover_video():
    ruta_video_origen_web = request.form.get('video_origen') 
    carpeta_destino_web = request.form.get('carpeta_destino')
    carpeta_vista_actual = request.form.get('carpeta_actual', '')
    
    if ruta_video_origen_web and carpeta_destino_web:
        ruta_fisica_abs_origen = os.path.join(CARPETA_VIDEOS_RAIZ, ruta_video_origen_web)
        nombre_archivo = os.path.basename(ruta_video_origen_web)
        
        if carpeta_destino_web == "Raiz": ruta_fisica_abs_destino_carpeta = CARPETA_VIDEOS_RAIZ
        else: ruta_fisica_abs_destino_carpeta = os.path.join(CARPETA_VIDEOS_RAIZ, carpeta_destino_web)
            
        ruta_fisica_final_archivo = os.path.join(ruta_fisica_abs_destino_carpeta, nombre_archivo)
        
        if os.path.exists(ruta_fisica_abs_origen):
            if not os.path.exists(ruta_fisica_abs_destino_carpeta): os.makedirs(ruta_fisica_abs_destino_carpeta)
            if ruta_fisica_abs_origen != ruta_fisica_final_archivo:
                shutil.move(ruta_fisica_abs_origen, ruta_fisica_final_archivo)
                exp = cargar_expiraciones()
                if ruta_video_origen_web in exp:
                    carpeta_limpia = carpeta_destino_web if carpeta_destino_web != "Raiz" else ""
                    nueva_ruta_relativa = os.path.join(carpeta_limpia, nombre_archivo).replace('\\', '/')
                    exp[nueva_ruta_relativa] = exp.pop(ruta_video_origen_web)
                    guardar_expiraciones(exp)
                
    return redirect(url_for('editor_visual', carpeta=carpeta_vista_actual))

@app.route('/admin/eliminar', methods=['POST'])
def eliminar_item():
    item_ruta = request.form.get('item_ruta') 
    tipo = request.form.get('tipo') 
    carpeta_actual = request.form.get('carpeta_actual', '')

    if item_ruta and tipo:
        ruta_fisica_abs = os.path.join(CARPETA_VIDEOS_RAIZ, item_ruta)
        if os.path.commonprefix([os.path.abspath(ruta_fisica_abs), os.path.abspath(CARPETA_VIDEOS_RAIZ)]) == os.path.abspath(CARPETA_VIDEOS_RAIZ):
            if os.path.exists(ruta_fisica_abs):
                try:
                    if tipo == 'video': os.remove(ruta_fisica_abs) 
                    elif tipo == 'carpeta': shutil.rmtree(ruta_fisica_abs) 
                except Exception as e: print(f"Error al borrar: {e}")
                exp = cargar_expiraciones()
                if item_ruta in exp:
                    del exp[item_ruta]
                    guardar_expiraciones(exp)
                    
    return redirect(url_for('editor_visual', carpeta=carpeta_actual))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)