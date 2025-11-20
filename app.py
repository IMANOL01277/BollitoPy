from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
import psycopg2
import psycopg2.extras
import os
import re

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_aqui_cambiar'


# =========================
# FUNCIÓN DE CONEXIÓN
# =========================
def get_conn():
    return psycopg2.connect(
        host=os.getenv("SUPABASE_HOST"),
        port=os.getenv("SUPABASE_PORT", 6543),
        database=os.getenv("SUPABASE_DB"),
        user=os.getenv("SUPABASE_USER"),
        password=os.getenv("SUPABASE_PASSWORD"),
        sslmode="require",
        connect_timeout=5
    )


# ============= DECORADORES =============
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'nombre' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'rol' not in session or session['rol'] != 'administrador':
            flash('⚠️ No tienes permisos para acceder a esta sección', 'danger')
            return redirect(url_for('panel'))
        return f(*args, **kwargs)
    return decorated_function


# ============= RUTAS DE AUTENTICACIÓN =============

@app.route('/')
def index():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form['correo']
        contrasena = request.form['contraseña']

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM usuarios WHERE correo = %s", (correo,))
        usuario = cur.fetchone()
        cur.close()
        conn.close()

        if usuario and check_password_hash(usuario[3], contrasena):
            session['id_usuario'] = usuario[0]
            session['nombre'] = usuario[1]
            session['correo'] = usuario[2]
            session['rol'] = usuario[4]
            return redirect(url_for('panel'))
        else:
            flash('❌ Credenciales incorrectas', 'danger')

    return render_template('login.html')


