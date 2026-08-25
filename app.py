from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
from functools import wraps
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
import os

app = Flask(__name__)
app.secret_key = "super_clave_secreta_alpha_2026"

# --- CONEXIÓN A AIVEN (POSTGRESQL) ---
DB_URI = os.environ.get("DATABASE_URL")

def get_db_connection():
    if not DB_URI:
        raise ValueError("Falta configurar la variable DATABASE_URL en Render con la conexión a Aiven")
    return psycopg2.connect(DB_URI)

# --- INICIALIZAR TABLAS EN AIVEN ---
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # Tabla de usuarios web
    cur.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            username VARCHAR(50) PRIMARY KEY,
            password VARCHAR(100) NOT NULL,
            id_alpha VARCHAR(50) DEFAULT 'TODOS'
        )
    ''')
    cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS id_alpha VARCHAR(50) DEFAULT 'TODOS'")
    
    cur.execute('''
        INSERT INTO usuarios (username, password, id_alpha) 
        VALUES ('ADMIN', '80406651DETAIMALPHA', 'TODOS') 
        ON CONFLICT (username) DO NOTHING
    ''')
    
    # Tabla de registros balísticos
    cur.execute('''
        CREATE TABLE IF NOT EXISTS registros (
            id SERIAL PRIMARY KEY,
            id_alpha VARCHAR(50),
            fecha_hora TIMESTAMP,
            numero_cedula VARCHAR(50),
            nombre VARCHAR(150),
            nombre_ejercicio VARCHAR(150),
            tipo_arma VARCHAR(50),
            tiros_acertados INT,
            tiros_fallidos INT,
            usuario_api VARCHAR(50) DEFAULT 'ADMIN'
        )
    ''')
    cur.execute("ALTER TABLE registros ADD COLUMN IF NOT EXISTS usuario_api VARCHAR(50) DEFAULT 'ADMIN'")

    # TABLA: PRE-REGISTRO DE TIRADORES
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tiradores_web (
            cedula VARCHAR(50) PRIMARY KEY,
            nombre VARCHAR(150) NOT NULL,
            sexo VARCHAR(20) DEFAULT 'MASCULINO',
            fecha_nacimiento VARCHAR(20) DEFAULT 'AAAA/MM/DD',
            foto_b64 TEXT,
            id_alpha_asignado VARCHAR(50) NOT NULL,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute("ALTER TABLE tiradores_web ADD COLUMN IF NOT EXISTS sexo VARCHAR(20) DEFAULT 'MASCULINO'")
    cur.execute("ALTER TABLE tiradores_web ADD COLUMN IF NOT EXISTS fecha_nacimiento VARCHAR(20) DEFAULT 'AAAA/MM/DD'")
    cur.execute("ALTER TABLE tiradores_web ADD COLUMN IF NOT EXISTS foto_b64 TEXT")
    
    # NUEVAS COLUMNAS (Admin)
    cur.execute("ALTER TABLE tiradores_web ADD COLUMN IF NOT EXISTS correo VARCHAR(100) DEFAULT ''")
    cur.execute("ALTER TABLE tiradores_web ADD COLUMN IF NOT EXISTS numero_celular VARCHAR(30) DEFAULT ''")
    cur.execute("ALTER TABLE tiradores_web ADD COLUMN IF NOT EXISTS afinidad_seguridad VARCHAR(150) DEFAULT ''")
    
    # COLUMNA PARA CONSERVAR EL HISTORIAL Y NO BORRARLO
    cur.execute("ALTER TABLE tiradores_web ADD COLUMN IF NOT EXISTS sincronizado BOOLEAN DEFAULT FALSE")

    conn.commit()
    cur.close()
    conn.close()

init_db()

# --- VALIDACIÓN DE USUARIOS EN BASE DE DATOS ---
def check_auth(username, password):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT password FROM usuarios WHERE username = %s", (username,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    
    if user and user['password'] == password:
        return True
    return False

def requires_api_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return jsonify({"error": "NO AUTORIZADO"}), 401
        return f(*args, **kwargs)
    return decorated

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# --- 1. ENDPOINT API (Recibe los datos de Alpha) ---
@app.route('/api/recepcion', methods=['POST'])
@requires_api_auth
def recepcion_datos():
    data = request.json
    if data:
        fecha_hora = data.get('fecha_hora', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        usuario_actual = request.authorization.username
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO registros 
            (id_alpha, fecha_hora, numero_cedula, nombre, nombre_ejercicio, tipo_arma, tiros_acertados, tiros_fallidos, usuario_api)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            data.get('id_alpha', 'DESCONOCIDO'),
            fecha_hora,
            data.get('numero_cedula', 'N/A'),
            data.get('nombre', 'N/A'),
            data.get('nombre_ejercicio', 'N/A'),
            data.get('tipo_arma', 'N/A'),
            data.get('tiros_acertados', 0),
            data.get('tiros_fallidos', 0),
            usuario_actual
        ))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "ok", "mensaje": "DATOS GUARDADOS EN POSTGRESQL EXITOSAMENTE"}), 200
    return jsonify({"error": "DATOS INVÁLIDOS"}), 400

# --- 2. ENDPOINT API (Alpha descarga pre-registros pendientes) ---
@app.route('/api/sincronizar_tiradores', methods=['GET'])
@requires_api_auth
def sincronizar_tiradores():
    id_maquina = request.args.get('id_alpha', 'TODOS')
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # SOLO DESCARGAR LOS QUE NO HAN SIDO SINCRONIZADOS AÚN
    cur.execute('''
        SELECT cedula, nombre, sexo, fecha_nacimiento, foto_b64 
        FROM tiradores_web 
        WHERE (id_alpha_asignado = %s OR id_alpha_asignado = 'TODOS') 
        AND sincronizado = FALSE 
        ORDER BY fecha_creacion ASC
    ''', (id_maquina,))
    
    tiradores = cur.fetchall()
    cur.close()
    conn.close()
    
    return jsonify({"status": "ok", "tiradores": tiradores}), 200

# --- 3. ENDPOINT API (Alpha confirma la sincronización. YA NO SE BORRAN) ---
@app.route('/api/confirmar_tirador', methods=['POST'])
@requires_api_auth
def confirmar_tirador():
    data = request.json
    if data and data.get("cedula"):
        conn = get_db_connection()
        cur = conn.cursor()
        
        # EN LUGAR DE BORRAR, ACTUALIZAMOS EL ESTADO A SINCRONIZADO
        cur.execute("UPDATE tiradores_web SET sincronizado = TRUE WHERE cedula = %s", (data.get("cedula"),))
        
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "ok"}), 200
    return jsonify({"error": "Falta cedula"}), 400

# --- PÁGINA DE LOGIN HTML ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if check_auth(username, password):
            session['user'] = username
            return redirect(url_for('index'))
        else:
            error = "CREDENCIALES INCORRECTAS"
            
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login | Alpha Security</title>
        <style>
            body { background: linear-gradient(rgba(0, 0, 0, 0.85), rgba(0, 0, 0, 0.85)), url('https://i.ibb.co/LDmTGmGn/datos.png') no-repeat center center fixed; background-size: cover; font-family: 'Segoe UI', Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; color: #ffffff; }
            .login-box { background: rgba(255, 255, 255, 0.95); padding: 50px 40px; border-top: 6px solid #cc0000; border-radius: 12px; width: 350px; text-align: center; box-shadow: 0 15px 35px rgba(0,0,0,0.5); }
            .logo { width: 220px; margin-bottom: 20px; filter: drop-shadow(0px 2px 4px rgba(0,0,0,0.3)); }
            p { color: #000000; font-size: 14px; font-weight: bold; margin-bottom: 25px; letter-spacing: 1px; }
            input { width: 90%; padding: 14px; margin: 10px 0; border: 2px solid #dddddd; border-radius: 6px; font-weight: bold; text-align: center; font-size: 14px; color: #000000;}
            input:focus { border: 2px solid #000000; outline: none; background: #fafafa;}
            button { background: #000000; color: #ffffff; border: none; padding: 16px 20px; width: 100%; border-radius: 6px; font-weight: bold; letter-spacing: 2px; cursor: pointer; margin-top: 20px; font-size: 14px; transition: background 0.3s;}
            button:hover { background: #cc0000; }
            .error { color: #ffffff; background: #cc0000; padding: 10px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-top: 20px; letter-spacing: 1px;}
        </style>
    </head>
    <body>
        <div class="login-box">
            <img src="{{ url_for('static', filename='Logo.png') }}" onerror="this.onerror=null; this.src='https://dummyimage.com/220x60/cc0000/ffffff&text=ALPHA+SECURITY';" alt="Alpha Security" class="logo">
            <p>PORTAL CLOUD SYSTEM</p>
            <form method="POST">
                <input type="text" name="username" placeholder="USUARIO" required>
                <input type="password" name="password" placeholder="CONTRASEÑA" required>
                <button type="submit">INICIAR SESIÓN</button>
            </form>
            {% if error %}
            <div class="error"><span style="font-weight:bold;">ERROR:</span> {{ error }}</div>
            {% endif %}
        </div>
    </body>
    </html>
    """
    return render_template_string(html, error=error)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

# --- CREAR O EDITAR USUARIO WEB (Solo ADMIN) ---
@app.route('/crear_usuario', methods=['POST'])
@login_required
def crear_usuario():
    if session.get('user') == 'ADMIN':
        new_u = request.form.get('new_user')
        new_p = request.form.get('new_password')
        new_id = request.form.get('new_id_alpha', '').strip()
        if not new_id: new_id = 'TODOS'
            
        if new_u and new_p:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO usuarios (username, password, id_alpha) 
                VALUES (%s, %s, %s) 
                ON CONFLICT (username) DO UPDATE SET password = EXCLUDED.password, id_alpha = EXCLUDED.id_alpha
            ''', (new_u.upper(), new_p, new_id.upper()))
            conn.commit()
            cur.close()
            conn.close()
    return redirect(url_for('index'))

