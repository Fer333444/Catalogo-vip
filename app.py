from flask import Flask, render_template, send_from_directory, request, redirect, url_for, make_response, session, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import smtplib
from email.mime.text import MIMEText
import json
import os
import shutil
import threading
import time
import uuid
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'super_clave_secreta_vip_cambiame' 

# --- CONFIGURACIÓN DE RUTAS (CONECTANDO EL DISCO) ---
# Usamos '/data' en Render, o una carpeta 'data' local si estás probando en tu PC
BASE_DIR = '/data' if os.environ.get('RENDER') else 'data'

cerrojo_stats = threading.Lock()
ARCHIVO_STATS = os.path.join(BASE_DIR, 'stats.json')
ARCHIVO_EXPIRACIONES = os.path.join(BASE_DIR, 'expiraciones.json')
ARCHIVO_USUARIOS = os.path.join(BASE_DIR, 'usuarios.json')
CARPETA_INFORMES = os.path.join(BASE_DIR, 'informes_diarios')
CARPETA_VIDEOS_RAIZ = os.path.join(BASE_DIR, 'videos')

# --- CONFIGURACIÓN DE CORREO (BREVO) ---
SMTP_SERVER = "smtp-relay.brevo.com"
SMTP_PORT = 587
SMTP_USERNAME = "a6199f001@smtp-brevo.com"  # Tu nuevo usuario de la captura
SMTP_PASSWORD = os.environ.get("CLAVE_BREVO") # <-- ¡Aquí está la magia!
CORREO_REMITENTE = "contenido2025yt@gmail.com"  # Tu nuevo correo

EXT_VIDEOS = ('.mp4', '.mov')
EXT_FOTOS = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
EXT_MEDIA = EXT_VIDEOS + EXT_FOTOS

for carpeta in [BASE_DIR, CARPETA_INFORMES, CARPETA_VIDEOS_RAIZ]:
    if not os.path.exists(carpeta): os.makedirs(carpeta)

def cargar_usuarios():
    if os.path.exists(ARCHIVO_USUARIOS):
        with open(ARCHIVO_USUARIOS, 'r') as f:
            try: return json.load(f)
            except: return {}
    return {}

def guardar_usuarios(data):
    with open(ARCHIVO_USUARIOS, 'w') as f: json.dump(data, f)