@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        correo = request.form['correo'].strip()
        contrasena = request.form['contraseña']
        confirmar = request.form['confirmar']

        # Validaciones
        if not re.match(r'^[a-zA-ZáéíóúÁÉÍÓÚñÑ\s]+$', nombre):
            flash('❌ El nombre solo puede contener letras y espacios', 'danger')
            return render_template('registro.html')

        if '..' in correo or not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', correo):
            flash('❌ El correo electrónico no es válido', 'danger')
            return render_template('registro.html')

        if contrasena != confirmar:
            flash('❌ Las contraseñas no coinciden', 'danger')
            return render_template('registro.html')

        if len(contrasena) < 8 or not re.search(r'[A-Z]', contrasena) or not re.search(r'[\W_]', contrasena):
            flash('❌ La contraseña debe tener al menos 8 caracteres, una mayúscula y un carácter especial', 'danger')
            return render_template('registro.html')

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id_usuario FROM usuarios WHERE correo = %s", (correo,))
        if cur.fetchone():
            flash('❌ El correo ya está registrado', 'danger')
            cur.close()
            conn.close()
            return render_template('registro.html')

        contrasena_hash = generate_password_hash(contrasena)
        cur.execute(
            "INSERT INTO usuarios (nombre, correo, contrasena, rol) VALUES (%s, %s, %s, 'empleado')",
            (nombre, correo, contrasena_hash)
        )
        conn.commit()
        cur.close()
        conn.close()

        flash('✅ Registro exitoso. Ahora puedes iniciar sesión', 'success')
        return redirect(url_for('login'))

    return render_template('registro.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ============= PANEL PRINCIPAL =============
@app.route('/panel')
@login_required
def panel():
    return render_template('index.html')


# ============= INVENTARIO =============
@app.route('/inventario')
@login_required
def inventario():
    return render_template('inventario.html')


# ============= ESTADÍSTICAS =============
@app.route('/estadisticas')
@login_required
def estadisticas():
    return render_template('estadisticas.html')


# ============= DOMICILIOS =============
@app.route('/domicilios', methods=['GET', 'POST'])
@login_required
def domicilios():
    conn = get_conn()
    cur = conn.cursor()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'create':
            conductor = request.form['conductor_responsable']
            matricula = request.form['matricula_vehiculo']
            observaciones = request.form['observaciones']
            id_producto = int(request.form['id_producto'])
            cantidad = int(request.form['cantidad'])

            cur.execute("SELECT nombre, precio FROM productos WHERE id_producto = %s", (id_producto,))
            producto = cur.fetchone()

            if producto:
                nombre_producto, precio_unitario = producto
                total = precio_unitario * cantidad

                cur.execute("""
                    INSERT INTO domicilios (conductor_responsable, matricula_vehiculo, observaciones, producto)
                    VALUES (%s, %s, %s, %s)
                """, (conductor, matricula, observaciones, nombre_producto))

                cur.execute("UPDATE productos SET stock = stock - %s WHERE id_producto = %s",
                            (cantidad, id_producto))

                descripcion = f"Domicilio entregado por {conductor}"

                cur.execute("""
                    INSERT INTO movimientos_inventario
                    (id_producto, tipo, cantidad, precio_unitario, total, descripcion)
                    VALUES (%s, 'salida', %s, %s, %s, %s)
                """, (id_producto, cantidad, precio_unitario, total, descripcion))

                conn.commit()
                flash("✅ Domicilio registrado correctamente", "success")

            cur.close()
            conn.close()
            return redirect(url_for('domicilios'))

        if action == 'delete':
            id_domicilio = int(request.form['id_domicilio'])
            cur.execute("DELETE FROM domicilios WHERE id_domicilio = %s", (id_domicilio,))
            conn.commit()
            cur.close()
            conn.close()
            flash("🗑️ Domicilio eliminado", "info")
            return redirect(url_for('domicilios'))

    # GET — LISTAR
    cur.execute("SELECT * FROM domicilios ORDER BY fecha_registro DESC")
    domicilios_list = cur.fetchall()

    cur.execute("SELECT id_producto, nombre, stock FROM productos ORDER BY nombre ASC")
    productos = cur.fetchall()

    cur.close()
    conn.close()
    return render_template('domicilios.html', domicilios=domicilios_list, productos=productos)


# ============= CATEGORÍAS =============
@app.route('/categorias', methods=['GET', 'POST'])
@login_required
@admin_required
def categorias():
    if request.method == 'POST':
        nombre = request.form['nombre']
        descripcion = request.form['descripcion']

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("INSERT INTO categorias (nombre, descripcion) VALUES (%s, %s)", (nombre, descripcion))
        conn.commit()
        cur.close()
        conn.close()

        flash('✅ Categoría creada correctamente', 'success')
        return redirect(url_for('categorias'))

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM categorias ORDER BY id_categoria DESC")
    categorias_list = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('categorias.html', categorias=categorias_list)


# ============= PROVEEDORES =============
@app.route('/proveedores', methods=['GET', 'POST'])
@login_required
@admin_required
def proveedores():
    if request.method == 'POST':
        nombre = request.form['nombre']
        contacto = request.form['contacto']
        telefono = request.form['telefono']
        correo = request.form['correo']
        direccion = request.form['direccion']

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO proveedores (nombre, contacto, telefono, correo, direccion)
            VALUES (%s, %s, %s, %s, %s)
        """, (nombre, contacto, telefono, correo, direccion))
        conn.commit()
        cur.close()
        conn.close()

        flash('✅ Proveedor agregado correctamente', 'success')
        return redirect(url_for('proveedores'))

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM proveedores ORDER BY id_proveedor DESC")
    proveedores_list = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('proveedores.html', proveedores=proveedores_list)


# ============= VENDEDORES =============
@app.route('/vendedores', methods=['GET', 'POST'])
@login_required
@admin_required
def vendedores():
    if request.method == 'POST':
        nombre = request.form['nombre']
        telefono = request.form['telefono']
        direccion = request.form['direccion']

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO vendedores_ambulantes (nombre, telefono, direccion)
            VALUES (%s, %s, %s)
        """, (nombre, telefono, direccion))
        conn.commit()
        cur.close()
        conn.close()

        flash('✅ Vendedor agregado correctamente', 'success')
        return redirect(url_for('vendedores'))

    # DELETE
    if request.args.get('eliminar'):
        id_vendedor = int(request.args.get('eliminar'))

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM vendedores_ambulantes WHERE id_vendedor = %s", (id_vendedor,))
        conn.commit()
        cur.close()
        conn.close()

        flash('🗑️ Vendedor eliminado', 'info')
        return redirect(url_for('vendedores'))

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM vendedores_ambulantes ORDER BY id_vendedor DESC")
    vendedores_list = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('vendedores.html', vendedores=vendedores_list)


# ============= USUARIOS =============
@app.route('/usuarios')
@login_required
@admin_required
def usuarios():
    return render_template('usuarios.html')


