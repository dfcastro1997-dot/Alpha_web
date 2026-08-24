from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
from functools import wraps
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
import os

app = Flask(__name__)
app.secret_key = "super_clave_secreta_alpha_2026"

# --- CONEXIÓN A AIVEN (POSTGRESQL) ---
# Toma la URL de conexión desde Render. Si no existe, lanza un error para avisarte.
DB_URI = os.environ.get("DATABASE_URL")

def get_db_connection():
    if not DB_URI:
        raise ValueError("Falta configurar la variable DATABASE_URL con la conexión a Aiven")
    return psycopg2.connect(DB_URI)

# --- INICIALIZAR TABLAS EN AIVEN ---
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # Crear tabla de usuarios web
    cur.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            username VARCHAR(50) PRIMARY KEY,
            password VARCHAR(100) NOT NULL
        )
    ''')
    # Crear administrador por defecto si no existe
    cur.execute('''
        INSERT INTO usuarios (username, password) 
        VALUES ('ADMIN', '80406651DETAIMALPHA') 
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
            tiros_fallidos INT
        )
    ''')
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
            return jsonify({"error": "No autorizado"}), 401
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
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO registros 
            (id_alpha, fecha_hora, numero_cedula, nombre, nombre_ejercicio, tipo_arma, tiros_acertados, tiros_fallidos)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            data.get('id_alpha', 'DESCONOCIDO'),
            fecha_hora,
            data.get('numero_cedula', 'N/A'),
            data.get('nombre', 'N/A'),
            data.get('nombre_ejercicio', 'N/A'),
            data.get('tipo_arma', 'N/A'),
            data.get('tiros_acertados', 0),
            data.get('tiros_fallidos', 0)
        ))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "ok", "mensaje": "Datos guardados en PostgreSQL exitosamente"}), 200
    return jsonify({"error": "Datos inválidos"}), 400

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
            error = "Credenciales incorrectas"
            
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
            p { color: #333333; font-size: 14px; font-weight: bold; margin-bottom: 25px; letter-spacing: 1px; }
            input { width: 90%; padding: 14px; margin: 10px 0; border: 2px solid #dddddd; border-radius: 6px; font-weight: bold; text-align: center; font-size: 14px; color: #000000;}
            input:focus { border: 2px solid #000000; outline: none; background: #fafafa;}
            button { background: #000000; color: #ffffff; border: none; padding: 16px 20px; width: 100%; border-radius: 6px; font-weight: bold; letter-spacing: 2px; cursor: pointer; margin-top: 20px; font-size: 14px; transition: background 0.3s;}
            button:hover { background: #cc0000; }
            .error { color: #ffffff; background: #cc0000; padding: 10px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-top: 20px; }
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
            {% if error %}<div class="error">❌ {{ error }}</div>{% endif %}
        </div>
    </body>
    </html>
    """
    return render_template_string(html, error=error)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

# --- 3. CREAR NUEVO USUARIO WEB EN AIVEN (Solo ADMIN) ---
@app.route('/crear_usuario', methods=['POST'])
@login_required
def crear_usuario():
    if session.get('user') == 'ADMIN':
        new_u = request.form.get('new_user')
        new_p = request.form.get('new_password')
        if new_u and new_p:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO usuarios (username, password) 
                VALUES (%s, %s) 
                ON CONFLICT (username) DO UPDATE SET password = EXCLUDED.password
            ''', (new_u.upper(), new_p))
            conn.commit()
            cur.close()
            conn.close()
    return redirect(url_for('index'))

