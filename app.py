from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
import re

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_aqui_cambiar'

# Configuración de MySQL
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'bd_mibollito'

mysql = MySQL(app)

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
        contraseña = request.form['contraseña']
        
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM usuarios WHERE correo = %s", (correo,))
        usuario = cur.fetchone()
        cur.close()
        
        if usuario and check_password_hash(usuario[4], contraseña):
            session['nombre'] = usuario[1]
            session['correo'] = usuario[2]
            session['rol'] = usuario[5]
            session['id_usuario'] = usuario[0]
            return redirect(url_for('panel'))
        else:
            flash('❌ Credenciales incorrectas', 'danger')
    
    return render_template('login.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        correo = request.form['correo'].strip()
        contraseña = request.form['contraseña']
        confirmar = request.form['confirmar']
        
        # Validaciones
        if not re.match(r'^[a-zA-ZáéíóúÁÉÍÓÚñÑ\s]+$', nombre):
            flash('❌ El nombre solo puede contener letras y espacios', 'danger')
            return render_template('registro.html')
        
        if '..' in correo or not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', correo):
            flash('❌ El correo electrónico no es válido', 'danger')
            return render_template('registro.html')
        
        if contraseña != confirmar:
            flash('❌ Las contraseñas no coinciden', 'danger')
            return render_template('registro.html')
        
        if len(contraseña) < 8 or not re.search(r'[A-Z]', contraseña) or not re.search(r'[\W_]', contraseña):
            flash('❌ La contraseña debe tener al menos 8 caracteres, una mayúscula y un carácter especial', 'danger')
            return render_template('registro.html')
        
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM usuarios WHERE correo = %s", (correo,))
        if cur.fetchone():
            flash('❌ El correo ya está registrado', 'danger')
            cur.close()
            return render_template('registro.html')
        
        contraseña_hash = generate_password_hash(contraseña)
        cur.execute("INSERT INTO usuarios (nombre, correo, contraseña) VALUES (%s, %s, %s)",
                   (nombre, correo, contraseña_hash))
        mysql.connection.commit()
        cur.close()
        
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
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create':
            conductor = request.form['conductor_responsable'].strip()
            matricula = request.form['matricula_vehiculo'].strip()
            observaciones = request.form['observaciones'].strip()
            id_producto = int(request.form['id_producto'])
            cantidad = int(request.form['cantidad'])
            
            cur = mysql.connection.cursor()
            cur.execute("SELECT nombre, precio FROM productos WHERE id_producto = %s", (id_producto,))
            producto = cur.fetchone()
            
            if producto and cantidad > 0:
                nombre_producto = producto[0]
                precio_unitario = producto[1]
                total = precio_unitario * cantidad
                
                # Registrar domicilio
                cur.execute("""INSERT INTO domicilios (conductor_responsable, matricula_vehiculo, 
                            observaciones, producto) VALUES (%s, %s, %s, %s)""",
                           (conductor, matricula, observaciones, nombre_producto))
                
                # Descontar stock
                cur.execute("UPDATE productos SET stock = stock - %s WHERE id_producto = %s",
                           (cantidad, id_producto))
                
                # Registrar movimiento
                descripcion = f"Domicilio entregado por {conductor}"
                cur.execute("""INSERT INTO movimientos_inventario 
                            (id_producto, tipo, cantidad, precio_unitario, total, descripcion)
                            VALUES (%s, 'salida', %s, %s, %s, %s)""",
                           (id_producto, cantidad, precio_unitario, total, descripcion))
                
                mysql.connection.commit()
                flash('✅ Domicilio registrado correctamente', 'success')
            else:
                flash('⚠️ Producto inválido o cantidad incorrecta', 'warning')
            
            cur.close()
            return redirect(url_for('domicilios'))
        
        elif action == 'delete':
            id_domicilio = int(request.form['id_domicilio'])
            cur = mysql.connection.cursor()
            cur.execute("DELETE FROM domicilios WHERE id_domicilio = %s", (id_domicilio,))
            mysql.connection.commit()
            cur.close()
            flash('🗑️ Domicilio eliminado', 'info')
            return redirect(url_for('domicilios'))
    
    # GET request
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM domicilios ORDER BY fecha_registro DESC")
    domicilios_list = cur.fetchall()
    
    cur.execute("SELECT id_producto, nombre, stock FROM productos ORDER BY nombre ASC")
    productos = cur.fetchall()
    cur.close()
    
    return render_template('domicilios.html', domicilios=domicilios_list, productos=productos)

# ============= CATEGORÍAS =============
@app.route('/categorias', methods=['GET', 'POST'])
@login_required
@admin_required
def categorias():
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        descripcion = request.form['descripcion'].strip()
        
        if nombre:
            cur = mysql.connection.cursor()
            cur.execute("INSERT INTO categorias (nombre, descripcion) VALUES (%s, %s)",
                       (nombre, descripcion))
            mysql.connection.commit()
            cur.close()
            flash('✅ Categoría creada correctamente', 'success')
        else:
            flash('❌ El nombre no puede estar vacío', 'danger')
        
        return redirect(url_for('categorias'))
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM categorias ORDER BY id_categoria DESC")
    categorias_list = cur.fetchall()
    cur.close()
    
    return render_template('categorias.html', categorias=categorias_list)

# ============= PROVEEDORES =============
@app.route('/proveedores', methods=['GET', 'POST'])
@login_required
@admin_required
def proveedores():
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        contacto = request.form['contacto'].strip()
        telefono = request.form['telefono'].strip()
        correo = request.form['correo'].strip()
        direccion = request.form['direccion'].strip()
        
        cur = mysql.connection.cursor()
        cur.execute("""INSERT INTO proveedores (nombre, contacto, telefono, correo, direccion)
                    VALUES (%s, %s, %s, %s, %s)""",
                   (nombre, contacto, telefono, correo, direccion))
        mysql.connection.commit()
        cur.close()
        flash('✅ Proveedor agregado correctamente', 'success')
        return redirect(url_for('proveedores'))
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM proveedores ORDER BY id_proveedor DESC")
    proveedores_list = cur.fetchall()
    cur.close()
    
    return render_template('proveedores.html', proveedores=proveedores_list)

# ============= VENDEDORES =============
@app.route('/vendedores', methods=['GET', 'POST'])
@login_required
@admin_required
def vendedores():
    if request.method == 'POST':
        if 'add_vendedor' in request.form:
            nombre = request.form['nombre'].strip()
            telefono = request.form['telefono'].strip()
            direccion = request.form['direccion'].strip()
            
            cur = mysql.connection.cursor()
            cur.execute("""INSERT INTO vendedores_ambulantes (nombre, telefono, direccion)
                        VALUES (%s, %s, %s)""", (nombre, telefono, direccion))
            mysql.connection.commit()
            cur.close()
            flash('✅ Vendedor agregado correctamente', 'success')
        
        return redirect(url_for('vendedores'))
    
    # Eliminar vendedor
    if request.args.get('eliminar'):
        id_vendedor = int(request.args.get('eliminar'))
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM vendedores_ambulantes WHERE id_vendedor = %s", (id_vendedor,))
        mysql.connection.commit()
        cur.close()
        flash('🗑️ Vendedor eliminado', 'info')
        return redirect(url_for('vendedores'))
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM vendedores_ambulantes ORDER BY id_vendedor DESC")
    vendedores_list = cur.fetchall()
    cur.close()
    
    return render_template('vendedores.html', vendedores=vendedores_list)

# ============= USUARIOS =============
@app.route('/usuarios')
@login_required
@admin_required
def usuarios():
    return render_template('usuarios.html')

# ============= API ENDPOINTS =============

# API Productos
@app.route('/api/productos', methods=['GET', 'POST'])
@login_required
def api_productos():
    action = request.args.get('action') or request.form.get('action')
    cur = mysql.connection.cursor()
    
    if action == 'list':
        cur.execute("""SELECT p.id_producto, p.nombre, p.descripcion, p.precio, p.stock,
                    c.nombre AS categoria, pr.nombre AS proveedor
                    FROM productos p
                    LEFT JOIN categorias c ON p.id_categoria = c.id_categoria
                    LEFT JOIN proveedores pr ON p.id_proveedor = pr.id_proveedor
                    ORDER BY p.id_producto DESC""")
        productos = cur.fetchall()
        cur.close()
        
        products_list = []
        for p in productos:
            products_list.append({
                'id_producto': p[0], 'nombre': p[1], 'descripcion': p[2],
                'precio': float(p[3]), 'stock': p[4], 'categoria': p[5], 'proveedor': p[6]
            })
        return jsonify({'success': True, 'products': products_list})
    
    elif action == 'categories':
        cur.execute("SELECT id_categoria, nombre FROM categorias ORDER BY nombre ASC")
        cats = cur.fetchall()
        cur.close()
        return jsonify({'success': True, 'categorias': [{'id_categoria': c[0], 'nombre': c[1]} for c in cats]})
    
    elif action == 'proveedores':
        cur.execute("SELECT id_proveedor, nombre FROM proveedores ORDER BY nombre ASC")
        provs = cur.fetchall()
        cur.close()
        return jsonify({'success': True, 'proveedores': [{'id_proveedor': p[0], 'nombre': p[1]} for p in provs]})
    
    elif action == 'create':
        nombre = request.form['nombre'].strip()
        descripcion = request.form.get('descripcion', '').strip()
        precio = float(request.form['precio'])
        stock = int(request.form['stock'])
        id_categoria = int(request.form['id_categoria'])
        id_proveedor = request.form.get('id_proveedor')
        
        cur.execute("""INSERT INTO productos (nombre, descripcion, precio, stock, stock_actual, 
                    id_categoria, id_proveedor) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                   (nombre, descripcion, precio, stock, stock, id_categoria, id_proveedor))
        mysql.connection.commit()
        new_id = cur.lastrowid
        
        if stock > 0:
            total = precio * stock
            cur.execute("""INSERT INTO movimientos_inventario (id_producto, tipo, cantidad, 
                        precio_unitario, total, descripcion) VALUES (%s, 'entrada', %s, %s, %s, %s)""",
                       (new_id, stock, precio, total, 'Registro inicial de stock'))
            mysql.connection.commit()
        
        cur.close()
        return jsonify({'success': True, 'message': 'Producto creado correctamente'})
    
    elif action == 'get':
        id_producto = int(request.args.get('id'))
        cur.execute("SELECT * FROM productos WHERE id_producto = %s", (id_producto,))
        producto = cur.fetchone()
        cur.close()
        
        if producto:
            return jsonify({'success': True, 'product': {
                'id_producto': producto[0], 'nombre': producto[1], 'id_categoria': producto[2],
                'descripcion': producto[3], 'precio': float(producto[4]), 'stock': producto[5],
                'id_proveedor': producto[6]
            }})
        return jsonify({'success': False, 'message': 'Producto no encontrado'})
    
    elif action == 'update':
        id_producto = int(request.form['id_producto'])
        nombre = request.form['nombre'].strip()
        descripcion = request.form.get('descripcion', '').strip()
        precio = float(request.form['precio'])
        stock = int(request.form['stock'])
        id_categoria = int(request.form['id_categoria'])
        id_proveedor = request.form.get('id_proveedor')
        
        # Obtener stock anterior
        cur.execute("SELECT stock, precio FROM productos WHERE id_producto = %s", (id_producto,))
        old_data = cur.fetchone()
        old_stock = old_data[0]
        old_precio = old_data[1]
        
        cur.execute("""UPDATE productos SET nombre=%s, descripcion=%s, precio=%s, stock=%s,
                    id_categoria=%s, id_proveedor=%s WHERE id_producto=%s""",
                   (nombre, descripcion, precio, stock, id_categoria, id_proveedor, id_producto))
        
        # Registrar movimiento si cambió stock
        cantidad = stock - old_stock
        if cantidad != 0:
            tipo = 'entrada' if cantidad > 0 else 'salida'
            cantidad_abs = abs(cantidad)
            precio_usado = precio if precio > 0 else old_precio
            total = cantidad_abs * precio_usado
            
            cur.execute("""INSERT INTO movimientos_inventario (id_producto, tipo, cantidad,
                        precio_unitario, total, descripcion) VALUES (%s, %s, %s, %s, %s, %s)""",
                       (id_producto, tipo, cantidad_abs, precio_usado, total, 'Actualización de stock'))
        
        mysql.connection.commit()
        cur.close()
        return jsonify({'success': True, 'message': 'Producto actualizado correctamente'})
    
    elif action == 'delete':
        id_producto = int(request.form['id_producto'])
        cur.execute("DELETE FROM movimientos_inventario WHERE id_producto = %s", (id_producto,))
        cur.execute("DELETE FROM productos WHERE id_producto = %s", (id_producto,))
        mysql.connection.commit()
        cur.close()
        return jsonify({'success': True, 'message': 'Producto eliminado'})
    
    cur.close()
    return jsonify({'success': False, 'message': 'Acción no válida'})

# API Movimientos
@app.route('/api/movimientos')
@login_required
def api_movimientos():
    action = request.args.get('action')
    cur = mysql.connection.cursor()
    
    if action == 'resumen':
        cur.execute("""SELECT tipo, SUM(total) as total FROM movimientos_inventario
                    WHERE fecha_movimiento >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                    GROUP BY tipo""")
        movs = cur.fetchall()
        cur.close()
        
        resumen = {'entrada': 0, 'salida': 0, 'ganancia': 0}
        for m in movs:
            resumen[m[0]] = float(m[1])
        resumen['ganancia'] = resumen['salida'] - resumen['entrada']
        
        return jsonify({'success': True, 'resumen': resumen})
    
    elif action == 'list':
        cur.execute("""SELECT m.*, p.nombre AS producto FROM movimientos_inventario m
                    LEFT JOIN productos p ON p.id_producto = m.id_producto
                    WHERE fecha_movimiento >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                    ORDER BY fecha_movimiento DESC""")
        movs = cur.fetchall()
        cur.close()
        
        movs_list = []
        for m in movs:
            movs_list.append({
                'id_movimiento': m[0], 'id_producto': m[1], 'tipo': m[2],
                'cantidad': m[3], 'precio_unitario': float(m[4]), 'total': float(m[5]),
                'fecha_movimiento': m[6].strftime('%Y-%m-%d %H:%M:%S'),
                'descripcion': m[7], 'producto': m[8]
            })
        return jsonify({'success': True, 'movs': movs_list})
    
    cur.close()
    return jsonify({'success': False, 'message': 'Acción no válida'})

# API Usuarios
@app.route('/api/usuarios', methods=['GET', 'POST'])
@login_required
@admin_required
def api_usuarios():
    action = request.args.get('action') or request.form.get('action')
    cur = mysql.connection.cursor()
    
    if action == 'list':
        cur.execute("SELECT id_usuario, nombre, correo, rol FROM usuarios ORDER BY id_usuario DESC")
        users = cur.fetchall()
        cur.close()
        
        users_list = []
        for u in users:
            users_list.append({
                'id_usuario': u[0], 'nombre': u[1], 'correo': u[2], 'rol': u[3]
            })
        return jsonify({'success': True, 'users': users_list})
    
    elif action == 'create':
        nombre = request.form['nombre']
        correo = request.form['correo']
        contraseña = generate_password_hash(request.form['contraseña'])
        rol = request.form.get('rol', 'empleado')
        
        cur.execute("INSERT INTO usuarios (nombre, correo, contraseña, rol) VALUES (%s, %s, %s, %s)",
                   (nombre, correo, contraseña, rol))
        mysql.connection.commit()
        cur.close()
        return jsonify({'success': True, 'message': 'Usuario creado'})
    
    elif action == 'update':
        id_usuario = int(request.form['id_usuario'])
        nombre = request.form['nombre']
        correo = request.form['correo']
        rol = request.form['rol']
        
        if request.form.get('contraseña'):
            contraseña = generate_password_hash(request.form['contraseña'])
            cur.execute("""UPDATE usuarios SET nombre=%s, correo=%s, contraseña=%s, rol=%s
                        WHERE id_usuario=%s""", (nombre, correo, contraseña, rol, id_usuario))
        else:
            cur.execute("UPDATE usuarios SET nombre=%s, correo=%s, rol=%s WHERE id_usuario=%s",
                       (nombre, correo, rol, id_usuario))
        
        mysql.connection.commit()
        cur.close()
        return jsonify({'success': True, 'message': 'Usuario actualizado'})
    
    elif action == 'delete':
        id_usuario = int(request.form['id_usuario'])
        cur.execute("DELETE FROM usuarios WHERE id_usuario = %s", (id_usuario,))
        mysql.connection.commit()
        cur.close()
        return jsonify({'success': True, 'message': 'Usuario eliminado'})
    
    cur.close()
    return jsonify({'success': False, 'message': 'Acción inválida'})

if __name__ == '__main__':

    app.run(debug=True)
