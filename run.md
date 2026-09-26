# Comandos Frecuentes — WhatsApp Backup to CSV

Guía rápida de comandos para desarrollo, pruebas y ejecución de la aplicación compatible con cualquier fabricante (**Samsung, Xiaomi, Honor, Realme, Oppo, Vivo, Motorola, Pixel**).

---

## 1. Detección Universal de Dispositivos y Cuentas Duales / Multi-OEM

### Listar cuentas de WhatsApp detectadas en el teléfono conectado
```bash
uv run python -m src.cli accounts
```
*Identifica automáticamente:*
- Cuenta estándar (`principal`, User 0) y WhatsApp Business (`business_principal`).
- Samsung One UI Dual Messenger (`samsung_dual`, User 95/96) y Secure Folder (`samsung_secure`, User 150+).
- Xiaomi MIUI/HyperOS Dual Apps (`dual_xiaomi`, User 999 / XSpace).
- Honor / Huawei App Twin (`dual_honor`, User 999/10).
- Realme / Oppo / OnePlus App Cloner (`dual_realme` / `dual_oppo`, User 999).
- Perfiles de trabajo y usuarios secundarios de Android (`user_<uid>`).

---

## 2. Interfaz de Usuario y Ejecución (GUI)

### Iniciar la Interfaz Gráfica
```bash
uv run python -m src.app
```
*O haz doble clic en `scripts\gui.bat`.*
- En la interfaz gráfica, selecciona la cuenta en el menú desplegable.
- Usa el botón **📷 Capturar Clave (OCR)** para capturar la pantalla del teléfono, delimitar el área y extraer la clave de 64 dígitos de forma aislada para la cuenta activa.

---

## 3. Captura y Extracción OCR de la Clave por Cuenta y Dispositivo

### Capturar pantalla por ADB y extraer clave con OCR (CLI)
```bash
# Para la cuenta principal
uv run python -m src.cli capture-key -a principal

# Para Samsung Dual Messenger
uv run python -m src.cli capture-key -a samsung_dual

# Para Xiaomi Dual Apps
uv run python -m src.cli capture-key -a dual_xiaomi

# Especificando número de serie del teléfono
uv run python -m src.cli capture-key -a principal -s <NUMERO_SERIE>
```

---

## 4. Gestión de Claves por Cuenta y Dispositivo (OS Keyring)

### Guardar o consultar la clave de 64 caracteres hex
```bash
# Guardar clave para cuenta principal
uv run python -m src.cli key set "TU_CLAVE_HEXADECIMAL_DE_64_CARACTERES" -a principal

# Guardar clave vinculada a un teléfono específico
uv run python -m src.cli key set "TU_CLAVE_HEXADECIMAL_DE_64_CARACTERES" -a principal -s <NUMERO_SERIE>

# Ver estado de la clave almacenada
uv run python -m src.cli key get -a principal
uv run python -m src.cli key get -a dual_xiaomi

# Eliminar clave guardada
uv run python -m src.cli key clear -a principal
```

---

## 5. Exportación a CSV

### Consultar estado del teléfono, ADB y cuentas
```bash
uv run python -m src.cli status
```

### Ejecutar exportación completa a CSV
```bash
# Exportar cuenta principal
uv run python -m src.cli export -a principal

# Exportar cuenta dual de Xiaomi o Samsung
uv run python -m src.cli export -a dual_xiaomi
uv run python -m src.cli export -a samsung_dual

# Exportación pasando la clave directamente por parámetro
uv run python -m src.cli export -a principal -k "TU_CLAVE_HEXADECIMAL_DE_64_CARACTERES"

# Especificar un dispositivo concreto (si hay varios conectados)
uv run python -m src.cli export --serial <NUMERO_DE_SERIE> -a principal
```

### Consultar historial de exportaciones
```bash
uv run python -m src.cli history
uv run python -m src.cli history -s <NUMERO_DE_SERIE>
```

---

## 6. Calidad y Pruebas

### Ejecutar suite completa de pruebas (pytest)
```bash
uv run pytest
```

---

## 7. Archivos de Salida

Los resultados se guardan de forma aislada y estructurada por dispositivo y cuenta en `data/exports/<device_serial>/<account_id>/`:
- `data/exports/<device_serial>/<account_id>/`:
  - `all_messages.csv`: Todos los mensajes del chat y cuenta.
  - `conversations.csv`: Resumen de conversaciones y métricas.
  - `conversations/`: Archivos CSV individuales por cada chat (`<jid>.csv`).
  - `manifest.json`: Metadatos técnicos, hash SHA-256, serial y conteo de filas.
