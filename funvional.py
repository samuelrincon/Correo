import imaplib
import email
from email.header import decode_header

# ----------------------------------
# CONFIGURACIÓN
# ----------------------------------
USUARIO = "anderson.castaneda@intouchcx.com"
CONTRASENA = "wfhyredeijygwoib"  # Tu App Password sin espacios
DESDE = "26-May-2025"
HASTA = "27-May-2025"  # BEFORE no incluye este día

# Asuntos específicos a buscar
ASUNTOS_OBJETIVO = [
    "Levi's",
    "Short Calls Daily Report - 05/26/2025",
    "Deloitte - Attendance report"
]

# Palabras clave que deben estar dentro del contenido o asunto
PALABRAS_CLAVE = ["affectation", "number", "following"]

# ----------------------------------
# FUNCIONES
# ----------------------------------

def conectar_gmail(usuario, contrasena):
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(usuario, contrasena)
    return mail

def buscar_correos(mail, desde, hasta):
    mail.select('"[Gmail]/All Mail"')
    resultado, datos = mail.search(None, f'(SINCE "{desde}" BEFORE "{hasta}")')
    return datos[0].split()

def obtener_asunto(msg):
    asunto, codificacion = decode_header(msg["Subject"])[0]
    if isinstance(asunto, bytes):
        return asunto.decode(codificacion or "utf-8", errors="ignore")
    return asunto or ""

def contiene_asunto_objetivo(asunto):
    return any(asunto_obj.lower() in asunto.lower() for asunto_obj in ASUNTOS_OBJETIVO)

def contiene_palabra_clave(asunto, cuerpo):
    texto = asunto.lower() + " " + cuerpo.lower()
    return any(palabra in texto for palabra in PALABRAS_CLAVE)

def extraer_cuerpo(mensaje):
    cuerpo = ""
    if mensaje.is_multipart():
        for parte in mensaje.walk():
            tipo = parte.get_content_type()
            if tipo == "text/plain":
                try:
                    cuerpo += parte.get_payload(decode=True).decode(errors="ignore")
                except:
                    pass
    else:
        cuerpo = mensaje.get_payload(decode=True).decode(errors="ignore")
    return cuerpo

# ----------------------------------
# PROGRAMA PRINCIPAL
# ----------------------------------

def main():
    mail = conectar_gmail(USUARIO, CONTRASENA)
    uids = buscar_correos(mail, DESDE, HASTA)

    print(f"\n📬 Correos entre {DESDE} y {HASTA}:\n")

    for uid in uids:
        resultado, datos = mail.fetch(uid, "(RFC822)")
        mensaje = email.message_from_bytes(datos[0][1])
        asunto = obtener_asunto(mensaje)
        cuerpo = extraer_cuerpo(mensaje)

        cumple_asunto = contiene_asunto_objetivo(asunto)
        cumple_palabras = contiene_palabra_clave(asunto, cuerpo)

        estado_asunto = "✅" if cumple_asunto else "❌"
        estado_palabras = "✅" if cumple_palabras else "❌"

        print(f"Asunto: {asunto}")
        print(f" - Coincide con asunto objetivo: {estado_asunto}")
        print(f" - Contiene palabras clave:       {estado_palabras}")
        print("-" * 60)

    mail.logout()

if __name__ == "__main__":
    main()