@app.route('/borrar_usuario', methods=['POST'])
@login_required
def borrar_usuario():
    if session.get('user') == 'ADMIN':
        del_u = request.form.get('username')
        if del_u and del_u != 'ADMIN':
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM usuarios WHERE username = %s", (del_u,))
            conn.commit()
            cur.close()
            conn.close()
    return redirect(url_for('index'))

# --- PRE-REGISTRO DE TIRADORES ---
@app.route('/registrar_tirador', methods=['POST'])
@login_required
def registrar_tirador():
    if session.get('user') == 'ADMIN':
        cedula = request.form.get('cedula').strip()
        nombre = request.form.get('nombre').strip().upper()
        sexo = request.form.get('sexo', 'MASCULINO').strip().upper()
        fecha_nac = request.form.get('fecha_nacimiento', 'AAAA-MM-DD').strip()
        id_asignado = request.form.get('id_asignado', 'TODOS').strip().upper()
        foto_b64 = request.form.get('foto_b64', '')
        
        correo = request.form.get('correo', '').strip()
        numero_celular = request.form.get('numero_celular', '').strip()
        # Ahora es campo de texto abierto
        afinidad_seguridad = request.form.get('afinidad_seguridad', '').strip().upper()
        
        if cedula and nombre:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO tiradores_web (cedula, nombre, sexo, fecha_nacimiento, id_alpha_asignado, foto_b64, correo, numero_celular, afinidad_seguridad, sincronizado) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE) 
                ON CONFLICT (cedula) DO UPDATE SET 
                    nombre = EXCLUDED.nombre,
                    sexo = EXCLUDED.sexo,
                    fecha_nacimiento = EXCLUDED.fecha_nacimiento,
                    id_alpha_asignado = EXCLUDED.id_alpha_asignado,
                    foto_b64 = EXCLUDED.foto_b64,
                    correo = EXCLUDED.correo,
                    numero_celular = EXCLUDED.numero_celular,
                    afinidad_seguridad = EXCLUDED.afinidad_seguridad,
                    sincronizado = FALSE
            ''', (cedula, nombre, sexo, fecha_nac, id_asignado, foto_b64, correo, numero_celular, afinidad_seguridad))
            conn.commit()
            cur.close()
            conn.close()
    return redirect(url_for('index'))

@app.route('/borrar_tirador', methods=['POST'])
@login_required
def borrar_tirador():
    if session.get('user') == 'ADMIN':
        cedula = request.form.get('cedula')
        if cedula:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM tiradores_web WHERE cedula = %s", (cedula,))
            conn.commit()
            cur.close()
            conn.close()
    return redirect(url_for('index'))

# --- DASHBOARD ---
@app.route('/', methods=['GET'])
@login_required
def index():
    usuario_logeado = session.get('user')

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT id_alpha FROM usuarios WHERE username = %s", (usuario_logeado,))
    user_info = cur.fetchone()
    user_id_alpha = user_info['id_alpha'] if user_info else 'TODOS'

    if usuario_logeado == 'ADMIN' or user_id_alpha == 'TODOS':
        cur.execute("SELECT * FROM registros ORDER BY fecha_hora DESC")
    else:
        cur.execute("SELECT * FROM registros WHERE id_alpha = %s ORDER BY fecha_hora DESC", (user_id_alpha,))
        
    registros_globales = cur.fetchall()

    registros_por_dia = {}
    for r in registros_globales:
        dia = r['fecha_hora'].strftime('%Y-%m-%d') if r['fecha_hora'] else 'FECHA DESCONOCIDA'
        if dia not in registros_por_dia:
            registros_por_dia[dia] = []
        registros_por_dia[dia].append(r)

    lista_usuarios = []
    lista_tiradores = []
    if usuario_logeado == 'ADMIN':
        cur.execute("SELECT username, id_alpha FROM usuarios ORDER BY username ASC")
        lista_usuarios = cur.fetchall()
        
        # SELECCIÓN CON TODOS LOS DATOS Y ESTADO DE SINCRONIZACIÓN
        cur.execute('''
            SELECT cedula, nombre, sexo, fecha_nacimiento, id_alpha_asignado, 
                   correo, numero_celular, afinidad_seguridad, fecha_creacion, sincronizado,
                   (foto_b64 IS NOT NULL AND foto_b64 != '') as tiene_foto 
            FROM tiradores_web 
            ORDER BY fecha_creacion DESC
        ''')
        lista_tiradores = cur.fetchall()

    cur.close()
    conn.close()

    total_registros = len(registros_globales)
    aciertos = sum(r.get('tiros_acertados', 0) for r in registros_globales)
    fallos = sum(r.get('tiros_fallidos', 0) for r in registros_globales)
    total_disparos = aciertos + fallos
    precision = round((aciertos / total_disparos * 100), 1) if total_disparos > 0 else 0

    tiradores_nombres = []
    tiradores_aciertos = []
    tiradores_fallos = []
    
    for r in registros_globales[:5]:
        tiradores_nombres.append(r.get('nombre', 'Desconocido')[:15]) 
        tiradores_aciertos.append(r.get('tiros_acertados', 0))
        tiradores_fallos.append(r.get('tiros_fallidos', 0))

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard | Alpha Security</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body { background-color: #f0f2f5; font-family: 'Segoe UI', Arial, sans-serif; margin: 0; color: #000000; }
            .navbar { background: #ffffff; padding: 15px 40px; color: #000000; display: flex; justify-content: space-between; align-items: center; border-bottom: 5px solid #cc0000; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
            .navbar img { height: 45px; filter: drop-shadow(0px 1px 2px rgba(0,0,0,0.2)); } 
            .user-info { display: flex; align-items: center; gap: 20px; }
            .user-info span { font-size: 13px; color: #555555; letter-spacing: 1px; }
            .user-info b { color: #000000; font-size: 15px; text-transform: uppercase; }
            .btn-rojo { background: #cc0000; color: #ffffff; padding: 10px 25px; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 12px; border: none; cursor: pointer; letter-spacing: 1px; transition: background 0.3s;}
            .btn-rojo:hover { background: #000000; }
            .container { padding: 40px; max-width: 1700px; margin: 0 auto; }
            
            .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; }
            .kpi-card { background: #ffffff; padding: 25px; border-radius: 4px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border-left: 5px solid #000000; display: flex; flex-direction: column; justify-content: center; }
            .kpi-card:nth-child(1) { border-left-color: #cc0000; }
            .kpi-card:nth-child(3) { border-left-color: #cc0000; }
            .kpi-title { font-size: 12px; color: #555555; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }
            .kpi-value { font-size: 32px; font-weight: bold; color: #000000; margin: 0; font-family: 'Consolas', monospace; }
            
            .panel { background: #ffffff; padding: 30px; border-radius: 4px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border: 1px solid #eeeeee; margin-bottom: 30px;}
            .panel h3 { margin-top: 0; color: #000000; font-size: 15px; letter-spacing: 1px; border-bottom: 2px solid #eeeeee; padding-bottom: 10px; margin-bottom: 20px; text-transform: uppercase; }
            
            /* NUEVO: Split Panel Layout (Lado a Lado) */
            .split-panel { display: flex; gap: 30px; flex-wrap: wrap; }
            .split-left { flex: 1; min-width: 350px; background: #fafafa; padding: 25px; border-radius: 8px; border: 1px solid #e0e0e0; }
            .split-right { flex: 2.5; background: #ffffff; border-radius: 8px; }
            
            .form-user { display: flex; flex-direction: column; gap: 12px; }
            .form-user input, .form-user select { padding: 10px; border: 1px solid #cccccc; border-radius: 4px; font-weight: bold; font-size: 12px; color: #000000; width: 100%; box-sizing: border-box;}
            .form-user input[type="date"] { font-family: 'Segoe UI', Arial, sans-serif; cursor: pointer; text-transform: uppercase;}
            .form-user input:focus, .form-user select:focus { border: 1px solid #cc0000; outline: none; }
            
            .table-container { overflow-x: auto; background: #ffffff; border-radius: 4px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border-top: 4px solid #000000; }
            table { width: 100%; border-collapse: collapse; min-width: 800px; }
            th, td { padding: 16px; text-align: center; font-size: 12px; }
            th { background-color: #ffffff; color: #000000; text-transform: uppercase; font-weight: bold; letter-spacing: 1px; position: sticky; top: 0; border-bottom: 2px solid #000000; }
            td { border-bottom: 1px solid #eeeeee; color: #000000; font-weight: 500; }
            tr:hover { background-color: #f9f9f9; }
            
            .badge-acierto { background-color: #000000; color: #ffffff; padding: 6px 14px; border-radius: 4px; font-weight: bold; font-size: 13px; }
            .badge-fallo { background-color: #cc0000; color: #ffffff; padding: 6px 14px; border-radius: 4px; font-weight: bold; font-size: 13px; }
            .badge-total { background-color: #ffffff; color: #000000; padding: 5px 13px; border-radius: 4px; font-weight: bold; font-size: 13px; border: 2px solid #000000;}
            
            .badge-sinc { background: #27ae60; color: white; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: bold; letter-spacing: 1px;}
            .badge-pend { background: #f39c12; color: white; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: bold; letter-spacing: 1px;}
            
            .filter-row th { background-color: #f9f9f9; padding: 10px 8px; border-bottom: 2px solid #dddddd; }
            .filter-input { width: 85%; padding: 8px; border: 1px solid #cccccc; border-radius: 4px; background: #ffffff; color: #000000; font-size: 11px; font-weight: bold; text-align: center; text-transform: uppercase; }
            
            .charts-wrapper { display: flex; gap: 30px; height: 250px; }
            .chart-box { flex: 1; position: relative; }
            .admin-table th { background: #f5f5f5; border-bottom: 1px solid #dddddd; font-size: 11px; padding: 10px; }
            .admin-table td { font-size: 11px; padding: 10px; }
            .btn-black-small { background: #000000; color: #ffffff; border: none; border-radius: 4px; padding: 6px 12px; font-weight: bold; font-size: 10px; cursor: pointer; letter-spacing: 1px; }
            .btn-black-small:hover { background: #cc0000; }
        </style>
    </head>
    <body>
        <div class="navbar">
            <img src="{{ url_for('static', filename='Logo.png') }}" onerror="this.onerror=null; this.src='https://dummyimage.com/220x60/cc0000/ffffff&text=ALPHA+SECURITY';" alt="Alpha Security">
            <div class="user-info">
                <span>CONECTADO COMO: <b>{{ current_user }}</b></span>
                <a href="/logout" class="btn-rojo">CERRAR SESIÓN</a>
            </div>
        </div>
        
        <div class="container">
            <div class="kpi-grid">
                <div class="kpi-card">
                    <span class="kpi-title">TOTAL REGISTROS EN NUBE</span>
                    <h2 class="kpi-value">{{ kpis.registros }}</h2>
                </div>
                <div class="kpi-card">
                    <span class="kpi-title">MUNICIÓN TOTAL USADA</span>
                    <h2 class="kpi-value">{{ kpis.disparos }}</h2>
                </div>
                <div class="kpi-card">
                    <span class="kpi-title">EFECTIVIDAD GLOBAL</span>
                    <h2 class="kpi-value">{{ kpis.precision }}%</h2>
                </div>
                <div class="kpi-card">
                    <span class="kpi-title">ESTADO SERVIDOR</span>
                    <h2 class="kpi-value" style="font-size: 24px; margin-top: 8px;">ACTIVO</h2>
                </div>
            </div>

            {% if current_user == 'ADMIN' %}
            
            <!-- PANEL DE USUARIOS (Cuentas) -->
            <div class="panel" style="border-top: 4px solid #cc0000;">
                <h3 style="color: #cc0000;">GESTIÓN DE PERFILES WEB</h3>
                <div style="display: flex; gap: 30px;">
                    <div style="flex: 1;">
                        <p style="color: #555555; font-size: 11px; margin-bottom: 15px;">Cree un nuevo usuario. Asigne el <b>ID EQUIPO</b> para limitar su vista.</p>
                        <form class="form-user" method="POST" action="/crear_usuario">
                            <input type="text" name="new_user" placeholder="NUEVO USUARIO" required>
                            <input type="password" name="new_password" placeholder="CONTRASEÑA" required>
                            <input type="text" name="new_id_alpha" placeholder="ID EQUIPO (Dejar vacío para ver todos)">
                            <button type="submit" class="btn-rojo" style="padding: 14px; margin-top: 5px;">GUARDAR PERFIL</button>
                        </form>
                    </div>
                    <div style="flex: 2; overflow-y: auto; max-height: 200px; border: 1px solid #eeeeee; border-radius: 4px;">
                        <table class="admin-table">
                            <tr>
                                <th>USUARIO</th>
                                <th>ID EQUIPO</th>
                                <th>ACCIÓN</th>
                            </tr>
                            {% for u in lista_usuarios %}
                            <tr>
                                <td style="font-weight:bold; color: #cc0000;">{{ u.username }}</td>
                                <td>{{ u.id_alpha }}</td>
                                <td>
                                    {% if u.username != 'ADMIN' %}
                                    <form method="POST" action="/borrar_usuario" style="margin:0;">
                                        <input type="hidden" name="username" value="{{ u.username }}">
                                        <button type="submit" class="btn-black-small">BORRAR</button>
                                    </form>
                                    {% endif %}
                                </td>
                            </tr>
                            {% endfor %}
                        </table>
                    </div>
                </div>
            </div>

            <!-- NUEVO PANEL DIVIDIDO: PRE-REGISTRO Y DIRECTORIO -->
            <div class="panel" style="border-top: 4px solid #000000;">
                <h3>GESTIÓN GLOBAL DE TIRADORES (PRE-REGISTRO)</h3>
                
                <div class="split-panel">
                    
                    <!-- LADO IZQUIERDO: FORMULARIO -->
                    <div class="split-left">
                        <h4 style="margin-top:0; color:#cc0000; font-size: 14px; border-bottom: 1px solid #ddd; padding-bottom: 8px;">1. NUEVO PRE-REGISTRO</h4>
                        <form class="form-user" method="POST" action="/registrar_tirador">
                            <div style="display: flex; gap: 10px;">
                                <input type="text" name="cedula" placeholder="NÚMERO DE CÉDULA" style="flex: 1;" required>
                                <input type="text" name="nombre" placeholder="NOMBRES COMPLETOS" style="flex: 2;" required>
                            </div>

                            <div style="display: flex; gap: 10px;">
                                <select name="sexo" style="flex: 1;">
                                    <option value="MASCULINO">MASCULINO</option>
                                    <option value="FEMENINO">FEMENINO</option>
                                </select>
                                <input type="date" name="fecha_nacimiento" style="flex: 1;" required>
                            </div>
                            
                            <hr style="border: 0; height: 1px; background: #eee; margin: 10px 0;">
                            
                            <!-- DATOS ADICIONALES (CAMPO ABIERTO) -->
                            <div style="display: flex; gap: 10px;">
                                <input type="email" name="correo" placeholder="CORREO ELECTRÓNICO" style="flex: 1;">
                                <input type="tel" name="numero_celular" placeholder="NÚMERO CELULAR" style="flex: 1;">
                            </div>
                            
                            <!-- AHORA ES UN INPUT TEXT ABIERTO -->
                            <input type="text" name="afinidad_seguridad" placeholder="AFINIDAD CON LA SEGURIDAD (Ej: Policía, Civil, Escolta...)" style="width: 100%;">

                            <hr style="border: 0; height: 1px; background: #eee; margin: 10px 0;">

                            <input type="text" name="id_asignado" placeholder="ID EQUIPO DESTINO (Ej: B5CD2CBD34 o TODOS)" required>
                            
                            <!-- SECCIÓN CÁMARA WEB HTML5 -->
                            <div style="display:flex; flex-direction:column; align-items:center; gap:8px; margin-top: 10px; padding:10px; border:1px solid #dddddd; border-radius:4px; background:#ffffff;">
                                <span style="font-size:11px; font-weight:bold; color:#555;">FOTOGRAFÍA FACIAL (Opcional)</span>
                                <video id="webcam" width="100%" height="auto" autoplay playsinline style="border: 2px solid #cccccc; border-radius: 4px; background:#000000; max-height:160px;"></video>
                                <canvas id="canvas" width="640" height="480" style="display:none;"></canvas>
                                <button type="button" id="btn_snap" class="btn-black-small" style="width:100%; padding:10px; font-size:11px;">📸 CAPTURAR FOTO</button>
                                <input type="hidden" name="foto_b64" id="foto_b64">
                                <span id="foto_status" style="font-size:10px; color:#cc0000; font-weight:bold;">SIN FOTO (Tomar localmente si se omite)</span>
                            </div>

                            <button type="submit" class="btn-rojo" style="background:#000000; padding: 14px; margin-top:10px; font-size:13px;">GUARDAR EN DIRECTORIO</button>
                        </form>
                    </div>

                    <!-- LADO DERECHO: DIRECTORIO COMPLETO -->
                    <div class="split-right">
                        <h4 style="margin-top:0; color:#000000; font-size: 14px; border-bottom: 1px solid #ddd; padding-bottom: 8px;">2. DIRECTORIO COMPLETO (HISTORIAL)</h4>
                        
                        <div style="overflow-y: auto; overflow-x: auto; max-height: 550px; border: 1px solid #eeeeee; border-radius: 4px;">
                            <table class="admin-table" style="min-width: 850px; text-align: center;">
                                <tr>
                                    <th>CREADO EL</th>
                                    <th>CÉDULA</th>
                                    <th>TIRADOR</th>
                                    <th>CONTACTO</th>
                                    <th>AFINIDAD</th>
                                    <th>FOTO</th>
                                    <th>DESTINO</th>
                                    <th>ESTADO</th>
                                    <th>ACCIÓN</th>
                                </tr>
                                {% for t in lista_tiradores %}
                                <tr>
                                    <td style="font-size: 10px; color:#555555;">{{ t.fecha_creacion.strftime('%Y-%m-%d %H:%M') if t.fecha_creacion else '' }}</td>
                                    <td style="font-weight:bold;">{{ t.cedula }}</td>
                                    <td style="text-align: left;">{{ t.nombre }}<br><span style="color:#777777; font-size:9px;">{{ t.sexo }} | {{ t.fecha_nacimiento }}</span></td>
                                    <td style="font-size: 10px;">{{ t.correo }}<br><span style="color:#777777">{{ t.numero_celular }}</span></td>
                                    <td style="font-weight:bold; font-size: 10px;">{{ t.afinidad_seguridad }}</td>
                                    <td style="font-weight:bold; color:{% if t.tiene_foto %}#27ae60{% else %}#cc0000{% endif %};">
                                        {% if t.tiene_foto %}SÍ{% else %}NO{% endif %}
                                    </td>
                                    <td style="color:#cc0000; font-weight:bold;">{{ t.id_alpha_asignado }}</td>
                                    <td>
                                        {% if t.sincronizado %}
                                            <span class="badge-sinc">SINCRONIZADO</span>
                                        {% else %}
                                            <span class="badge-pend">PENDIENTE</span>
                                        {% endif %}
                                    </td>
                                    <td>
                                        <form method="POST" action="/borrar_tirador" style="margin:0;">
                                            <input type="hidden" name="cedula" value="{{ t.cedula }}">
                                            <button type="submit" class="btn-black-small">BORRAR</button>
                                        </form>
                                    </td>
                                </tr>
                                {% endfor %}
                            </table>
                        </div>
                    </div>

                </div>
            </div>
            
            <div class="panel">
                <h3>ANÁLISIS DE RENDIMIENTO (ÚLTIMAS 5 SESIONES)</h3>
                <div class="charts-wrapper">
                    <div class="chart-box">
                        <canvas id="hitMissChart"></canvas>
                    </div>
                    <div class="chart-box" style="flex: 2;">
                        <canvas id="barChart"></canvas>
                    </div>
                </div>
            </div>
            {% endif %}

            <!-- 3. Tabla de Datos -->
            <div class="table-container">
                <table id="dataTable">
                    <thead>
                        <tr>
                            <th>ID Equipo (Usuario)</th>
                            <th>Hora Exacta</th>
                            <th>Identificación</th>
                            <th>Tirador</th>
                            <th>Misión / Escenario</th>
                            <th>Armamento</th>
                            <th>Impactos</th>
                            <th>Fallos</th>
                            <th>Total</th>
                        </tr>
                        <tr class="filter-row">
                            <th><input type="text" class="filter-input" data-col="0" placeholder="BUSCAR ID..." onkeyup="filterTable()"></th>
                            <th><input type="text" class="filter-input" data-col="1" placeholder="BUSCAR HORA..." onkeyup="filterTable()"></th>
                            <th><input type="text" class="filter-input" data-col="2" placeholder="BUSCAR CÉDULA..." onkeyup="filterTable()"></th>
                            <th><input type="text" class="filter-input" data-col="3" placeholder="BUSCAR TIRADOR..." onkeyup="filterTable()"></th>
                            <th><input type="text" class="filter-input" data-col="4" placeholder="BUSCAR MISIÓN..." onkeyup="filterTable()"></th>
                            <th><input type="text" class="filter-input" data-col="5" placeholder="BUSCAR ARMA..." onkeyup="filterTable()"></th>
                            <th></th>
                            <th></th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- AGRUPACIÓN POR DÍAS -->
                        {% for dia, regs in registros_por_dia.items() %}
                        <tr>
                            <td colspan="9" class="day-header" style="background-color: #f5f5f5; font-weight: bold; color: #cc0000; text-align: left; padding-left: 20px; font-size: 14px; border-top: 2px solid #dddddd;">REPORTE DEL DÍA: {{ dia }}</td>
                        </tr>
                            {% for r in regs %}
                            <tr class="data-row">
                                <td style="line-height:1.2;"><b>{{ r.id_alpha }}</b><br><span style="font-size:10px; color:#777777;">{{ r.usuario_api }}</span></td>
                                <td style="color: #555555; font-family: 'Consolas', monospace; font-size: 11px; font-weight:bold;">{{ r.fecha_hora.strftime('%H:%M:%S') if r.fecha_hora else '' }}</td>
                                <td style="color: #555555; font-weight: bold;">{{ r.numero_cedula }}</td>
                                <td style="font-weight: bold; color: #cc0000;">{{ r.nombre }}</td>
                                <td style="font-weight: bold;">{{ r.nombre_ejercicio }}</td>
                                <td style="font-weight: bold;">{{ r.tipo_arma }}</td>
                                <td><span class="badge-acierto">{{ r.tiros_acertados }}</span></td>
                                <td><span class="badge-fallo">{{ r.tiros_fallidos }}</span></td>
                                <td><span class="badge-total">{{ r.tiros_acertados + r.tiros_fallidos }}</span></td>
                            </tr>
                            {% endfor %}
                        {% else %}
                        <tr class="no-data"><td colspan="9" style="color: #555555; padding: 40px; font-style: italic; font-weight: bold;">NO SE HAN RECIBIDO TRANSMISIONES BALÍSTICAS.</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- SCRIPTS JS -->
        <script>
            // Lógica de Filtros de Tabla
            function filterTable() {
                const table = document.getElementById('dataTable');
                const tr = table.querySelectorAll('tbody tr.data-row');
                const inputs = document.querySelectorAll('.filter-input');

                tr.forEach(row => {
                    let showRow = true;
                    inputs.forEach((input) => {
                        const colIdx = input.getAttribute('data-col');
                        const filterValue = input.value.toLowerCase();
                        const cell = row.cells[colIdx];
                        if (cell) {
                            const cellText = cell.textContent || cell.innerText;
                            if (cellText.toLowerCase().indexOf(filterValue) === -1) {
                                showRow = false;
                            }
                        }
                    });
                    row.style.display = showRow ? '' : 'none';
                });
            }

            // Lógica de Cámara Web HTML5
            {% if current_user == 'ADMIN' %}
            const video = document.getElementById('webcam');
            const canvas = document.getElementById('canvas');
            const btnSnap = document.getElementById('btn_snap');
            const fotoInput = document.getElementById('foto_b64');
            const fotoStatus = document.getElementById('foto_status');

            if(navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
                navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } }).then(function(stream) {
                    video.srcObject = stream;
                    video.play();
                }).catch(function(err) {
                    console.log("No se pudo acceder a la cámara: " + err);
                    fotoStatus.textContent = "CÁMARA NO DISPONIBLE";
                });
            }

            btnSnap.addEventListener('click', function() {
                if(video.srcObject) {
                    const context = canvas.getContext('2d');
                    // Espejamos la imagen por UX
                    context.translate(canvas.width, 0);
                    context.scale(-1, 1);
                    context.drawImage(video, 0, 0, 640, 480);
                    
                    // Extraer Base64
                    const dataUrl = canvas.toDataURL('image/jpeg', 0.85); // JPEG comprimido para transferencias ágiles
                    fotoInput.value = dataUrl;
                    
                    fotoStatus.textContent = "✓ FOTO CAPTURADA SATISFACTORIAMENTE";
                    fotoStatus.style.color = "#27ae60";
                    
                    // Pequeño efecto visual
                    btnSnap.style.backgroundColor = "#27ae60";
                    btnSnap.textContent = "FOTO TOMADA";
                    setTimeout(() => {
                        btnSnap.style.backgroundColor = "#000000";
                        btnSnap.textContent = "📸 REPETIR FOTO";
                    }, 1500);
                }
            });
            {% endif %}
        </script>

        {% if current_user == 'ADMIN' %}
        <script>
            const aciertosTotales = {{ kpis.aciertos }};
            const fallosTotales = {{ kpis.fallos }};
            const labelsTiradores = {{ charts.nombres | safe }};
            const dataAciertos = {{ charts.aciertos | safe }};
            const dataFallos = {{ charts.fallos | safe }};

            const ctxDona = document.getElementById('hitMissChart').getContext('2d');
            new Chart(ctxDona, {
                type: 'doughnut',
                data: {
                    labels: ['Aciertos', 'Fallos'],
                    datasets: [{
                        data: [aciertosTotales, fallosTotales],
                        backgroundColor: ['#000000', '#cc0000'],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'bottom', labels: { boxWidth: 12, font: {family: 'Segoe UI', size: 11, weight: 'bold'}, color: '#000000' } }
                    },
                    cutout: '70%'
                }
            });

            const ctxBarras = document.getElementById('barChart').getContext('2d');
            new Chart(ctxBarras, {
                type: 'bar',
                data: {
                    labels: labelsTiradores.length > 0 ? labelsTiradores : ['Sin Datos'],
                    datasets: [
                        { label: 'Aciertos', data: dataAciertos.length > 0 ? dataAciertos : [0], backgroundColor: '#000000', borderRadius: 4 },
                        { label: 'Fallos', data: dataFallos.length > 0 ? dataFallos : [0], backgroundColor: '#cc0000', borderRadius: 4 }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: { beginAtZero: true, grid: { color: '#eeeeee' }, ticks: { color: '#000000', font: {weight: 'bold'} } },
                        x: { grid: { display: false }, ticks: { color: '#000000', font: {weight: 'bold'} } }
                    },
                    plugins: {
                        legend: { position: 'bottom', labels: { boxWidth: 12, font: {family: 'Segoe UI', size: 11, weight: 'bold'}, color: '#000000' } }
                    }
                }
            });
        </script>
        {% endif %}
    </body>
    </html>
    """
    
    kpis = {
        "registros": total_registros,
        "disparos": total_disparos,
        "precision": precision,
        "aciertos": aciertos,
        "fallos": fallos
    }
    charts = {
        "nombres": tiradores_nombres,
        "aciertos": tiradores_aciertos,
        "fallos": tiradores_fallos
    }

    return render_template_string(html, registros_por_dia=registros_por_dia, current_user=session.get('user'), kpis=kpis, charts=charts, lista_usuarios=lista_usuarios, lista_tiradores=lista_tiradores)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)