# ============= API PRODUCTOS =============
@app.route('/api/productos', methods=['GET', 'POST'])
@login_required
def api_productos():
    action = request.args.get('action') or request.form.get('action')

    conn = get_conn()
    cur = conn.cursor()

    if action == 'list':
        cur.execute("""
            SELECT p.id_producto, p.nombre, p.descripcion, p.precio, p.stock,
                   c.nombre AS categoria, pr.nombre AS proveedor
            FROM productos p
            LEFT JOIN categorias c ON p.id_categoria = c.id_categoria
            LEFT JOIN proveedores pr ON p.id_proveedor = pr.id_proveedor
            ORDER BY p.id_producto DESC
        """)
        productos = cur.fetchall()
        cur.close()
        conn.close()

        lista = []
        for p in productos:
            lista.append({
                "id_producto": p[0],
                "nombre": p[1],
                "descripcion": p[2],
                "precio": float(p[3]),
                "stock": p[4],
                "categoria": p[5],
                "proveedor": p[6]
            })

        return jsonify({"success": True, "products": lista})

    if action == 'categories':
        cur.execute("SELECT id_categoria, nombre FROM categorias ORDER BY nombre ASC")
        cats = cur.fetchall()
        cur.close()
        conn.close()

        return jsonify({"success": True, "categorias": [
            {"id_categoria": c[0], "nombre": c[1]} for c in cats
        ]})

    if action == 'proveedores':
        cur.execute("SELECT id_proveedor, nombre FROM proveedores ORDER BY nombre ASC")
        provs = cur.fetchall()
        cur.close()
        conn.close()

        return jsonify({"success": True, "proveedores": [
            {"id_proveedor": p[0], "nombre": p[1]} for p in provs
        ]})

    if action == 'create':
        nombre = request.form['nombre']
        descripcion = request.form.get('descripcion', '')
        precio = float(request.form['precio'])
        stock = int(request.form['stock'])
        id_categoria = int(request.form['id_categoria'])
        id_proveedor = request.form.get('id_proveedor')

        cur.execute("""
            INSERT INTO productos (nombre, descripcion, precio, stock, id_categoria, id_proveedor)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (nombre, descripcion, precio, stock, id_categoria, id_proveedor))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"success": True, "message": "Producto creado correctamente"})

    cur.close()
    conn.close()
    return jsonify({"success": False, "message": "Acción no válida"})


# ============= API MOVIMIENTOS =============
@app.route('/api/movimientos')
@login_required
def api_movimientos():
    action = request.args.get('action')

    conn = get_conn()
    cur = conn.cursor()

    if action == 'list':
        cur.execute("""
            SELECT m.id_movimiento, m.id_producto, m.tipo, m.cantidad, m.precio_unitario,
                   m.total, m.fecha_movimiento, m.descripcion, p.nombre
            FROM movimientos_inventario m
            LEFT JOIN productos p ON p.id_producto = m.id_producto
            ORDER BY fecha_movimiento DESC
            LIMIT 200
        """)

        movs = cur.fetchall()
        cur.close()
        conn.close()

        lista = []
        for m in movs:
            lista.append({
                "id_movimiento": m[0],
                "id_producto": m[1],
                "tipo": m[2],
                "cantidad": m[3],
                "precio_unitario": float(m[4]),
                "total": float(m[5]),
                "fecha_movimiento": m[6].strftime("%Y-%m-%d %H:%M:%S"),
                "descripcion": m[7],
                "producto": m[8]
            })

        return jsonify({"success": True, "movs": lista})

    cur.close()
    conn.close()
    return jsonify({"success": False, "message": "Acción no válida"})


# ============= API USUARIOS =============
@app.route('/api/usuarios', methods=['GET', 'POST'])
@login_required
@admin_required
def api_usuarios():
    action = request.args.get('action') or request.form.get('action')

    conn = get_conn()
    cur = conn.cursor()

    if action == 'list':
        cur.execute("SELECT id_usuario, nombre, correo, rol FROM usuarios ORDER BY id_usuario DESC")
        users = cur.fetchall()
        cur.close()
        conn.close()

        lista = []
        for u in users:
            lista.append({
                "id_usuario": u[0],
                "nombre": u[1],
                "correo": u[2],
                "rol": u[3]
            })

        return jsonify({"success": True, "users": lista})

    if action == 'create':
        nombre = request.form['nombre']
        correo = request.form['correo']
        contrasena = generate_password_hash(request.form['contraseña'])
        rol = request.form['rol']

        cur.execute(
            "INSERT INTO usuarios (nombre, correo, contrasena, rol) VALUES (%s, %s, %s, %s)",
            (nombre, correo, contrasena, rol)
        )
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"success": True, "message": "Usuario creado"})

    if action == 'delete':
        id_usuario = int(request.form['id_usuario'])

        cur.execute("DELETE FROM usuarios WHERE id_usuario = %s", (id_usuario,))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"success": True, "message": "Usuario eliminado"})

    cur.close()
    conn.close()
    return jsonify({"success": False, "message": "Acción inválida"})


# =========================
# EJECUCIÓN
# =========================

if __name__ == "__main__":
    app.run(debug=True)


