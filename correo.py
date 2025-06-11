import imaplib
import email
from email.header import decode_header
from flask import Flask, render_template_string, request, redirect, url_for, flash, jsonify
from datetime import datetime
import re
import json
import os
from difflib import SequenceMatcher

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Configuración de correo
EMAIL_CONFIG = {
    'usuario': '',
    'contrasena': '',
    'desde': '',
    'hasta': ''
}

# Archivo para guardar las campañas
CAMPAIGNS_FILE = 'campaigns.json'

def load_campaigns():
    if os.path.exists(CAMPAIGNS_FILE):
        with open(CAMPAIGNS_FILE, 'r') as f:
            return json.load(f)
    else:
        default_campaigns = {
            'Frontpoint': [
                "Frontpoint Staff Status EOD",
                "Frontpoint Staff Status intraday",
                "Frontpoint Post mortem"
            ],
            'Cargurus': [
                "CarGurus StaffStatus report",
                "CarGurus StaffStatus report EOD",
                "CarGurus Voice Interval Report",
                "CarGurus Chat/SMS Interval Report"
            ],
            "Levi's": [
                "Short Calls Daily Report",
                "Post Mortem | Levi's | EOD report"
            ],
            'Optavia': [
                "Coach Interval Report | Optavia | Coach SMS, Coach Webchat, Coach Voice",
                "Client Interval Report | Optavia | Client Voice, Client Webchat, Client SMS"
            ],
            'Macmillan': [
                "Attendence | Macmillan | All LoBs"
            ],
            'Mejuri': [
                "WFM - Mejuri | StaffStatus"
            ],
            'Newell': [
                "NB: Service Level",
                "Newell | Post Mortem"
            ],
            'Weber Grills': [
                "Weber Grills | Staff Status Weber Specialty Queues",
                "Weber Grills | Staff Status Weber",
                "Weber Grills | Post-Mortem Report"
            ],
            'Deloitte': [
                "WFM - DELOITTE | Staff Status EOD"
            ],
            'GNC': [
                "WFM GNC Staff Status EOD",
                "WFM-EOD GNC"
            ],
            'AOSmith': [
                "WFM - AOS | Staff Status & SLA - OCC - Ready Time EOD",
                "WFM - AOS | MTD & WTD KPIs Results"
            ]
        }
        save_campaigns(default_campaigns)
        return default_campaigns

def save_campaigns(campaigns):
    with open(CAMPAIGNS_FILE, 'w') as f:
        json.dump(campaigns, f, indent=4)

CAMPANAS_CORREOS = load_campaigns()

def conectar_gmail(usuario, contrasena):
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(usuario, contrasena)
        return mail, None
    except imaplib.IMAP4.error as e:
        return None, f"Error de autenticación IMAP: {str(e)}"
    except Exception as e:
        return None, f"Error inesperado al conectar: {str(e)}"

def convertir_fecha_imap(fecha_str):
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d')
        return fecha.strftime('%d-%b-%Y')
    except ValueError:
        return fecha_str

def buscar_correos(mail, desde, hasta):
    try:
        desde_imap = convertir_fecha_imap(desde)
        hasta_imap = convertir_fecha_imap(hasta)
        
        status, _ = mail.select('"[Gmail]/All Mail"')
        if status != 'OK':
            return [], "No se pudo seleccionar el buzón All Mail"
        
        criterio = f'(SINCE "{desde_imap}" BEFORE "{hasta_imap}")'
        resultado, datos = mail.search(None, criterio)
        if resultado != 'OK':
            return [], f"Error en la búsqueda: {datos[0].decode()}"
        
        uids = datos[0].split()
        return uids, None
    except Exception as e:
        return [], f"Error al buscar correos: {str(e)}"

def obtener_asunto(msg):
    if msg["Subject"] is None:
        return "(Sin asunto)"
    
    asunto, codificacion = decode_header(msg["Subject"])[0]
    if isinstance(asunto, bytes):
        return asunto.decode(codificacion or "utf-8", errors="ignore")
    return asunto or "(Sin asunto)"