def enviar_correo_verificacion(destinatario, token, url_base):
    enlace = f"{url_base}verificar/{token}"
    
    # Diseño limpio con un botón pequeño y discreto (Amigable con la Bandeja Principal)
    html_content = f"""
    <div style="font-family: Arial, sans-serif; font-size: 15px; color: #222; max-width: 600px; padding: 20px;">
        <p>Hola,</p>
        <p>Gracias por registrarte en Publicidad Vip. Ya casi terminamos.</p>
        <p>Para activar tu cuenta de forma segura, haz clic en el botón de abajo:</p>
        
        <p style="margin: 25px 0;">
            <a href="{enlace}" style="background-color: #1a73e8; color: #ffffff; padding: 10px 20px; text-decoration: none; font-weight: bold; border-radius: 6px; font-size: 14px; display: inline-block;">Verificar mi cuenta</a>
        </p>
        
        <p style="font-size: 12px; color: #777; margin-top: 30px;">Si el botón no funciona, copia y pega este enlace en tu navegador:<br>{enlace}</p>
        <br>
        <p>Saludos cordiales,<br>El Equipo de Publicidad Vip</p>
    </div>
    """
    
    msg = MIMEText(html_content, 'html')
    msg['Subject'] = 'Tu acceso a Publicidad Vip'  # Asunto limpio y directo
    msg['From'] = CORREO_REMITENTE
    msg['To'] = destinatario

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(CORREO_REMITENTE, [destinatario], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Error enviando correo con Brevo: {e}")
        return False

def login_requerido(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# --- NUEVAS RUTAS SEPARADAS DE LOGIN Y REGISTRO ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'usuario' in session: return redirect(url_for('index'))
    
    if request.method == 'POST':
        correo = request.form.get('correo').lower().strip()
        password = request.form.get('password')
        usuarios = cargar_usuarios()

        user = usuarios.get(correo)
        if user and check_password_hash(user['password'], password):
            if not user['verificado']:
                flash("Debes revisar tu correo y verificar tu cuenta primero.", "error")
            else:
                session['usuario'] = correo
                session.permanent = True
                return redirect(url_for('index'))
        else:
            flash("Correo o contraseña incorrectos.", "error")

    return render_template('login.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if 'usuario' in session: return redirect(url_for('index'))
    
    if request.method == 'POST':
        correo = request.form.get('correo').lower().strip()
        password = request.form.get('password')
        usuarios = cargar_usuarios()

        if correo in usuarios:
            flash("Este correo ya está registrado. Por favor, inicia sesión.", "error")
            return redirect(url_for('login'))
        else:
            token = str(uuid.uuid4())
            usuarios[correo] = {
                "password": generate_password_hash(password),
                "verificado": False,
                "token": token
            }
            guardar_usuarios(usuarios)
            url_base = request.host_url 
            enviado = enviar_correo_verificacion(correo, token, url_base)
            if enviado:
                flash("¡Registro exitoso! Revisa tu correo (y Spam) y dale al botón para verificar tu cuenta.", "exito")
                return redirect(url_for('login'))
            else:
                flash("Error al enviar el correo. Intenta de nuevo.", "error")

    return render_template('registro.html')

# --------------------------------------------------

@app.route('/verificar/<token>')
def verificar(token):
    usuarios = cargar_usuarios()
    for correo, datos in usuarios.items():
        if datos.get('token') == token:
            usuarios[correo]['verificado'] = True
            usuarios[correo]['token'] = None 
            guardar_usuarios(usuarios)
            session['usuario'] = correo 
            session.permanent = True
            return redirect(url_for('index'))
    return "Enlace inválido o expirado."

@app.route('/logout')
def logout():
    session.pop('usuario', None)
    return redirect(url_for('login'))
@app.route('/perfil')
@login_requerido
def perfil():
    # Abre la página del perfil. (El correo ya se envía automáticamente por la session)
    return render_template('perfil.html')

@app.route('/eliminar-mi-cuenta', methods=['POST'])
@login_requerido
def eliminar_mi_cuenta():
    correo = session.get('usuario')
    usuarios = cargar_usuarios()
    
    # Si el usuario existe en la base de datos, lo borramos
    if correo and correo in usuarios:
        del usuarios[correo]
        guardar_usuarios(usuarios)
        
    # Cerramos su sesión forzosamente
    session.pop('usuario', None)
    flash("Tu cuenta ha sido eliminada. Lamentamos verte ir.", "exito")
    return redirect(url_for('login'))

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
            if ahora > fecha_creacion + segundos_limite: rutas_a_borrar.append(ruta)
    for ruta in rutas_a_borrar:
        ruta_fisica = os.path.join(CARPETA_VIDEOS_RAIZ, ruta)
        if os.path.exists(ruta_fisica):
            try:
                if os.path.isdir(ruta_fisica): shutil.rmtree(ruta_fisica) 
                else: os.remove(ruta_fisica) 
            except Exception as e: pass
        del exp[ruta]
        modificado = True
    if modificado: guardar_expiraciones(exp)

@app.before_request
def vigilante_de_tiempo():
    limpiar_expirados()

def obtener_fecha_hoy(): return datetime.now().strftime("%Y-%m-%d")

def cargar_estadisticas():
    hoy = obtener_fecha_hoy()
    stats_default = {"fecha": hoy, "descargas": {}, "visitas": 0}
    if os.path.exists(ARCHIVO_STATS):
        with open(ARCHIVO_STATS, 'r') as f:
            try: data = json.load(f)
            except: data = stats_default
            if data.get("fecha") != hoy and "fecha" in data: return stats_default
            if "fecha" not in data: data["fecha"] = hoy
            if "descargas" not in data: data["descargas"] = {}
            if "visitas" not in data: data["visitas"] = 0
            return data
    return stats_default

def guardar_estadisticas(data):
    with open(ARCHIVO_STATS, 'w') as f: json.dump(data, f)

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
                        if num > max_num: max_num = num
                    except ValueError: pass
    return max_num + 1

def escanear_contenido_carpeta(ruta_relativa=''):
    ruta_completa = os.path.join(CARPETA_VIDEOS_RAIZ, ruta_relativa)
    carpetas = []
    videos = []
    if not os.path.exists(ruta_completa):
        return {'carpetas': carpetas, 'videos': videos}

    expiraciones = cargar_expiraciones()
    ahora = int(time.time())
    modificado = False

    for elemento in sorted(os.listdir(ruta_completa)):
        ruta_elemento = os.path.join(ruta_completa, elemento)
        ruta_relativa_elemento = os.path.join(ruta_relativa, elemento).replace('\\', '/')

        if os.path.isdir(ruta_elemento):
            # --- NUEVA LÓGICA DE COLLAGE PARA CARPETAS ---
            previsualizaciones = []
            try:
                contenido_interior = os.listdir(ruta_elemento)
                for item_interior in sorted(contenido_interior):
                    if item_interior.lower().endswith(EXT_MEDIA):
                        ruta_relativa_interior = os.path.join(ruta_relativa_elemento, item_interior).replace('\\', '/')
                        previsualizaciones.append(ruta_relativa_interior)
                        if len(previsualizaciones) == 4:
                            break
            except:
                pass

            carpetas.append({
                'nombre': elemento,
                'ruta_relativa': ruta_relativa_elemento,
                'miniaturas_collage': previsualizaciones
            })
        elif os.path.isfile(ruta_elemento) and elemento.lower().endswith(EXT_MEDIA):
            exp_data = expiraciones.get(ruta_relativa_elemento, {})
            expira_en = exp_data.get('expira_en', 0)
            total_segundos = exp_data.get('total_segundos', 0)

            if expira_en > 0 and ahora > expira_en:
                try:
                    os.remove(ruta_elemento)
                    del expiraciones[ruta_relativa_elemento]
                    modificado = True
                except: pass
                continue

            tipo = 'foto' if elemento.lower().endswith(EXT_FOTOS) else 'video'
            
            # Transformamos "video_1.mp4" a "Video 1" visualmente elegante
            titulo_limpio = elemento.rsplit('.', 1)[0].replace('_', ' ').title()

            videos.append({
                'archivo': elemento,
                'titulo': titulo_limpio,
                'ruta_completa_descarga': ruta_relativa_elemento,
                'tipo': tipo,
                'timestamp_exp': expira_en,
                'total_segundos': total_segundos
            })
            
    if modificado: guardar_expiraciones(expiraciones)
    return {'carpetas': carpetas, 'videos': videos}

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

@app.route('/')
@login_requerido
def index():
    with cerrojo_stats:
        data = cargar_estadisticas()
        data["visitas"] = data.get("visitas", 0) + 1
        guardar_estadisticas(data)
        
    carpeta_actual = request.args.get('carpeta', default='')
    contenido = escanear_contenido_carpeta(carpeta_actual)
    return render_template('index.html', carpetas=contenido["carpetas"], videos=contenido["videos"], carpeta_actual=carpeta_actual)

@app.route('/ver/<path:ruta_video>')
@login_requerido
def ver_video(ruta_video):
    titulo_limpio = os.path.basename(ruta_video).rsplit('.', 1)[0].replace('_', ' ')
    tipo_media = 'foto' if ruta_video.lower().endswith(EXT_FOTOS) else 'video'
    video_seleccionado = {"titulo": titulo_limpio, "archivo": os.path.basename(ruta_video), "ruta_relativa": ruta_video, "tipo": tipo_media}
    return render_template('reproductor.html', video=video_seleccionado)

@app.route('/download/<path:filename>')
@login_requerido
def download_video(filename):
    nombre_limpio_archivo = os.path.basename(filename)
    ruta_fisica = os.path.join(CARPETA_VIDEOS_RAIZ, filename)
    
    if os.path.exists(ruta_fisica): os.utime(ruta_fisica, None)
        
    with cerrojo_stats:
        data = cargar_estadisticas()
        descargas = data["descargas"]
        descargas[nombre_limpio_archivo] = descargas.get(nombre_limpio_archivo, 0) + 1
        data["descargas"] = descargas
        guardar_estadisticas(data)
        
    respuesta = make_response(send_from_directory(CARPETA_VIDEOS_RAIZ, filename, as_attachment=True))
    respuesta.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    respuesta.headers["Pragma"] = "no-cache"
    respuesta.headers["Expires"] = "0"
    return respuesta
# --- GENERADOR DEL INFORME EJECUTIVO EN TXT ---
def generar_informe_txt(visitas, videos_ordenados, fecha):
    hora_actual = datetime.now().strftime("%H:%M:%S")
    ruta_informe = os.path.join(CARPETA_INFORMES, f"informe_{fecha}.txt")
    
    total_descargas = sum(v['descargas'] for v in videos_ordenados)
    
    tasa_interaccion = 0.0
    if visitas > 0:
        tasa_interaccion = round((total_descargas / visitas) * 100, 1)

    mejor_video = "Aún no hay descargas"
    if videos_ordenados and videos_ordenados[0]['descargas'] > 0:
        mejor_video = f"{videos_ordenados[0]['titulo']} con {videos_ordenados[0]['descargas']} descargas!"

    lineas = [
        "=========================================================",
        "          📊 INFORME DIARIO - PUBLICIDAD VIP             ",
        "=========================================================",
        f"📅 Fecha del reporte: {fecha}",
        f"⏱️ Generado/Actualizado a las: {hora_actual}",
        "---------------------------------------------------------",
        " 📈 RESUMEN GENERAL:",
        f"  👁️  Personas que entraron al catálogo: {visitas}",
        f"  📥  Total de descargas (todos los videos): {total_descargas}",
        f"  🔥  Tasa de interacción: {tasa_interaccion}%",
        "---------------------------------------------------------",
        " 🏆 EL CONTENIDO ESTRELLA DEL DÍA:",
        f"      >> {mejor_video} <<",
        "---------------------------------------------------------",
        " 📋 DESGLOSE POR VIDEO (Del más al menos descargado):\n"
    ]

    for v in videos_ordenados:
        carpeta_txt = v['carpeta'] if v['carpeta'] else 'Raíz'
        lineas.append(f"  - {v['descargas']:>2} descargas | [{carpeta_txt}] {v['titulo']}")

    lineas.append("\n=========================================================")
    lineas.append(" Fin del reporte.")

    # Guardamos el archivo en la caja fuerte usando UTF-8 para que soporten emojis
    with open(ruta_informe, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lineas))


@app.route('/admin-stats')
def panel_admin_stats():
    with cerrojo_stats: 
        data = cargar_estadisticas()
    
    descargas = data.get("descargas", {})
    fecha_hoy = data.get("fecha", obtener_fecha_hoy())
    visitas_hoy = data.get("visitas", 0)
    
    catalogo_flat = obtener_todo_el_catalogo_flat()
    datos_completos = []
    
    for v in catalogo_flat:
        datos_completos.append({
            "titulo": v['titulo'], 
            "carpeta": v['carpeta'], 
            "archivo": v['archivo'], 
            "descargas": descargas.get(v['archivo'], 0),
            "ruta_relativa": v['ruta_relativa'],
            "tipo": v['tipo']
        })
        
    # Ordenamos de más descargas a menos
    datos_completos.sort(key=lambda x: x['descargas'], reverse=True)
    
    # ¡LA MAGIA AQUÍ! Generamos el reporte .txt en segundo plano automáticamente
    generar_informe_txt(visitas_hoy, datos_completos, fecha_hoy)
    
    return render_template('admin.html', videos=datos_completos, fecha=fecha_hoy, visitas=visitas_hoy)

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
    horas = int(request.form.get('horas', 0))
    minutos = int(request.form.get('minutos', 0))
    
    if nueva_carpeta_nombre:
        nombre_seguro = secure_filename(nueva_carpeta_nombre)
        ruta_relativa = os.path.join(carpeta_padre_actual, nombre_seguro).replace('\\', '/')
        ruta_fisica_final = os.path.join(CARPETA_VIDEOS_RAIZ, carpeta_padre_actual, nombre_seguro)
        
        if not os.path.exists(ruta_fisica_final):
            os.makedirs(ruta_fisica_final)
            
            # Convertimos horas y minutos a segundos
            tiempo_segundos = (horas * 3600) + (minutos * 60)
            if tiempo_segundos > 0:
                exp = cargar_expiraciones()
                exp[ruta_relativa] = {"tipo": "carpeta", "limite": str(tiempo_segundos), "creacion": time.time()}
                guardar_expiraciones(exp)
                
    return redirect(url_for('editor_visual', carpeta=carpeta_padre_actual))
@app.route('/admin/renombrar-carpeta', methods=['POST'])
@login_requerido
def renombrar_carpeta():
    carpeta_actual = request.form.get('carpeta_actual', '')
    nombre_viejo = request.form.get('nombre_viejo')
    nombre_nuevo = request.form.get('nombre_nuevo')

    if nombre_viejo and nombre_nuevo:
        nombre_seguro = secure_filename(nombre_nuevo)
        ruta_base = os.path.join(CARPETA_VIDEOS_RAIZ, carpeta_actual)
        ruta_vieja_fisica = os.path.join(ruta_base, nombre_viejo)
        ruta_nueva_fisica = os.path.join(ruta_base, nombre_seguro)

        if os.path.exists(ruta_vieja_fisica) and not os.path.exists(ruta_nueva_fisica):
            # 1. Renombramos la carpeta en el disco
            os.rename(ruta_vieja_fisica, ruta_nueva_fisica)
            
            # 2. Actualizamos el archivo de expiraciones para que no pierdan su contador
            exp = cargar_expiraciones()
            exp_modificado = False
            rutas_viejas_relativas = os.path.join(carpeta_actual, nombre_viejo).replace('\\', '/')
            rutas_nuevas_relativas = os.path.join(carpeta_actual, nombre_seguro).replace('\\', '/')

            nuevas_expiraciones = {}
            for ruta_key, info in exp.items():
                if ruta_key.startswith(rutas_viejas_relativas):
                    nueva_ruta_key = ruta_key.replace(rutas_viejas_relativas, rutas_nuevas_relativas, 1)
                    nuevas_expiraciones[nueva_ruta_key] = info
                    exp_modificado = True
                else:
                    nuevas_expiraciones[ruta_key] = info
            
            if exp_modificado:
                guardar_expiraciones(nuevas_expiraciones)
                
            flash(f"Carpeta renombrada a '{nombre_seguro}' exitosamente.", "exito")
        else:
            flash("Error: La carpeta no existe o el nuevo nombre ya está en uso.", "error")

    return redirect(url_for('editor_visual', carpeta=carpeta_actual))

@app.route('/admin/editar-tiempo', methods=['POST'])
@login_requerido
def editar_tiempo():
    ruta_archivo = request.form.get('ruta_archivo')
    carpeta_actual = request.form.get('carpeta_actual', '')
    horas = int(request.form.get('horas', 0))
    minutos = int(request.form.get('minutos', 0))

    if ruta_archivo:
        # Convertimos todo a segundos
        tiempo_segundos = (horas * 3600) + (minutos * 60)
        
        exp = cargar_expiraciones()
        
        if tiempo_segundos > 0:
            timestamp_exp = int(time.time()) + tiempo_segundos
            exp[ruta_archivo] = {
                'expira_en': timestamp_exp,
                'total_segundos': tiempo_segundos
            }
            flash(f"Tiempo actualizado a {horas}h {minutos}m.", "exito")
        else:
            # Si le ponen 0, significa que no expira nunca, así que lo borramos del registro
            if ruta_archivo in exp:
                del exp[ruta_archivo]
            flash("Temporizador eliminado. El archivo ya no expirará.", "exito")
            
        guardar_expiraciones(exp)

    return redirect(url_for('editor_visual', carpeta=carpeta_actual))

@app.route('/admin/subir-video', methods=['POST'])
@login_requerido
def subir_video():
    if 'video_file' not in request.files: 
        return redirect('/editor-visual')
        
    archivos = request.files.getlist('video_file')
    carpeta_actual = request.form.get('carpeta_actual', '').strip('/')
    
    # Leemos las horas y minutos desde el formulario de subida
    horas = int(request.form.get('horas', 0))
    minutos = int(request.form.get('minutos', 0))

    if not archivos or (len(archivos) == 1 and archivos[0].filename == ''):
        return redirect(f'/editor-visual?carpeta={carpeta_actual}')

    # Calculamos el tiempo de expiración
    tiempo_segundos = (horas * 3600) + (minutos * 60)
    timestamp_exp = int(time.time()) + tiempo_segundos if tiempo_segundos > 0 else 0

    expiraciones = cargar_expiraciones()
    agregados = 0

    ruta_destino = os.path.join(CARPETA_VIDEOS_RAIZ, carpeta_actual)
    if not os.path.exists(ruta_destino): 
        os.makedirs(ruta_destino)

    archivos_existentes = [f for f in os.listdir(ruta_destino) if f.lower().endswith(EXT_MEDIA)]
    contador = len(archivos_existentes) + 1

    for archivo in archivos:
        if archivo and archivo.filename.lower().endswith(EXT_MEDIA):
            extension = archivo.filename.rsplit('.', 1)[1].lower()
            nombre_limpio = f"video_{contador}.{extension}"
            
            while os.path.exists(os.path.join(ruta_destino, nombre_limpio)):
                contador += 1
                nombre_limpio = f"video_{contador}.{extension}"
            
            archivo.save(os.path.join(ruta_destino, nombre_limpio))

            # Si el tiempo es mayor a 0, lo registramos para que expire
            if timestamp_exp > 0:
                ruta_relativa = os.path.join(carpeta_actual, nombre_limpio).replace('\\', '/')
                expiraciones[ruta_relativa] = {
                    'expira_en': timestamp_exp,
                    'total_segundos': tiempo_segundos
                }
            contador += 1
            agregados += 1

    if agregados > 0: 
        guardar_expiraciones(expiraciones)
        
    return redirect(f'/editor-visual?carpeta={carpeta_actual}')

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
                except Exception as e: pass
                exp = cargar_expiraciones()
                if item_ruta in exp:
                    del exp[item_ruta]
                    guardar_expiraciones(exp)
    return redirect(url_for('editor_visual', carpeta=carpeta_actual))
@app.route('/admin-usuarios')
def panel_usuarios():
    usuarios = cargar_usuarios()
    lista_usuarios = []
    
    # Variables para nuestros nuevos contadores
    verificados_count = 0
    no_verificados_count = 0

    for correo, datos in usuarios.items():
        is_verified = datos.get("verificado", False)
        lista_usuarios.append({
            "correo": correo,
            "verificado": is_verified
        })
        
        # Contamos cuántos hay de cada uno
        if is_verified:
            verificados_count += 1
        else:
            no_verificados_count += 1

    return render_template('usuarios.html', 
                           usuarios=lista_usuarios, 
                           total=len(usuarios),
                           verificados=verificados_count,
                           no_verificados=no_verificados_count)

@app.route('/admin/agregar-usuario', methods=['POST'])
def admin_agregar_usuario():
    correo = request.form.get('correo').lower().strip()
    password = request.form.get('password')
    usuarios = cargar_usuarios()

    if correo in usuarios:
        flash(f"El correo {correo} ya está registrado.", "error")
    else:
        # Si el admin lo agrega, entra directo sin necesidad de verificar correo
        usuarios[correo] = {
            "password": generate_password_hash(password),
            "verificado": True, 
            "token": None
        }
        guardar_usuarios(usuarios)
        flash(f"Usuario {correo} agregado con éxito y verificado.", "exito")
        
    return redirect(url_for('panel_usuarios'))

@app.route('/admin/eliminar-usuario', methods=['POST'])
def admin_eliminar_usuario():
    correo = request.form.get('correo')
    usuarios = cargar_usuarios()
    
    if correo in usuarios:
        del usuarios[correo]
        guardar_usuarios(usuarios)
        flash(f"Usuario {correo} eliminado correctamente.", "exito")
        
    return redirect(url_for('panel_usuarios'))
@app.route('/media/<path:filename>')
def serve_media(filename):
    return send_from_directory(CARPETA_VIDEOS_RAIZ, filename)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)