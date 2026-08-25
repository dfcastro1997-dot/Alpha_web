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
    # Crear tabla de usuarios web con asignación de ID EQUIPO
    cur.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            username VARCHAR(50) PRIMARY KEY,
            password VARCHAR(100) NOT NULL,
            id_alpha VARCHAR(50) DEFAULT 'TODOS'
        )
    ''')
    # Actualización automática si la tabla ya existía
    cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS id_alpha VARCHAR(50) DEFAULT 'TODOS'")
    
    # Crear administrador por defecto si no existe
    cur.execute('''
        INSERT INTO usuarios (username, password, id_alpha) 
        VALUES ('ADMIN', '80406651DETAIMALPHA', 'TODOS') 
        ON CONFLICT (username) DO NOTHING
    ''')
    
    # Crear tabla de registros balísticos
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
    
    conn.commit()
    cur.close()
    conn.close()

# Ejecutar creación de tablas al arrancar
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

# --- MIDDLEWARE PARA LA API (Software de Escritorio) ---
def requires_api_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return jsonify({"error": "NO AUTORIZADO"}), 401
        return f(*args, **kwargs)
    return decorated

# --- MIDDLEWARE PARA LA WEB (Usuarios Humanos) ---
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# --- 1. ENDPOINT API (Recibe los datos silenciosamente y los guarda en Aiven) ---
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

# --- 2. PÁGINA DE LOGIN HTML ---
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
            body { 
                background: linear-gradient(rgba(0, 0, 0, 0.85), rgba(0, 0, 0, 0.85)), url('https://i.ibb.co/LDmTGmGn/datos.png') no-repeat center center fixed; 
                background-size: cover;
                font-family: 'Segoe UI', Arial, sans-serif; 
                display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; color: #ffffff; 
            }
            .login-box { 
                background: rgba(255, 255, 255, 0.95); 
                padding: 50px 40px; 
                border-top: 6px solid #cc0000; 
                border-radius: 12px; 
                width: 350px; 
                text-align: center; 
                box-shadow: 0 15px 35px rgba(0,0,0,0.5); 
            }
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
            <img src="https://i.ibb.co/r2mMkRTq/Logo.png" alt="Alpha Security" class="logo">
            <p>PORTAL CLOUD SYSTEM</p>
            <form method="POST">
                <input type="text" name="username" placeholder="USUARIO" required>
                <input type="password" name="password" placeholder="CONTRASEÑA" required>
                <button type="submit">INICIAR SESIÓN</button>
            </form>
            {% if error %}
            <div class="error">
                <span style="font-weight:bold;">ERROR:</span> {{ error }}
            </div>
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

# --- 3. CREAR O EDITAR USUARIO WEB (Solo ADMIN) ---
@app.route('/crear_usuario', methods=['POST'])
@login_required
def crear_usuario():
    if session.get('user') == 'ADMIN':
        new_u = request.form.get('new_user')
        new_p = request.form.get('new_password')
        new_id = request.form.get('new_id_alpha', '').strip()
        if not new_id:
            new_id = 'TODOS'
            
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

# --- ELIMINAR USUARIO WEB (Solo ADMIN) ---
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

# --- 4. DASHBOARD (Tabla Profesional + Gráficas + Filtros) ---
@app.route('/', methods=['GET'])
@login_required
def index():
    usuario_logeado = session.get('user')

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Obtener qué ID EQUIPO puede ver este usuario
    cur.execute("SELECT id_alpha FROM usuarios WHERE username = %s", (usuario_logeado,))
    user_info = cur.fetchone()
    user_id_alpha = user_info['id_alpha'] if user_info else 'TODOS'

    # Filtrar registros
    if usuario_logeado == 'ADMIN' or user_id_alpha == 'TODOS':
        cur.execute("SELECT * FROM registros ORDER BY id DESC")
    else:
        cur.execute("SELECT * FROM registros WHERE id_alpha = %s ORDER BY id DESC", (user_id_alpha,))
        
    registros_globales = cur.fetchall()

    # Si es ADMIN, obtener la lista de perfiles para administrarlos
    lista_usuarios = []
    if usuario_logeado == 'ADMIN':
        cur.execute("SELECT username, id_alpha FROM usuarios ORDER BY username ASC")
        lista_usuarios = cur.fetchall()

    cur.close()
    conn.close()

    # --- CÁLCULOS PARA KPIS ---
    total_registros = len(registros_globales)
    aciertos = sum(r.get('tiros_acertados', 0) for r in registros_globales)
    fallos = sum(r.get('tiros_fallidos', 0) for r in registros_globales)
    total_disparos = aciertos + fallos
    precision = round((aciertos / total_disparos * 100), 1) if total_disparos > 0 else 0

    # --- CÁLCULOS PARA GRÁFicas ---
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
            
            /* Header / Navbar en Blanco y Rojo Estricto */
            .navbar { background: #ffffff; padding: 15px 40px; color: #000000; display: flex; justify-content: space-between; align-items: center; border-bottom: 5px solid #cc0000; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
            .navbar img { height: 45px; filter: drop-shadow(0px 1px 2px rgba(0,0,0,0.2)); } 
            .user-info { display: flex; align-items: center; gap: 20px; }
            .user-info span { font-size: 13px; color: #555555; letter-spacing: 1px; }
            .user-info b { color: #000000; font-size: 15px; text-transform: uppercase; }
            .btn-rojo { background: #cc0000; color: #ffffff; padding: 10px 25px; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 12px; border: none; cursor: pointer; letter-spacing: 1px; transition: background 0.3s;}
            .btn-rojo:hover { background: #000000; }
            
            .container { padding: 40px; max-width: 1500px; margin: 0 auto; }
            
            /* KPIs */
            .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; }
            .kpi-card { background: #ffffff; padding: 25px; border-radius: 4px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border-left: 5px solid #000000; display: flex; flex-direction: column; justify-content: center; }
            .kpi-card:nth-child(1) { border-left-color: #cc0000; }
            .kpi-card:nth-child(3) { border-left-color: #cc0000; }
            .kpi-title { font-size: 12px; color: #555555; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }
            .kpi-value { font-size: 32px; font-weight: bold; color: #000000; margin: 0; font-family: 'Consolas', monospace; }
            
            /* Layout Admin */
            .panel { background: #ffffff; padding: 30px; border-radius: 4px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border: 1px solid #eeeeee; margin-bottom: 30px;}
            .panel h3 { margin-top: 0; color: #000000; font-size: 15px; letter-spacing: 1px; border-bottom: 2px solid #eeeeee; padding-bottom: 10px; margin-bottom: 20px; text-transform: uppercase; }
            
            /* Formularios Admin */
            .form-user { display: flex; flex-direction: column; gap: 15px; }
            .form-user input { padding: 12px; border: 1px solid #cccccc; border-radius: 4px; font-weight: bold; font-size: 12px; color: #000000; }
            .form-user input:focus { border: 1px solid #cc0000; outline: none; }
            
            /* Tablas Blanco/Negro/Rojo Estricto */
            .table-container { overflow-x: auto; background: #ffffff; border-radius: 4px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border-top: 4px solid #000000; }
            table { width: 100%; border-collapse: collapse; }
            th, td { padding: 16px; text-align: center; font-size: 12px; }
            th { background-color: #ffffff; color: #000000; text-transform: uppercase; font-weight: bold; letter-spacing: 1px; position: sticky; top: 0; border-bottom: 2px solid #000000; }
            td { border-bottom: 1px solid #eeeeee; color: #000000; font-weight: 500; }
            tr:hover { background-color: #f9f9f9; }
            
            /* Badges Estrictos (Sin verdes/azules) */
            .badge-acierto { background-color: #000000; color: #ffffff; padding: 6px 14px; border-radius: 4px; font-weight: bold; font-size: 13px; }
            .badge-fallo { background-color: #cc0000; color: #ffffff; padding: 6px 14px; border-radius: 4px; font-weight: bold; font-size: 13px; }
            .badge-total { background-color: #ffffff; color: #000000; padding: 5px 13px; border-radius: 4px; font-weight: bold; font-size: 13px; border: 2px solid #000000;}
            
            /* Inputs de Filtro en Tabla Blancos/Grises */
            .filter-row th { background-color: #f9f9f9; padding: 10px 8px; border-bottom: 2px solid #dddddd; }
            .filter-input { width: 85%; padding: 8px; border: 1px solid #cccccc; border-radius: 4px; background: #ffffff; color: #000000; font-size: 11px; font-weight: bold; text-align: center; text-transform: uppercase; }
            .filter-input::placeholder { color: #888888; }
            .filter-input:focus { border-color: #cc0000; outline: none; box-shadow: 0 0 5px rgba(204,0,0,0.2); }

            /* Charts */
            .charts-wrapper { display: flex; gap: 30px; height: 250px; }
            .chart-box { flex: 1; position: relative; }
            
            /* Admin table compact */
            .admin-table th { background: #f5f5f5; border-bottom: 1px solid #dddddd; font-size: 11px; padding: 10px; }
            .admin-table td { font-size: 11px; padding: 10px; }
            .btn-black-small { background: #000000; color: #ffffff; border: none; border-radius: 4px; padding: 6px 12px; font-weight: bold; font-size: 10px; cursor: pointer; letter-spacing: 1px; }
            .btn-black-small:hover { background: #cc0000; }
        </style>
    </head>
    <body>
        <div class="navbar">
            <img src="https://i.ibb.co/r2mMkRTq/Logo.png" alt="Alpha Security">
            <div class="user-info">
                <span>CONECTADO COMO: <b>{{ current_user }}</b></span>
                <a href="/logout" class="btn-rojo">CERRAR SESIÓN</a>
            </div>
        </div>
        
        <div class="container">
            <!-- 1. Cajas de KPI -->
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

            <!-- 2. Sección Exclusiva Admin (Gráficas y Creación de Usuarios) -->
            {% if current_user == 'ADMIN' %}
            <div class="panel" style="border-top: 4px solid #cc0000;">
                <h3 style="color: #cc0000;">GESTIÓN DE PERFILES WEB</h3>
                <div style="display: grid; grid-template-columns: 1fr 2fr; gap: 40px;">
                    <div>
                        <p style="color: #555555; font-size: 11px; margin-bottom: 20px; line-height: 1.5;">Cree un nuevo usuario o sobreescriba uno existente. Asigne el <b>ID EQUIPO</b> para que ese usuario solo vea los datos de su polígono.</p>
                        <form class="form-user" method="POST" action="/crear_usuario">
                            <input type="text" name="new_user" placeholder="NUEVO USUARIO" required>
                            <input type="password" name="new_password" placeholder="CONTRASEÑA" required>
                            <input type="text" name="new_id_alpha" placeholder="ID EQUIPO (Dejar vacío para ver todos)">
                            <button type="submit" class="btn-rojo" style="padding: 14px;">GUARDAR PERFIL</button>
                        </form>
                    </div>
                    <div style="overflow-y: auto; max-height: 250px; border: 1px solid #eeeeee; border-radius: 4px;">
                        <table class="admin-table">
                            <tr>
                                <th>USUARIO</th>
                                <th>ID EQUIPO ASIGNADO</th>
                                <th>CONTRASEÑA</th>
                                <th>ACCIÓN</th>
                            </tr>
                            {% for u in lista_usuarios %}
                            <tr>
                                <td style="font-weight:bold; color: #cc0000;">{{ u.username }}</td>
                                <td>{{ u.id_alpha }}</td>
                                <td style="color:#aaa;">***</td>
                                <td>
                                    {% if u.username != 'ADMIN' %}
                                    <form method="POST" action="/borrar_usuario" style="margin:0;">
                                        <input type="hidden" name="username" value="{{ u.username }}">
                                        <button type="submit" class="btn-black-small">BORRAR</button>
                                    </form>
                                    {% else %}
                                    <span style="color:#aaa; font-size: 10px;">MAESTRO</span>
                                    {% endif %}
                                </td>
                            </tr>
                            {% endfor %}
                        </table>
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

            <!-- 3. Tabla de Datos Estricta -->
            <div class="table-container">
                <table id="dataTable">
                    <thead>
                        <tr>
                            <th>ID Equipo</th>
                            <th>Fecha y Hora</th>
                            <th>Identificación</th>
                            <th>Tirador</th>
                            <th>Misión / Escenario</th>
                            <th>Armamento</th>
                            <th>Impactos</th>
                            <th>Fallos</th>
                            <th>Total</th>
                        </tr>
                        <!-- FILA DE FILTROS BÚSQUEDA EN TIEMPO REAL -->
                        <tr class="filter-row">
                            <th><input type="text" class="filter-input" data-col="0" placeholder="BUSCAR ID..." onkeyup="filterTable()"></th>
                            <th><input type="text" class="filter-input" data-col="1" placeholder="BUSCAR FECHA..." onkeyup="filterTable()"></th>
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
                        {% for r in registros %}
                        <tr class="data-row">
                            <td><b>{{ r.id_alpha }}</b></td>
                            <td style="color: #555555; font-family: 'Consolas', monospace; font-size: 11px; font-weight:bold;">{{ r.fecha_hora.strftime('%Y-%m-%d %H:%M:%S') if r.fecha_hora else '' }}</td>
                            <td style="color: #555555; font-weight: bold;">{{ r.numero_cedula }}</td>
                            <td style="font-weight: bold; color: #cc0000;">{{ r.nombre }}</td>
                            <td style="font-weight: bold;">{{ r.nombre_ejercicio }}</td>
                            <td style="font-weight: bold;">{{ r.tipo_arma }}</td>
                            <td><span class="badge-acierto">{{ r.tiros_acertados }}</span></td>
                            <td><span class="badge-fallo">{{ r.tiros_fallidos }}</span></td>
                            <!-- COLUMNA TOTAL (Aciertos + Fallos) -->
                            <td><span class="badge-total">{{ r.tiros_acertados + r.tiros_fallidos }}</span></td>
                        </tr>
                        {% else %}
                        <tr class="no-data"><td colspan="9" style="color: #555555; padding: 40px; font-style: italic; font-weight: bold;">NO SE HAN RECIBIDO TRANSMISIONES BALÍSTICAS.</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- SCRIPTS JS -->
        <script>
            // FUNCIÓN DE FILTRADO MULTI-COLUMNA EN TIEMPO REAL
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
        </script>

        {% if current_user == 'ADMIN' %}
        <script>
            // Datos Inyectados desde Python para Charts
            const aciertosTotales = {{ kpis.aciertos }};
            const fallosTotales = {{ kpis.fallos }};
            const labelsTiradores = {{ charts.nombres | safe }};
            const dataAciertos = {{ charts.aciertos | safe }};
            const dataFallos = {{ charts.fallos | safe }};

            // 1. Gráfica de Dona
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
                        legend: { position: 'bottom', labels: { boxWidth: 12, font: {family: 'Segoe UI', size: 11, weight: 'bold'}, color: '#000' } }
                    },
                    cutout: '70%'
                }
            });

            // 2. Gráfica de Barras
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
                        y: { beginAtZero: true, grid: { color: '#eeeeee' }, ticks: { color: '#000', font: {weight: 'bold'} } },
                        x: { grid: { display: false }, ticks: { color: '#000', font: {weight: 'bold'} } }
                    },
                    plugins: {
                        legend: { position: 'bottom', labels: { boxWidth: 12, font: {family: 'Segoe UI', size: 11, weight: 'bold'}, color: '#000' } }
                    }
                }
            });
        </script>
        {% endif %}
    </body>
    </html>
    """
    
    # Preparar datos para inyectar en el template HTML
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

    return render_template_string(html, registros=registros_globales, current_user=session.get('user'), kpis=kpis, charts=charts, lista_usuarios=lista_usuarios)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)