# --- 4. DASHBOARD (Tabla Profesional + Gráficas + Filtros) ---
@app.route('/', methods=['GET'])
@login_required
def index():
    # Obtener todos los registros desde PostgreSQL
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM registros ORDER BY id DESC")
    registros_globales = cur.fetchall()
    cur.close()
    conn.close()

    # --- CÁLCULOS PARA KPIS ---
    total_registros = len(registros_globales)
    aciertos = sum(r.get('tiros_acertados', 0) for r in registros_globales)
    fallos = sum(r.get('tiros_fallidos', 0) for r in registros_globales)
    total_disparos = aciertos + fallos
    precision = round((aciertos / total_disparos * 100), 1) if total_disparos > 0 else 0

    # --- CÁLCULOS PARA GRÁFICAS ---
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
            body { background-color: #f0f2f5; font-family: 'Segoe UI', Arial, sans-serif; margin: 0; color: #333; }
            
            /* Header / Navbar en Blanco */
            .navbar { background: #ffffff; padding: 15px 40px; color: #000000; display: flex; justify-content: space-between; align-items: center; border-bottom: 5px solid #cc0000; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
            .navbar img { height: 45px; filter: drop-shadow(0px 1px 2px rgba(0,0,0,0.2)); } 
            .user-info { display: flex; align-items: center; gap: 20px; }
            .user-info span { font-size: 13px; color: #555555; letter-spacing: 1px; }
            .user-info b { color: #000000; font-size: 15px; }
            .btn-rojo { background: #cc0000; color: #ffffff; padding: 10px 25px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 12px; border: none; cursor: pointer; letter-spacing: 1px; transition: background 0.3s;}
            .btn-rojo:hover { background: #aa0000; }
            
            .container { padding: 40px; max-width: 1450px; margin: 0 auto; }
            
            /* KPIs */
            .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; }
            .kpi-card { background: #ffffff; padding: 25px; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border-left: 5px solid #cc0000; display: flex; flex-direction: column; justify-content: center; }
            .kpi-title { font-size: 12px; color: #7f8c8d; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }
            .kpi-value { font-size: 32px; font-weight: bold; color: #000000; margin: 0; font-family: 'Consolas', monospace; }
            .kpi-card:nth-child(2) { border-left-color: #000000; }
            .kpi-card:nth-child(3) { border-left-color: #27ae60; }
            
            /* Layout Admin */
            .admin-grid { display: grid; grid-template-columns: 1fr 2fr; gap: 30px; margin-bottom: 30px; }
            
            /* Panels */
            .panel { background: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
            .panel h3 { margin-top: 0; color: #000000; font-size: 16px; letter-spacing: 1px; border-bottom: 2px solid #f0f0f0; padding-bottom: 10px; margin-bottom: 20px; }
            
            /* Formularios */
            .form-user { display: flex; flex-direction: column; gap: 15px; }
            .form-user input { padding: 12px; border: 1px solid #cccccc; border-radius: 4px; font-weight: bold; font-size: 13px; color: #000;}
            .form-user input:focus { border: 1px solid #cc0000; outline: none; }
            
            /* Tablas en Blanco con texto negro */
            .table-container { overflow-x: auto; background: #ffffff; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border-top: 4px solid #cc0000; }
            table { width: 100%; border-collapse: collapse; }
            th, td { padding: 16px; text-align: center; font-size: 13px; }
            th { background-color: #ffffff; color: #000000; text-transform: uppercase; font-size: 12px; letter-spacing: 1px; position: sticky; top: 0; border-bottom: 2px solid #eeeeee; }
            td { border-bottom: 1px solid #eeeeee; color: #333333; }
            tr:hover { background-color: #fafafa; }
            
            .badge-acierto { background-color: #e8f8f5; color: #27ae60; padding: 5px 12px; border-radius: 12px; font-weight: bold; font-size: 14px; }
            .badge-fallo { background-color: #fdedec; color: #cc0000; padding: 5px 12px; border-radius: 12px; font-weight: bold; font-size: 14px; }
            .badge-total { background-color: #f4f6f7; color: #34495e; padding: 5px 12px; border-radius: 12px; font-weight: bold; font-size: 14px; border: 1px solid #d5dbdb;}
            
            /* Inputs de Filtro en Tabla (Grises claros) */
            .filter-row th { background-color: #f9f9f9; padding: 10px 8px; border-top: 1px solid #eeeeee; border-bottom: 2px solid #dddddd; }
            .filter-input { width: 85%; padding: 8px; border: 1px solid #cccccc; border-radius: 4px; background: #ffffff; color: #000000; font-size: 11px; font-weight: bold; text-align: center; }
            .filter-input::placeholder { color: #999999; }
            .filter-input:focus { border-color: #cc0000; outline: none; box-shadow: 0 0 5px rgba(204,0,0,0.1); }

            /* Charts */
            .charts-wrapper { display: flex; gap: 20px; height: 250px; }
            .chart-box { flex: 1; position: relative; }
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
                    <h2 class="kpi-value" style="color: #27ae60;">{{ kpis.precision }}%</h2>
                </div>
                <div class="kpi-card" style="border-left-color: #34495e;">
                    <span class="kpi-title">ESTADO BD AIVEN</span>
                    <h2 class="kpi-value" style="color: #34495e; font-size: 24px; margin-top: 8px;">CONECTADO 🟢</h2>
                </div>
            </div>

            <!-- 2. Sección Exclusiva Admin (Gráficas y Creación de Usuarios) -->
            {% if current_user == 'ADMIN' %}
            <div class="admin-grid">
                <div class="panel" style="border-top: 4px solid #cc0000;">
                    <h3 style="color: #cc0000;">⚙️ GESTIÓN DE PERFILES WEB</h3>
                    <p style="color: #777; font-size: 12px; margin-bottom: 20px;">Añada operadores para acceder al panel. (Guardados en PostgreSQL).</p>
                    <form class="form-user" method="POST" action="/crear_usuario">
                        <input type="text" name="new_user" placeholder="NUEVO USUARIO" required>
                        <input type="password" name="new_password" placeholder="CONTRASEÑA" required>
                        <button type="submit" class="btn-rojo">REGISTRAR ACCESO</button>
                    </form>
                </div>
                
                <div class="panel">
                    <h3>📊 ANÁLISIS DE RENDIMIENTO (Últimas 5 Sesiones)</h3>
                    <div class="charts-wrapper">
                        <div class="chart-box">
                            <canvas id="hitMissChart"></canvas>
                        </div>
                        <div class="chart-box" style="flex: 2;">
                            <canvas id="barChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
            {% endif %}

            <!-- 3. Tabla de Datos -->
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
                            <th><input type="text" class="filter-input" data-col="0" placeholder="🔍 Buscar ID..." onkeyup="filterTable()"></th>
                            <th><input type="text" class="filter-input" data-col="1" placeholder="🔍 Buscar Fecha..." onkeyup="filterTable()"></th>
                            <th><input type="text" class="filter-input" data-col="2" placeholder="🔍 Buscar Cédula..." onkeyup="filterTable()"></th>
                            <th><input type="text" class="filter-input" data-col="3" placeholder="🔍 Buscar Tirador..." onkeyup="filterTable()"></th>
                            <th><input type="text" class="filter-input" data-col="4" placeholder="🔍 Buscar Misión..." onkeyup="filterTable()"></th>
                            <th><input type="text" class="filter-input" data-col="5" placeholder="🔍 Buscar Arma..." onkeyup="filterTable()"></th>
                            <th></th>
                            <th></th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for r in registros %}
                        <tr class="data-row">
                            <td><b>{{ r.id_alpha }}</b></td>
                            <td style="color: #7f8c8d; font-family: 'Consolas', monospace; font-size: 12px;"><b>{{ r.fecha_hora.strftime('%Y-%m-%d %H:%M:%S') if r.fecha_hora else '' }}</b></td>
                            <td style="color: #7f8c8d;">{{ r.numero_cedula }}</td>
                            <td style="font-weight: bold; color: #cc0000;">{{ r.nombre }}</td>
                            <td style="font-weight: bold;">{{ r.nombre_ejercicio }}</td>
                            <td>{{ r.tipo_arma }}</td>
                            <td><span class="badge-acierto">{{ r.tiros_acertados }}</span></td>
                            <td><span class="badge-fallo">{{ r.tiros_fallidos }}</span></td>
                            <!-- COLUMNA TOTAL (Aciertos + Fallos) -->
                            <td><span class="badge-total">{{ r.tiros_acertados + r.tiros_fallidos }}</span></td>
                        </tr>
                        {% else %}
                        <tr class="no-data"><td colspan="9" style="color: #aaaaaa; padding: 40px; font-style: italic;">No se han recibido transmisiones balísticas en la base de datos de Aiven.</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- SCRIPTS JS -->
        <script>
            // FUNCIÓN PROFESIONAL DE FILTRADO MULTI-COLUMNA
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
                        legend: { position: 'bottom', labels: { boxWidth: 12, font: {family: 'Segoe UI', size: 11} } }
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
                        y: { beginAtZero: true, grid: { color: '#eee' } },
                        x: { grid: { display: false } }
                    },
                    plugins: {
                        legend: { position: 'bottom', labels: { boxWidth: 12, font: {family: 'Segoe UI', size: 11} } }
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

    return render_template_string(html, registros=registros_globales, current_user=session.get('user'), kpis=kpis, charts=charts)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)