def obtener_remitente_completo(msg):
    remitente = msg["From"]
    if remitente is None:
        return "Desconocido <desconocido@desconocido>"
    
    try:
        decoded = decode_header(remitente)
        name_part = email_address_part = ""
        
        for part, encoding in decoded:
            if isinstance(part, bytes):
                part = part.decode(encoding or 'utf-8', errors='ignore')
            
            if '@' in part:
                email_address_part = part
            else:
                name_part = part
        
        if not name_part and not email_address_part:
            match = re.match(r'(.*?)\s*<([^>]+)>', remitente)
            if match:
                name_part, email_address_part = match.groups()
            else:
                email_address_part = remitente
        
        name_part = name_part.strip() if name_part else ""
        email_address_part = email_address_part.strip() if email_address_part else "desconocido@desconocido"
        
        if name_part:
            return f"{name_part} <{email_address_part}>"
        return email_address_part
    
    except Exception:
        return remitente

def normalizar_texto(texto):
    """Normaliza el texto para comparación: minúsculas, sin puntuación y espacios simples"""
    if not texto:
        return ""
    
    # Convertir a minúsculas
    texto = texto.lower()
    
    # Remover signos de puntuación y caracteres especiales
    texto = re.sub(r'[^\w\s]', ' ', texto)
    
    # Reemplazar múltiples espacios con uno solo
    texto = re.sub(r'\s+', ' ', texto).strip()
    
    return texto

def palabras_coincidentes(texto1, texto2):
    """Verifica si todas las palabras de texto2 están presentes en texto1"""
    texto1_normalizado = normalizar_texto(texto1)
    texto2_normalizado = normalizar_texto(texto2)
    
    palabras1 = set(texto1_normalizado.split())
    palabras2 = set(texto2_normalizado.split())
    
    # Verificar que todas las palabras de texto2 estén en texto1
    return palabras2.issubset(palabras1)

def determinar_campana(asunto):
    """Determina a qué campaña pertenece un asunto usando coincidencia flexible de palabras"""
    for campana, asuntos in CAMPANAS_CORREOS.items():
        for asunto_objetivo in asuntos:
            if palabras_coincidentes(asunto, asunto_objetivo):
                return campana, asunto_objetivo
    
    return None, None

def extraer_cuerpo(mensaje):
    cuerpo = ""
    if mensaje.is_multipart():
        for parte in mensaje.walk():
            if parte.get_content_type() in ["text/plain", "text/html"]:
                try:
                    cuerpo += parte.get_payload(decode=True).decode(errors="ignore")
                except:
                    pass
    else:
        cuerpo = mensaje.get_payload(decode=True).decode(errors="ignore")
    return cuerpo

def procesar_correos():
    mail, error = conectar_gmail(EMAIL_CONFIG['usuario'], EMAIL_CONFIG['contrasena'])
    if error:
        return None, error
    
    uids, error = buscar_correos(mail, EMAIL_CONFIG['desde'], EMAIL_CONFIG['hasta'])
    if error:
        mail.logout()
        return None, error
    
    resultados = {
        campana: {
            'enviados': [],
            'no_enviados': list(asuntos),
            'detectados': []
        } 
        for campana, asuntos in CAMPANAS_CORREOS.items()
    }
    
    all_emails = []
    for uid in uids:
        try:
            resultado, datos = mail.fetch(uid, "(RFC822)")
            if resultado != 'OK':
                continue
                
            mensaje = email.message_from_bytes(datos[0][1])
            asunto = obtener_asunto(mensaje)
            remitente = obtener_remitente_completo(mensaje)
            cuerpo = extraer_cuerpo(mensaje)
            fecha = mensaje["Date"]
            
            all_emails.append({
                'uid': uid.decode(),
                'asunto': asunto,
                'remitente': remitente,
                'fecha': fecha,
                'cuerpo': cuerpo[:200] + '...' if len(cuerpo) > 200 else cuerpo
            })
        except Exception as e:
            print(f"Error procesando correo: {str(e)}")
            continue
    
    # Procesamos cada correo con la nueva lógica
    for correo in all_emails:
        campana, asunto_coincidente = determinar_campana(correo['asunto'])
        if campana and asunto_coincidente:
            # Agregar a correos enviados
            resultados[campana]['enviados'].append(correo)
            
            # Remover de no enviados si está presente
            if asunto_coincidente in resultados[campana]['no_enviados']:
                resultados[campana]['no_enviados'].remove(asunto_coincidente)
            
            # Agregar a detectados
            resultados[campana]['detectados'].append({
                'asunto_original': correo['asunto'],
                'asunto_esperado': asunto_coincidente,
                'coincidencia': True
            })
    
    # Verificamos los no detectados
    for campana in resultados:
        for asunto_esperado in CAMPANAS_CORREOS[campana]:
            if asunto_esperado in resultados[campana]['no_enviados']:
                # Buscar correos similares
                similares = []
                for correo in all_emails:
                    if palabras_coincidentes(correo['asunto'], asunto_esperado):
                        similares.append(correo['asunto'])
                
                resultados[campana]['detectados'].append({
                    'asunto_esperado': asunto_esperado,
                    'coincidencia': False,
                    'similares': similares
                })
    
    mail.logout()
    return resultados, None

