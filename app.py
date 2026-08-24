from flask import Flask, request, jsonify, render_template_string
from functools import wraps
import os

app = Flask(__name__)

# --- CONFIGURACIÓN DE CREDENCIALES ---
USUARIO_WEB = os.environ.get('USUARIO_WEB', 'admin')
PASSWORD_WEB = os.environ.get('PASSWORD_WEB', 'alpha2026')

# Base de datos en memoria (Para producción, se recomienda cambiar a SQLite o PostgreSQL)
registros_globales = []

def check_auth(username, password):
    return username == USUARIO_WEB and password == PASSWORD_WEB

def authenticate():
    return jsonify({"error": "Autenticación requerida"}), 401, {'WWW-Authenticate': 'Basic realm="Acceso Restringido"'}

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# --- ENDPOINT API PARA EL SISTEMA ALPHA ---
@app.route('/api/recepcion', methods=['POST'])
@requires_auth
def recepcion_datos():
    data = request.json
    if data:
        registros_globales.insert(0, data) # Insertar al inicio
        return jsonify({"status": "ok", "mensaje": "Datos recibidos correctamente"}), 200
    return jsonify({"error": "Datos inválidos"}), 400

# --- PÁGINA WEB PARA VER LA TABLA ---
@app.route('/', methods=['GET'])
@requires_auth
def index():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard Alpha en la Nube</title>
        <style>
            body { font-family: Arial, sans-serif; background-color: #f4f4f4; margin: 40px; }
            h2 { color: #cc0000; text-align: center; }
            table { width: 100%; border-collapse: collapse; background: #fff; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
            th, td { padding: 12px; border: 1px solid #ddd; text-align: center; }
            th { background-color: #000; color: #fff; }
            tr:nth-child(even) { background-color: #f9f9f9; }
        </style>
    </head>
    <body>
        <h2>🎯 REGISTRO GLOBAL DE TIRO ALPHA</h2>
        <table>
            <tr>
                <th>ID Alpha</th>
                <th>Cédula</th>
                <th>Tirador</th>
                <th>Ejercicio</th>
                <th>Arma</th>
                <th>Aciertos</th>
                <th>Fallos</th>
            </tr>
            {% for r in registros %}
            <tr>
                <td>{{ r.id_alpha }}</td>
                <td>{{ r.numero_cedula }}</td>
                <td>{{ r.nombre }}</td>
                <td>{{ r.nombre_ejercicio }}</td>
                <td>{{ r.tipo_arma }}</td>
                <td style="color: green; font-weight: bold;">{{ r.tiros_acertados }}</td>
                <td style="color: red; font-weight: bold;">{{ r.tiros_fallidos }}</td>
            </tr>
            {% else %}
            <tr><td colspan="7">No hay registros recibidos aún.</td></tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """
    return render_template_string(html, registros=registros_globales)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)