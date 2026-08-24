from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
from functools import wraps
import os

app = Flask(__name__)
app.secret_key = "super_clave_secreta_alpha_2026" # Requerido para las sesiones HTML

# Base de datos en memoria (Usuarios y Registros)
# Nota: Al reiniciar Render, los usuarios nuevos se borrarán. Para producción final se pasará a SQLite.
usuarios_db = {
    "ADMIN": "80406651DETAIMALPHA"
}
registros_globales = []

# --- MIDDLEWARE PARA LA API (Software de Escritorio) ---
def requires_api_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username not in usuarios_db or usuarios_db[auth.username] != auth.password:
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

# --- 1. ENDPOINT API (Recibe los datos silenciosamente) ---
@app.route('/api/recepcion', methods=['POST'])
@requires_api_auth
def recepcion_datos():
    data = request.json
    if data:
        registros_globales.insert(0, data)
        return jsonify({"status": "ok", "mensaje": "Datos recibidos correctamente"}), 200
    return jsonify({"error": "Datos inválidos"}), 400

# --- 2. PÁGINA DE LOGIN HTML ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username in usuarios_db and usuarios_db[username] == password:
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
            body { background-color: #000000; font-family: 'Segoe UI', Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; color: #ffffff; }
            .login-box { background: #ffffff; padding: 40px; border-top: 6px solid #cc0000; border-radius: 8px; width: 350px; text-align: center; box-shadow: 0 10px 30px rgba(204,0,0,0.2); }
            h2 { color: #cc0000; margin-top: 0; letter-spacing: 2px; }
            p { color: #555555; font-size: 13px; font-weight: bold; margin-bottom: 25px; }
            input { width: 90%; padding: 12px; margin: 10px 0; border: 2px solid #dddddd; border-radius: 4px; font-weight: bold; text-align: center; }
            input:focus { border: 2px solid #000000; outline: none; }
            button { background: #000000; color: #ffffff; border: none; padding: 14px 20px; width: 100%; border-radius: 4px; font-weight: bold; letter-spacing: 1px; cursor: pointer; margin-top: 15px; }
            button:hover { background: #cc0000; }
            .error { color: #cc0000; font-size: 12px; font-weight: bold; margin-top: 15px; }
        </style>
    </head>
    <body>
        <div class="login-box">
            <h2>ALPHA SECURITY</h2>
            <p>ACCESO A LA NUBE</p>
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

# --- 3. CREAR NUEVO USUARIO WEB (Solo ADMIN) ---
@app.route('/crear_usuario', methods=['POST'])
@login_required
def crear_usuario():
    if session.get('user') == 'ADMIN':
        new_u = request.form.get('new_user')
        new_p = request.form.get('new_password')
        if new_u and new_p:
            usuarios_db[new_u] = new_p
    return redirect(url_for('index'))

# --- 4. DASHBOARD (Tabla Profesional) ---
@app.route('/', methods=['GET'])
@login_required
def index():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard | Alpha Security</title>
        <style>
            body { background-color: #f5f5f5; font-family: 'Segoe UI', Arial, sans-serif; margin: 0; color: #333; }
            .navbar { background: #000000; padding: 15px 40px; color: #ffffff; display: flex; justify-content: space-between; align-items: center; border-bottom: 5px solid #cc0000; }
            .navbar h2 { margin: 0; font-size: 22px; letter-spacing: 2px; }
            .btn-rojo { background: #cc0000; color: #ffffff; padding: 10px 20px; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 12px; border: none; cursor: pointer; }
            .btn-rojo:hover { background: #aa0000; }
            .container { padding: 40px; max-width: 1400px; margin: 0 auto; }
            .panel { background: #ffffff; padding: 25px; border-radius: 8px; box-shadow: 0 5px 15px rgba(0,0,0,0.05); margin-bottom: 30px; border: 1px solid #e0e0e0; border-top: 4px solid #000000; }
            table { width: 100%; border-collapse: collapse; margin-top: 15px; }
            th, td { padding: 15px; border-bottom: 1px solid #eeeeee; text-align: center; font-size: 14px; }
            th { background-color: #000000; color: #ffffff; text-transform: uppercase; font-size: 12px; letter-spacing: 1px; }
            tr:hover { background-color: #fff0f0; }
            .form-user { display: flex; gap: 15px; margin-top: 15px;}
            .form-user input { padding: 12px; border: 1px solid #cccccc; border-radius: 4px; flex: 1; font-weight: bold; }
            .form-user input:focus { border: 1px solid #000000; outline: none; }
            .acierto { color: #27ae60; font-weight: bold; }
            .fallo { color: #cc0000; font-weight: bold; }
        </style>
    </head>
    <body>
        <div class="navbar">
            <h2>ALPHA <span style="color:#cc0000;">SECURITY</span></h2>
            <div>
                <span style="margin-right: 20px; font-size: 14px;">OPERADOR: <b>{{ current_user }}</b></span>
                <a href="/logout" class="btn-rojo">CERRAR SESIÓN</a>
            </div>
        </div>
        <div class="container">
            
            {% if current_user == 'ADMIN' %}
            <div class="panel" style="border-top: 4px solid #cc0000;">
                <h3 style="margin-top: 0; color: #cc0000;">⚙️ GESTIÓN DE PERFILES WEB</h3>
                <p style="color: #777; font-size: 13px;">Añada sub-usuarios para que puedan acceder a este panel. (Se borrarán al reiniciar el servidor en versión Lite).</p>
                <form class="form-user" method="POST" action="/crear_usuario">
                    <input type="text" name="new_user" placeholder="NUEVO USUARIO" required>
                    <input type="password" name="new_password" placeholder="CONTRASEÑA" required>
                    <button type="submit" class="btn-rojo" style="padding: 0 30px;">REGISTRAR</button>
                </form>
            </div>
            {% endif %}

            <div class="panel">
                <h3 style="margin-top: 0; color: #000000;">🎯 BASE DE DATOS DE IMPACTOS EN VIVO</h3>
                <table>
                    <tr>
                        <th>ID Equipo</th>
                        <th>Identificación</th>
                        <th>Tirador</th>
                        <th>Misión / Escenario</th>
                        <th>Armamento</th>
                        <th>Impactos</th>
                        <th>Fallos</th>
                    </tr>
                    {% for r in registros %}
                    <tr>
                        <td><strong>{{ r.id_alpha }}</strong></td>
                        <td>{{ r.numero_cedula }}</td>
                        <td>{{ r.nombre }}</td>
                        <td>{{ r.nombre_ejercicio }}</td>
                        <td>{{ r.tipo_arma }}</td>
                        <td class="acierto">{{ r.tiros_acertados }}</td>
                        <td class="fallo">{{ r.tiros_fallidos }}</td>
                    </tr>
                    {% else %}
                    <tr><td colspan="7" style="color: #aaaaaa; padding: 40px; font-style: italic;">No se han recibido transmisiones balísticas recientes.</td></tr>
                    {% endfor %}
                </table>
            </div>
        </div>
    </body>
    </html>
    """
    return render_template_string(html, registros=registros_globales, current_user=session.get('user'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)