# Plantillas HTML (mantengo las originales)
LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Email Checker - Login</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f8f9fa; }
        .login-container {
            max-width: 500px;
            margin: 100px auto;
            padding: 30px;
            background-color: white;
            border-radius: 10px;
            box-shadow: 0 0 20px rgba(0,0,0,0.1);
        }
        .logo { text-align: center; margin-bottom: 30px; }
        .form-control:focus {
            border-color: #6610f2;
            box-shadow: 0 0 0 0.25rem rgba(102,16,242,.25);
        }
        .btn-primary {
            background-color: #6610f2;
            border-color: #6610f2;
        }
        .btn-primary:hover {
            background-color: #560bd0;
            border-color: #560bd0;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="login-container">
            <div class="logo">
                <h2>Email Checker</h2>
                <p class="text-muted">Verifica tus correos importantes</p>
            </div>
            
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
                            {{ message }}
                            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                        </div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            
            <form method="POST" action="/">
                <div class="mb-3">
                    <label for="usuario" class="form-label">Correo electrónico</label>
                    <input type="email" class="form-control" id="usuario" name="usuario" required>
                </div>
                <div class="mb-3">
                    <label for="contrasena" class="form-label">Contraseña de aplicación</label>
                    <input type="password" class="form-control" id="contrasena" name="contrasena" required>
                    <div class="form-text">
                        <a href="https://myaccount.google.com/apppasswords" target="_blank">Obtener contraseña de aplicación</a>
                    </div>
                </div>
                <div class="mb-3">
                    <label for="desde" class="form-label">Fecha inicial</label>
                    <input type="date" class="form-control" id="desde" name="desde" required>
                </div>
                <div class="mb-3">
                    <label for="hasta" class="form-label">Fecha final</label>
                    <input type="date" class="form-control" id="hasta" name="hasta" required>
                </div>
                <button type="submit" class="btn btn-primary w-100">Ingresar</button>
            </form>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

PANEL_TEMPLATE = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Panel de Control</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    <style>
        body { background-color: #f8f9fa; }
        .dashboard-header {
            background-color: white;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }
        .card {
            border: none;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: transform 0.3s;
            margin-bottom: 20px;
        }
        .card:hover { transform: translateY(-5px); }
        .date-range {
            background-color: white;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
        }
        .date-form {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        .date-form .form-group {
            margin-bottom: 0;
        }
    </style>
</head>
<body>
    <div class="dashboard-header py-3">
        <div class="container">
            <div class="d-flex justify-content-between align-items-center">
                <h2 class="mb-0">Email Checker</h2>
                <div>
                    <a href="/settings" class="btn btn-outline-primary me-2">
                        <i class="bi bi-gear"></i> Configuración
                    </a>
                    <a href="/logout" class="btn btn-outline-secondary">
                        <i class="bi bi-box-arrow-left"></i> Salir
                    </a>
                </div>
            </div>
        </div>
    </div>
    
    <div class="container">
        <div class="date-range">
            <h5><i class="bi bi-calendar-range"></i> Rango de fechas</h5>
            <form method="POST" action="/update_dates" class="date-form">
                <div class="form-group">
                    <input type="date" class="form-control" name="desde" value="{{ desde }}" required>
                </div>
                <div class="form-group">
                    <input type="date" class="form-control" name="hasta" value="{{ hasta }}" required>
                </div>
                <button type="submit" class="btn btn-primary">Actualizar</button>
            </form>
        </div>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        <div class="d-grid gap-2 mb-4">
            <a href="/correos" class="btn btn-primary btn-lg">
                <i class="bi bi-envelope-check"></i> Ver Todos los Correos
            </a>
        </div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

CORREOS_TEMPLATE = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Correos Recibidos</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    <style>
        body { background-color: #f8f9fa; }
        .email-header {
            background-color: white;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }
        .campaign-section {
            background-color: white;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .campaign-title {
            border-bottom: 2px solid #f0f0f0;
            padding-bottom: 10px;
            margin-bottom: 15px;
        }
        .email-card {
            border-left: 4px solid #4caf50;
            padding: 15px;
            margin-bottom: 10px;
            background-color: #f8f9fa;
            border-radius: 4px;
        }
        .missing-email {
            color: #dc3545;
            padding: 5px 10px;
            background-color: #f8d7da;
            border-radius: 4px;
            margin-bottom: 5px;
            display: inline-block;
        }
        .badge-success {
            background-color: #28a745;
        }
        .badge-danger {
            background-color: #dc3545;
        }
        .email-subject { font-weight: 600; }
        .email-sender { color: #6c757d; }
        .email-date { color: #6c757d; font-size: 0.9rem; }
        .email-preview { color: #495057; }
    </style>
</head>
<body>
    <div class="email-header py-3">
        <div class="container">
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <a href="/panel" class="btn btn-outline-secondary">
                        <i class="bi bi-arrow-left"></i> Volver
                    </a>
                    <h3 class="d-inline-block mb-0">Correos Recibidos y Faltantes</h3>
                </div>
                <div class="text-muted">
                    {{ desde }} - {{ hasta }}
                </div>
            </div>
        </div>
    </div>
    
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        {% for campana, datos in resultados.items() %}
            <div class="campaign-section">
                <div class="d-flex justify-content-between align-items-center campaign-title">
                    <h4>{{ campana }}</h4>
                    <div>
                        <span class="badge badge-success me-2">
                            Recibidos: {{ datos.enviados|length }}
                        </span>
                        <span class="badge badge-danger">
                            Faltantes: {{ datos.no_enviados|length }}
                        </span>
                    </div>
                </div>
                
                <h5 class="mt-4 mb-3">Correos Recibidos:</h5>
                {% if datos.enviados %}
                    {% for correo in datos.enviados %}
                        <div class="email-card">
                            <div class="d-flex justify-content-between align-items-start mb-2">
                                <h5 class="email-subject mb-0">{{ correo.asunto }}</h5>
                                <span class="email-date">{{ correo.fecha }}</span>
                            </div>
                            <div class="mb-2">
                                <span class="email-sender"><i class="bi bi-person"></i> {{ correo.remitente }}</span>
                            </div>
                            <p class="email-preview mb-0">{{ correo.cuerpo }}</p>
                        </div>
                    {% endfor %}
                {% else %}
                    <div class="alert alert-warning">
                        No se recibieron correos de esta campaña.
                    </div>
                {% endif %}
                
                <h5 class="mt-4 mb-3">Correos No Recibidos:</h5>
                {% if datos.no_enviados %}
                    {% for asunto in datos.no_enviados %}
                        <span class="missing-email">
                            <i class="bi bi-exclamation-triangle"></i> {{ asunto }}
                        </span>
                    {% endfor %}
                {% else %}
                    <div class="alert alert-success">
                        <i class="bi bi-check-circle"></i> Todos los correos esperados fueron recibidos.
                    </div>
                {% endif %}
            </div>
        {% endfor %}
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

SETTINGS_TEMPLATE = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Configuración</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    <style>
        body { background-color: #f8f9fa; }
        .settings-header {
            background-color: white;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }
        .campaign-card {
            border: none;
            border-radius: 10px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            margin-bottom: 20px;
            background-color: white;
        }
        .campaign-header {
            background-color: #f8f9fa;
            border-radius: 10px 10px 0 0;
            padding: 15px;
            border-bottom: 1px solid #eee;
        }
        .subject-item {
            padding: 10px 15px;
            border-bottom: 1px solid #eee;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .subject-item:last-child {
            border-bottom: none;
        }
        .add-subject-form {
            padding: 15px;
            background-color: #f8f9fa;
            border-radius: 0 0 10px 10px;
        }
    </style>
</head>
<body>
    <div class="settings-header py-3">
        <div class="container">
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <a href="/panel" class="btn btn-outline-secondary">
                        <i class="bi bi-arrow-left"></i> Volver
                    </a>
                    <h3 class="d-inline-block mb-0 ms-2">Configuración de Campañas</h3>
                </div>
                <button class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#addCampaignModal">
                    <i class="bi bi-plus"></i> Agregar Campaña
                </button>
            </div>
        </div>
    </div>
    
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        {% if not campanias %}
            <div class="alert alert-info">
                No hay campañas configuradas. Agrega tu primera campaña.
            </div>
        {% else %}
            {% for campania, asuntos in campanias.items() %}
                <div class="campaign-card">
                    <div class="campaign-header d-flex justify-content-between align-items-center">
                        <h4 class="mb-0">{{ campania }}</h4>
                        <div>
                            <button class="btn btn-sm btn-outline-primary me-2 edit-campaign-btn" 
                                    data-campania="{{ campania }}">
                                <i class="bi bi-pencil"></i> Editar
                            </button>
                            <button class="btn btn-sm btn-outline-danger delete-campaign-btn" 
                                    data-campania="{{ campania }}">
                                <i class="bi bi-trash"></i> Eliminar
                            </button>
                        </div>
                    </div>
                    
                    <div class="subject-list">
                        {% if not asuntos %}
                            <div class="subject-item text-muted">
                                No hay asuntos configurados para esta campaña
                            </div>
                        {% else %}
                            {% for asunto in asuntos %}
                                <div class="subject-item">
                                    <span>{{ asunto }}</span>
                                    <div>
                                        <button class="btn btn-sm btn-outline-primary me-2 edit-subject-btn" 
                                                data-campania="{{ campania }}" 
                                                data-asunto-original="{{ asunto }}">
                                            <i class="bi bi-pencil"></i>
                                        </button>
                                        <button class="btn btn-sm btn-outline-danger delete-subject-btn" 
                                                data-campania="{{ campania }}" 
                                                data-asunto="{{ asunto }}">
                                            <i class="bi bi-trash"></i>
                                        </button>
                                    </div>
                                </div>
                            {% endfor %}
                        {% endif %}
                    </div>
                    
                    <div class="add-subject-form">
                        <form class="add-subject-form" data-campania="{{ campania }}">
                            <div class="input-group">
                                <input type="text" class="form-control new-subject-input" 
                                       placeholder="Nuevo asunto" required>
                                <button class="btn btn-primary" type="submit">
                                    <i class="bi bi-plus"></i> Agregar
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            {% endfor %}
        {% endif %}
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script>
        $(document).ready(function() {
            $('.add-subject-form').submit(function(e) {
                e.preventDefault();
                const form = $(this);
                const campaignName = form.data('campania');
                const subjectText = form.find('.new-subject-input').val().trim();
                
                if (subjectText) {
                    $.post('/add_subject', { 
                        campania: campaignName, 
                        asunto: subjectText 
                    }, function(response) {
                        if (response.success) {
                            location.reload();
                        } else {
                            alert(response.message || 'Error al agregar asunto');
                        }
                    }).fail(function() {
                        alert('Error de conexión');
                    });
                }
            });
        });
    </script>
</body>
</html>
'''

# Rutas de Flask
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip()
        contrasena = request.form.get('contrasena', '').strip()
        desde = request.form.get('desde', '')
        hasta = request.form.get('hasta', '')
        
        if not all([usuario, contrasena, desde, hasta]):
            flash('Por favor complete todos los campos', 'error')
            return render_template_string(LOGIN_TEMPLATE)
        
        try:
            datetime.strptime(desde, '%Y-%m-%d')
            datetime.strptime(hasta, '%Y-%m-%d')
        except ValueError:
            flash('Formato de fecha incorrecto. Use YYYY-MM-DD', 'error')
            return render_template_string(LOGIN_TEMPLATE)
        
        EMAIL_CONFIG.update({
            'usuario': usuario,
            'contrasena': contrasena,
            'desde': desde,
            'hasta': hasta
        })
        
        return redirect(url_for('panel_control'))
    
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
def logout():
    EMAIL_CONFIG.update({
        'usuario': '',
        'contrasena': '',
        'desde': '',
        'hasta': ''
    })
    return redirect(url_for('index'))

@app.route('/update_dates', methods=['POST'])
def update_dates():
    if not EMAIL_CONFIG['usuario']:
        return redirect(url_for('index'))
    
    desde = request.form.get('desde', '')
    hasta = request.form.get('hasta', '')
    
    try:
        datetime.strptime(desde, '%Y-%m-%d')
        datetime.strptime(hasta, '%Y-%m-%d')
    except ValueError:
        flash('Formato de fecha incorrecto. Use YYYY-MM-DD', 'error')
        return redirect(url_for('panel_control'))
    
    EMAIL_CONFIG.update({
        'desde': desde,
        'hasta': hasta
    })
    
    flash('Fechas actualizadas correctamente', 'success')
    return redirect(url_for('panel_control'))

@app.route('/panel')
def panel_control():
    if not EMAIL_CONFIG['usuario']:
        return redirect(url_for('index'))
    
    return render_template_string(PANEL_TEMPLATE, 
                               desde=EMAIL_CONFIG['desde'], 
                               hasta=EMAIL_CONFIG['hasta'])

@app.route('/correos')
def ver_correos():
    if not EMAIL_CONFIG['usuario']:
        return redirect(url_for('index'))
    
    resultados, error = procesar_correos()
    if error:
        flash(f"Error al procesar correos: {error}", 'error')
        return redirect(url_for('panel_control'))
    
    return render_template_string(CORREOS_TEMPLATE, 
                               resultados=resultados,
                               desde=EMAIL_CONFIG['desde'], 
                               hasta=EMAIL_CONFIG['hasta'])

@app.route('/settings')
def settings():
    if not EMAIL_CONFIG['usuario']:
        return redirect(url_for('index'))
    
    return render_template_string(SETTINGS_TEMPLATE, campanias=CAMPANAS_CORREOS)

@app.route('/add_campaign', methods=['POST'])
def add_campaign():
    if not EMAIL_CONFIG['usuario']:
        return jsonify({'success': False, 'message': 'No autorizado'}), 401
    
    nombre = request.form.get('nombre', '').strip()
    if not nombre:
        return jsonify({'success': False, 'message': 'El nombre de la campaña no puede estar vacío'})
    
    if nombre in CAMPANAS_CORREOS:
        return jsonify({'success': False, 'message': 'Ya existe una campaña con ese nombre'})
    
    CAMPANAS_CORREOS[nombre] = []
    save_campaigns(CAMPANAS_CORREOS)
    
    return jsonify({'success': True})

@app.route('/edit_campaign', methods=['POST'])
def edit_campaign():
    if not EMAIL_CONFIG['usuario']:
        return jsonify({'success': False, 'message': 'No autorizado'}), 401
    
    original_name = request.form.get('original_name', '').strip()
    new_name = request.form.get('new_name', '').strip()
    
    if not original_name or not new_name:
        return jsonify({'success': False, 'message': 'Los nombres no pueden estar vacíos'})
    
    if original_name not in CAMPANAS_CORREOS:
        return jsonify({'success': False, 'message': 'La campaña original no existe'})
    
    if original_name != new_name and new_name in CAMPANAS_CORREOS:
        return jsonify({'success': False, 'message': 'Ya existe una campaña con el nuevo nombre'})
    
    asuntos = CAMPANAS_CORREOS[original_name]
    del CAMPANAS_CORREOS[original_name]
    CAMPANAS_CORREOS[new_name] = asuntos
    save_campaigns(CAMPANAS_CORREOS)
    
    return jsonify({'success': True})

@app.route('/delete_campaign', methods=['POST'])
def delete_campaign():
    if not EMAIL_CONFIG['usuario']:
        return jsonify({'success': False, 'message': 'No autorizado'}), 401
    
    nombre = request.form.get('nombre', '').strip()
    if not nombre:
        return jsonify({'success': False, 'message': 'El nombre de la campaña no puede estar vacío'})
    
    if nombre not in CAMPANAS_CORREOS:
        return jsonify({'success': False, 'message': 'La campaña no existe'})
    
    del CAMPANAS_CORREOS[nombre]
    save_campaigns(CAMPANAS_CORREOS)
    
    return jsonify({'success': True})

@app.route('/add_subject', methods=['POST'])
def add_subject():
    if not EMAIL_CONFIG['usuario']:
        return jsonify({'success': False, 'message': 'No autorizado'}), 401
    
    campania = request.form.get('campania', '').strip()
    asunto = request.form.get('asunto', '').strip()
    
    if not campania or not asunto:
        return jsonify({'success': False, 'message': 'Los campos no pueden estar vacíos'})
    
    if campania not in CAMPANAS_CORREOS:
        return jsonify({'success': False, 'message': 'La campaña no existe'})
    
    if asunto in CAMPANAS_CORREOS[campania]:
        return jsonify({'success': False, 'message': 'El asunto ya existe en esta campaña'})
    
    CAMPANAS_CORREOS[campania].append(asunto)
    save_campaigns(CAMPANAS_CORREOS)
    
    return jsonify({'success': True})

@app.route('/edit_subject', methods=['POST'])
def edit_subject():
    if not EMAIL_CONFIG['usuario']:
        return jsonify({'success': False, 'message': 'No autorizado'}), 401
    
    campania = request.form.get('campania', '').strip()
    asunto_original = request.form.get('asunto_original', '').strip()
    asunto_nuevo = request.form.get('asunto_nuevo', '').strip()
    
    if not campania or not asunto_original or not asunto_nuevo:
        return jsonify({'success': False, 'message': 'Los campos no pueden estar vacíos'})
    
    if campania not in CAMPANAS_CORREOS:
        return jsonify({'success': False, 'message': 'La campaña no existe'})
    
    if asunto_original not in CAMPANAS_CORREOS[campania]:
        return jsonify({'success': False, 'message': 'El asunto original no existe en esta campaña'})
    
    if asunto_original != asunto_nuevo and asunto_nuevo in CAMPANAS_CORREOS[campania]:
        return jsonify({'success': False, 'message': 'El nuevo asunto ya existe en esta campaña'})
    
    index = CAMPANAS_CORREOS[campania].index(asunto_original)
    CAMPANAS_CORREOS[campania][index] = asunto_nuevo
    save_campaigns(CAMPANAS_CORREOS)
    
    return jsonify({'success': True})

@app.route('/delete_subject', methods=['POST'])
def delete_subject():
    if not EMAIL_CONFIG['usuario']:
        return jsonify({'success': False, 'message': 'No autorizado'}), 401
    
    campania = request.form.get('campania', '').strip()
    asunto = request.form.get('asunto', '').strip()
    
    if not campania or not asunto:
        return jsonify({'success': False, 'message': 'Los campos no pueden estar vacíos'})
    
    if campania not in CAMPANAS_CORREOS:
        return jsonify({'success': False, 'message': 'La campaña no existe'})
    
    if asunto not in CAMPANAS_CORREOS[campania]:
        return jsonify({'success': False, 'message': 'El asunto no existe en esta campaña'})
    
    CAMPANAS_CORREOS[campania].remove(asunto)
    save_campaigns(CAMPANAS_CORREOS)
    
    return jsonify({'success': True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
