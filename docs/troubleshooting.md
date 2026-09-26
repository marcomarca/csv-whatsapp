# Manual de Solución de Problemas — WhatsApp Backup to CSV

Guía para diagnosticar y resolver errores comunes durante la conexión, transferencia y descifrado.

---

## 1. Errores de Conexión y ADB

### `DEVICE_NOT_FOUND`: No se detecta el teléfono
- **Causa**: El cable USB es solo de carga o el puerto USB no está reconociendo el dispositivo.
- **Solución**:
  1. Cambia de cable USB por uno certificado para transferencia de datos.
  2. En la notificación de Android al conectar el USB, selecciona *«Transferencia de archivos (MTP)»*.
  3. Comprueba que el daemon de ADB se ejecuta ejecutando en terminal:
     ```bash
     uv run python -m src.cli devices
     ```

### `DEVICE_UNAUTHORIZED`: El teléfono no está autorizado
- **Causa**: No se ha aceptado el diálogo de huella digital de la clave RSA de depuración USB en la pantalla del móvil.
- **Solución**:
  1. Desbloquea la pantalla de tu móvil.
  2. Acepta el diálogo de autorización que aparece en pantalla.
  3. Si no aparece el diálogo, desconecta y vuelve a conectar el cable USB, o ve a *Opciones de desarrollador* > *Revocar autorizaciones de depuración USB* y reconecta.

### `MULTIPLE_DEVICES`: Múltiples dispositivos detectados
- **Causa**: Hay más de un emulador o teléfono Android conectado simultáneamente.
- **Solución**:
  1. Ejecuta `uv run python -m src.cli devices` para obtener la lista de números de serie.
  2. Especifica el dispositivo deseado mediante el parámetro `--serial <SERIAL>`:
     ```bash
     uv run python -m src.cli export --serial c83eb1a
     ```

---

## 2. Errores de Copia de Seguridad y Cifrado

### `BACKUP_NOT_FOUND`: No se encuentra archivo de backup
- **Causa**: WhatsApp aún no ha generado una copia de seguridad local en la memoria interna (`/sdcard/Android/media/com.whatsapp/WhatsApp/Databases/`).
- **Solución**:
  1. Abre WhatsApp en el móvil.
  2. Ve a **Ajustes** > **Chats** > **Copia de seguridad**.
  3. Pulsa el botón verde **Guardar** (o *Crear copia*) y espera a que la barra de progreso llegue al 100%.

### `INVALID_KEY` / `DECRYPTION_FAILED`: Error al descifrar el backup
- **Causa**: La clave de 64 dígitos introducida no corresponde al backup de esta cuenta o se transcribió erróneamente un carácter.
- **Solución**:
  1. Comprueba que la clave contenga exactamente 64 caracteres hexadecimales (números del 0 al 9 y letras de la 'a' a la 'f').
  2. En WhatsApp, ve a *Copia de seguridad cifrada* y verifica el estado de la clave.
  3. Actualiza la clave guardada en el almacén con:
     ```bash
     uv run python -m src.cli key set "NUEVA_CLAVE_DE_64_CARACTERES"
     ```

### `BACKUP_OUTDATED`: El backup encontrado es antiguo
- **Causa**: La fecha del archivo en el teléfono es anterior a tus mensajes recientes.
- **Solución**:
  1. Abre WhatsApp y pulsa **Guardar** en la sección de Copia de seguridad.
  2. Si deseas exportar de todos modos la copia existente, añade el parámetro `--force`:
     ```bash
     uv run python -m src.cli export --force
     ```

---

## 3. Errores de Archivos y Excel

### Caracteres especiales o emojis no se ven bien en Excel
- **Causa**: Los archivos CSV generados por defecto están codificados en `UTF-8 con BOM (utf-8-sig)` para máxima compatibilidad con Microsoft Excel en Windows.
- **Solución**:
  1. Haz doble clic directamente en `all_messages.csv` para abrirlo en Excel.
  2. Si usas *Obtener datos desde texto/CSV* en Excel, selecciona la codificación `65001: Unicode (UTF-8)`.
