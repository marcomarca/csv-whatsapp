# Documentación de Seguridad y Privacidad

WhatsApp Backup to CSV procesa comunicaciones privadas y metadatos personales. Esta arquitectura implementa medidas de seguridad estrictas:

---

## 1. Principios de Seguridad Fundamentales

1. **Ejecución 100% Local (Air-gapped ready)**:
   - Todo el procesamiento, descifrado, análisis de SQLite y exportación a CSV ocurre exclusivamente en el ordenador local.
   - No se envían datos, metadatos, identificadores ni textos de conversaciones a servicios en la nube, servidores de terceros ni APIs de inteligencia artificial.

2. **Sin Root ni Modificaciones del Teléfono**:
   - No se requiere rootear el dispositivo ni desbloquear el bootloader.
   - El sistema opera únicamente mediante los canales estándar de depuración USB de Android (ADB) sobre la partición accesible de almacenamiento `/sdcard/`.
   - La aplicación nunca modifica ni elimina los archivos originales presentes en el teléfono móvil.

3. **Custodia Segura de Secretos**:
   - La clave de descifrado de 64 caracteres se almacena únicamente en el almacén de credenciales del sistema operativo del usuario mediante la librería `keyring` (Windows Credential Manager / macOS Keychain / Linux SecretService).
   - Las claves nunca se guardan en texto plano en archivos de configuración ni en el repositorio.
   - Las claves nunca se imprimen ni se registran en archivos de logs.

4. **Prevención de Fugas en Control de Versiones (Git Guardrails)**:
   - El archivo `.gitignore` excluye obligatoriamente:
     - Archivos de clave (`*.key`, `*.secret`).
     - Backups cifrados y bases de datos (`*.crypt*`, `*.db`, `*.sqlite*`).
     - Archivos de exportación (`*.csv`, `data/exports/`).
     - Directorios de trabajo y multimedia privada (`data/working/`, `data/backups/`, `data/media/`).

5. **Protección Contra Inyección de Fórmulas CSV**:
   - Para prevenir ataques de inyección de fórmulas CSV (CSV / Spreadsheet Injection) al abrir los archivos exportados en hojas de cálculo como Microsoft Excel o LibreOffice Calc, cualquier celda que comience por caracteres de fórmula (`=`, `+`, `-`, `@`, `\t`, `\r`) es prefijada automáticamente con una comilla simple (`'`), desactivando su ejecución automática.

6. **Operaciones Atómicas de Escritura**:
   - Todas las escrituras de bases de datos y archivos CSV se realizan escribiendo en archivos temporales con comprobación de integridad y reemplazo atómico, evitando estados intermedios corruptos si se interrumpe la energía o el proceso.
