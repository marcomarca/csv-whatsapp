# Plan de Arquitectura: Soporte Universal Multi-OEM y Almacenamiento Estructurado por Dispositivo

## 1. Visión General y Objetivos
Este documento define la arquitectura técnica para extender la compatibilidad de extracción, descifrado y exportación de copias de seguridad de WhatsApp a dispositivos Android de cualquier fabricante (**Samsung, Honor, Realme, Xiaomi, Oppo, Vivo, Motorola, Google Pixel, etc.**), así como el almacenamiento estructurado y particionado por **dispositivo de origen** (`device_serial`) y **perfil de cuenta** (`account_id`).

---

## 2. Análisis Técnico de Fabricantes y Espacios Duales (OEMs)

Cada fabricante implementa la clonación de aplicaciones y perfiles seguros utilizando diferentes IDs de usuario en el subsistema multi-usuario de Android:

| Fabricante / Capa | Característica | User ID Android típico | Identificador `UserInfo` en `pm list users` | Ruta remota Databases |
| :--- | :--- | :--- | :--- | :--- |
| **Universal (AOSP)** | Usuario Principal | `0` | `UserInfo{0:Owner/Propietario:...}` | `/storage/emulated/0/Android/media/<pkg>/...` |
| **Xiaomi / POCO / Redmi** (MIUI / HyperOS) | Dual Apps (Aplicaciones Duales) | `999` | `UserInfo{999:XSpace:...}` | `/storage/emulated/999/Android/media/<pkg>/...` |
| **Samsung** (One UI) | Dual Messenger (Mensajería Dual) | `95`, `96` | `UserInfo{95:DualApp:...}` | `/storage/emulated/95/Android/media/<pkg>/...` |
| **Samsung** (Knox) | Secure Folder (Carpeta Segura) | `150`, `151`+ | `UserInfo{150:Secure Folder:...}` | `/storage/emulated/150/Android/media/<pkg>/...` |
| **Honor / Huawei** (MagicOS / EMUI) | App Twin (App Gemela) / PrivateSpace | `999`, `10` | `UserInfo{999:Twin:...}` o `UserInfo{10:...}` | `/storage/emulated/999/Android/media/<pkg>/...` |
| **Realme / Oppo / OnePlus** (ColorOS / RealmeUI / OxygenOS) | App Cloner / Clone Apps | `999` | `UserInfo{999:Clone:...}` | `/storage/emulated/999/Android/media/<pkg>/...` |
| **Vivo / iQOO** (Funtouch OS / OriginOS) | App Clone | `999` | `UserInfo{999:Clone:...}` | `/storage/emulated/999/Android/media/<pkg>/...` |
| **Android Enterprise / Work Profiles** | Perfil de Trabajo / Segundo Usuario | `10`, `11`, `12`... | `UserInfo{10:Work Profile:...}` | `/storage/emulated/10/Android/media/<pkg>/...` |

---

## 3. Estrategia de Descubrimiento Dinámico Universal

En lugar de listas rígidas de fabricantes o IDs fijos, el algoritmo de descubrimiento implementa un enfoque de tres capas:

1. **Inspección de Hardware y OEM (`ro.product.*`)**:
   - Fabricante: `ro.product.manufacturer` (ej. `samsung`, `xiaomi`, `HONOR`, `realme`, `oppo`, `vivo`, `motorola`, `Google`).
   - Marca y Modelo: `ro.product.brand`, `ro.product.model`.
2. **Descubrimiento de Usuarios Android Dinámico**:
   - Consulta `pm list users` parseando todos los bloques `UserInfo{(\d+):([^:]*):([0-9a-fA-F]*)}`.
   - Escaneo de respaldo en sistema de archivos: `ls -d /storage/emulated/*/` para detectar carpetas de usuarios activas incluso si `pm list users` tuviera restricciones de permisos.
   - Mapeo de IDs comunes conocidos: `0`, `95`, `96`, `150`, `999`, `10`, `11`, `12`.
3. **Mapeo Inteligente de Nombres y `account_id`**:
   - `principal`: Cuenta estándar en User 0 (`com.whatsapp`).
   - `business_principal`: WhatsApp Business en User 0 (`com.whatsapp.w4b`).
   - `samsung_dual` / `samsung_secure`: Cuentas en Samsung Dual Messenger o Secure Folder.
   - `dual_xiaomi` / `dual_honor` / `dual_realme` / `dual_oppo` / `dual_vivo`: Cuentas clonadas según el fabricante detectado o etiqueta de usuario.
   - `dual_user_<uid>`: Fallback universal para cualquier perfil secundario o de trabajo de Android.

---

## 4. Estructura de Almacenamiento Particionada por Dispositivo

Para garantizar que múltiples dispositivos no colisionen al procesarse en la misma máquina:

### 4.1 Almacén Seguro de Claves (OS Keyring)
- Las claves se indexan con la clave compuesta:
  `whatsapp_key_<serial>_<account_id>` con fallback a `whatsapp_key_<account_id>` y `whatsapp_key_default`.

### 4.2 Base de Datos SQLite Unificada (`data/working/vault.db`)
- Columnas de partición compuestas en todas las tablas (`messages`, `conversations`, `export_runs`, `export_manifests`):
  - `device_serial TEXT DEFAULT ''`
  - `account_id TEXT DEFAULT 'principal'`
- Índices de rendimiento:
  - `CREATE INDEX IF NOT EXISTS idx_messages_dev_acc ON messages(device_serial, account_id, jid_raw, timestamp_ms);`
  - `CREATE INDEX IF NOT EXISTS idx_conv_dev_acc ON conversations(device_serial, account_id, jid_raw);`

### 4.3 Jerarquía de Archivos de Exportación CSV
- Directorios organizados por número de serie del dispositivo y cuenta:
  ```
  data/exports/
  └── <device_serial>/              (ej. c83eb1a / R58M123456)
      ├── principal/
      │   ├── all_messages.csv
      │   ├── conversations.csv
      │   ├── conversations/*.csv
      │   └── manifest.json
      ├── dual_xiaomi/ (o samsung_dual, etc.)
      │   ├── all_messages.csv
      │   ├── conversations.csv
      │   ├── conversations/*.csv
      │   └── manifest.json
      └── business_principal/
          └── ...
  ```

---

## 5. Matriz de Pruebas Unitarias e Integración
1. Pruebas de emulación para Samsung Dual Messenger (User 95).
2. Pruebas de emulación para Samsung Secure Folder (User 150).
3. Pruebas de emulación para Honor / Realme / Oppo (User 999).
4. Pruebas de aislamiento en base de datos verificando particionamiento por `(device_serial, account_id)`.
5. Pruebas de rutas de exportación organizadas por dispositivo.
