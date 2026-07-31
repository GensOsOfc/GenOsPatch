# 🧩 GenOs Patch Engine

**GenOs Patch Engine** es una herramienta en Python para automatizar modificaciones sobre APK Android mediante parches empaquetados en archivos ZIP.

El usuario no necesita editar manualmente toda la aplicación descompilada. El motor recibe una APK y un parche, interpreta las instrucciones de `patch.txt`, agrega archivos, ejecuta búsquedas y reemplazos —incluyendo expresiones regulares— y recompila el proyecto.

> ⚠️ Utiliza esta herramienta únicamente sobre APK propias o aplicaciones que tengas autorización para modificar.

---

## 🧱 Componentes del proyecto

El proyecto se divide en dos partes:

```text
GenOsPatch/
├── gndev_patcher.py     # Motor que procesa la APK
├── GenOsPatch.zip       # Parche con instrucciones y archivos
└── Aplicacion.apk       # APK de entrada, cuando se usa una copia local
```

### 🐍 `gndev_patcher.py`

Es el motor principal. Se encarga de validar la APK, abrir el parche, descompilar, modificar, recompilar y generar un reporte.

### 📦 `GenOsPatch.zip`

Es el paquete del parche. Contiene:

- 📄 `patch.txt`, con los metadatos y operaciones.
- 🎨 Recursos Android dentro de `res/`.
- 🧬 Clases o modificaciones Smali dentro de `smali/`.
- 📂 Otros archivos que el autor del parche quiera copiar o extraer.

---

# 🧰 Requisitos para ejecutar el motor

## 🛠️ Herramientas obligatorias

| Herramienta | Función dentro del proyecto |
|---|---|
| **Python 3** | Ejecuta `gndev_patcher.py`. |
| **Java** | Permite que Apktool funcione. |
| **Apktool** | Descompila y recompila la APK. |
| **cURL** | Descarga APK desde una URL y se utiliza en el modo de descarga oficial. |
| **APK Android** | Archivo que será procesado. |
| **Parche ZIP** | Contiene `patch.txt` y los archivos del parche. |

El motor comprueba antes de iniciar que los comandos `java`, `apktool` y `curl` estén disponibles en el `PATH` del sistema.

Comprueba tu instalación con:

```bash
python3 --version
java -version
apktool --version
curl --version
```

En Windows, Python también puede ejecutarse como:

```powershell
python --version
```

## 🔎 Herramientas opcionales para crear Regex

Estas herramientas **no son necesarias para ejecutar el motor**, pero facilitan la creación y prueba de las reglas:

| Herramienta | Uso recomendado |
|---|---|
| **Regex101** | Probar expresiones regulares usando el modo Python. |
| **Visual Studio Code** | Buscar patrones en carpetas completas y editar XML, Smali y `patch.txt`. |
| **Notepad++** | Realizar búsquedas y reemplazos Regex en Windows. |
| **ripgrep (`rg`)** | Buscar patrones rápidamente desde la terminal. |
| **grep** | Alternativa de búsqueda disponible en Linux. |
| **JADX** | Analizar el código de una APK y localizar métodos o referencias antes de crear una regla. |
| **MT Manager** | Revisar APK, XML y Smali desde Android. |

GenOs Patch usa el módulo `re` incluido en Python. No requiere instalar una librería Regex adicional mediante `pip`.

## 🔐 Herramientas opcionales para el APK final

El APK recompilado queda sin firmar. Para instalarlo normalmente se pueden usar:

- `zipalign`, para alinear el APK.
- `apksigner`, para firmarlo.
- `keytool`, para crear una clave de firma.
- `adb`, para instalarlo y probarlo desde el computador.

---

# 📦 Estructura de un parche

Un parche puede organizarse de esta manera:

```text
GenOsPatch.zip
├── patch.txt
├── res/
│   ├── drawable/
│   │   └── genos_example_background.xml
│   └── values/
│       └── genos_example.xml
└── smali/
    └── com/
        └── genos/
            └── example/
                └── GenOsExample.smali
```

## 📄 `patch.txt`

Es el manifiesto principal. El motor lo busca dentro del ZIP, lo interpreta y ejecuta sus operaciones en el orden en que aparecen.

Debe estar codificado en **UTF-8** y solo debe existir un `patch.txt` dentro del paquete.

## 🎨 `res/`

Contiene recursos Android que pueden copiarse al proyecto descompilado, por ejemplo:

- Colores.
- Textos.
- Drawables XML.
- Imágenes.
- Layouts.
- Menús.
- Archivos dentro de `values/`.

## 🧬 `smali/`

Contiene clases Smali que serán agregadas al proyecto. La ruta de carpetas debe corresponder con el nombre interno de la clase.

Ejemplo:

```text
smali/com/genos/example/GenOsExample.smali
```

Clase interna:

```smali
.class public Lcom/genos/example/GenOsExample;
```

---

# 🧪 Ejemplo completo de `patch.txt`

```ini
[PATCH_NAME]
GenOs Patch - Ejemplo Regex

[PATCH_VERSION]
1.0.0

[MIN_ENGINE_VER]
3

[AUTHOR]
GeniousMods | GnDev

[SCRIPT_AUTHOR]
GeniousMods | GnDev

[YOUTUBE_CHANNEL]
https://www.youtube.com/@GeniousMods

[DESCRIPTION]
Parche de ejemplo para agregar recursos y clases Smali.
También modifica contenido XML y Smali mediante Regex.

[PACKAGE]
*

[ADD_FILES]
NAME: Agregar recursos XML
SOURCE: res
TARGET: res
EXTRACT: false
OVERWRITE: true
[/ADD_FILES]

[ADD_FILES]
NAME: Agregar clases Smali
SOURCE: smali
TARGET: AUTO_SMALI
EXTRACT: false
OVERWRITE: true
[/ADD_FILES]

[MATCH_REPLACE]
NAME: Cambiar color mediante Regex
TARGET: res/values/genos_example.xml
REGEX: true
IGNORE_CASE: true
REQUIRED: true
MIN_MATCHES: 1
MAX_MATCHES: 1
MATCH: (<color\s+name="genos_example_primary">)#[0-9a-f]{6}(</color>)
REPLACE: \g<1>#2F80FF\g<2>
[/MATCH_REPLACE]

[MATCH_REPLACE]
NAME: Cambiar mensaje Smali mediante Regex
TARGET: com/genos/example/GenOsExample.smali
REGEX: true
REQUIRED: true
MIN_MATCHES: 1
MAX_MATCHES: 1
MATCH: const-string\s+(v\d+),\s*"GenOs Example"
REPLACE: const-string \g<1>, "GenOs Patch funcionando"
[/MATCH_REPLACE]
```

---

# 🏷️ Metadatos disponibles

| Bloque | Función |
|---|---|
| `[PATCH_NAME]` | Nombre visible del parche. |
| `[PATCH_VERSION]` | Versión del parche. |
| `[MIN_ENGINE_VER]` | Versión mínima del motor necesaria. |
| `[AUTHOR]` | Autor del parche. |
| `[SCRIPT_AUTHOR]` | Autor que se muestra en el banner del motor. |
| `[YOUTUBE_CHANNEL]` | Canal mostrado en el banner. |
| `[DESCRIPTION]` | Descripción del parche. |
| `[PACKAGE]` | Paquete permitido. `*` acepta cualquier paquete. |

`[PACKAGE]` también admite una o varias reglas separadas por líneas, comas o punto y coma. El motor compara esas reglas con el paquete detectado en `AndroidManifest.xml`.

Ejemplo restringido:

```ini
[PACKAGE]
com.ejemplo.app
```

Ejemplo con patrón:

```ini
[PACKAGE]
com.ejemplo.*
```

---

# ⚙️ Operaciones compatibles

La versión actual del motor reconoce dos tipos de operaciones:

1. `[ADD_FILES]`
2. `[MATCH_REPLACE]`

## ➕ 1. `ADD_FILES`

Copia archivos o carpetas desde el ZIP del parche hacia el proyecto descompilado.

```ini
[ADD_FILES]
NAME: Agregar recursos
SOURCE: res
TARGET: res
EXTRACT: false
OVERWRITE: true
[/ADD_FILES]
```

### 🧾 Campos de `ADD_FILES`

| Campo | Función |
|---|---|
| `NAME` | Nombre que se muestra durante la ejecución. |
| `SOURCE` | Archivo o carpeta ubicada dentro del parche. |
| `TARGET` | Ruta de destino dentro del proyecto descompilado. |
| `EXTRACT` | Si es `true`, `SOURCE` debe ser un ZIP y será extraído. |
| `OVERWRITE` | Permite reemplazar archivos existentes. |

### 🎯 Destinos especiales

```ini
TARGET: /
```

Apunta a la raíz del proyecto descompilado.

```ini
TARGET: AUTO_SMALI
```

Apunta a la carpeta `smali/` del proyecto y la crea cuando no existe.

### 📂 Extraer un ZIP interno

```ini
[ADD_FILES]
NAME: Extraer archivos del parche
SOURCE: archivos.zip
TARGET: /
EXTRACT: true
OVERWRITE: true
[/ADD_FILES]
```

El motor valida las rutas internas del ZIP para impedir que un archivo se extraiga fuera de la carpeta de destino.

---

## 🔁 2. `MATCH_REPLACE`

Busca contenido dentro de uno o varios archivos y lo reemplaza.

Puede trabajar con texto exacto o con expresiones regulares.

```ini
[MATCH_REPLACE]
NAME: Cambiar texto
TARGET: res/values/strings.xml
REGEX: false
MATCH: Texto original
REPLACE: Texto modificado
[/MATCH_REPLACE]
```

### 🧾 Campos de `MATCH_REPLACE`

| Campo | Función |
|---|---|
| `NAME` | Nombre de la operación. |
| `TARGET` | Archivo o patrón de archivos donde se buscará. |
| `REGEX` | Activa expresiones regulares. |
| `MATCH` | Texto o patrón que se buscará. |
| `REPLACE` | Contenido que sustituirá la coincidencia. |
| `IGNORE_CASE` | Ignora mayúsculas y minúsculas. |
| `DOTALL` | Permite que `.` abarque saltos de línea. |
| `REQUIRED` | Detiene el proceso si no encuentra coincidencias. |
| `MIN_MATCHES` | Número mínimo de coincidencias permitido. |
| `MAX_MATCHES` | Número máximo de coincidencias permitido. |

Cuando `REGEX: true`, el motor usa la sintaxis de expresiones regulares de Python y activa `MULTILINE`. También puede activar `DOTALL` e `IGNORE_CASE` según la regla.

---

# 🧠 Cómo funcionan las capturas Regex

## 🧾 Capturar etiquetas XML

```regex
(<color\s+name="genos_example_primary">)#[0-9a-f]{6}(</color>)
```

La expresión crea dos grupos:

- Grupo 1: etiqueta de apertura.
- Grupo 2: etiqueta de cierre.

Reemplazo:

```text
\g<1>#2F80FF\g<2>
```

Resultado:

```xml
<color name="genos_example_primary">#2F80FF</color>
```

## 🧩 Capturar un registro Smali

```regex
const-string\s+(v\d+),\s*"GenOs Example"
```

El grupo `(v\d+)` puede capturar registros como:

```text
v0
v1
v2
v15
```

Reemplazo:

```text
const-string \g<1>, "GenOs Patch funcionando"
```

De esta manera se conserva automáticamente el registro encontrado y no se depende de un registro fijo.

## ✅ Recomendaciones al crear reglas

- Prueba la expresión en modo **Python**.
- Evita patrones demasiado generales.
- Usa `REQUIRED: true` cuando la modificación sea indispensable.
- Usa `MIN_MATCHES` y `MAX_MATCHES` para controlar la cantidad esperada.
- Captura únicamente la parte que deba conservarse.
- Prueba primero sobre una copia de la APK.
- Usa `--no-build` para revisar el proyecto modificado antes de recompilar.

---

# 🎯 Patrones `TARGET` compatibles

## 🔍 Buscar recursos

```ini
TARGET: res/**/*.xml
```

Busca archivos XML dentro de `res/` de forma recursiva.

## 🗂️ Buscar todos los Smali

```ini
TARGET: *.smali
```

Busca recursivamente en `smali/` y en carpetas multidex como `smali_classes2/`, `smali_classes3/` y superiores.

## 🧭 Buscar una ruta Smali en todas las DEX

```ini
TARGET: com/genos/example/GenOsExample.smali
```

El motor intenta esa ruta dentro de todas las carpetas Smali detectadas.

## 🧵 Patrón multidex explícito

```ini
TARGET: smali*/**/*.smali
```

Busca de forma explícita dentro de todas las carpetas Smali.

---

# 🐍 Funciones principales del motor Python

## 🌐 Descarga y entrada de APK

| Función | Responsabilidad |
|---|---|
| `resolve_official_whatsapp_apk_url()` | Localiza el enlace directo vigente del APK desde la página oficial configurada. |
| `download_file()` | Descarga una APK desde una URL personalizada, maneja cookies, redirecciones y validaciones básicas. |
| `download_official_whatsapp_apk()` | Descarga el APK oficial utilizando cURL. |
| `validate_apk()` | Verifica que el archivo sea un ZIP válido y contenga `AndroidManifest.xml`. |

## 🔒 Integridad y hashes

| Función | Responsabilidad |
|---|---|
| `hash_file()` | Calcula un hash usando el algoritmo indicado. |
| `md5_file()` | Calcula MD5 para identificación. |
| `sha256_file()` | Calcula SHA-256 para integridad. |
| `inspect_apk_hashes()` | Analiza el APK y los archivos `classes*.dex`. |
| `hash_zip_entry()` | Calcula MD5, SHA-256 y CRC32 de cada DEX. |
| `display_apk_hashes()` | Muestra los resultados en la consola. |

## 🛡️ Lectura y seguridad del parche

| Función | Responsabilidad |
|---|---|
| `safe_destination()` | Impide rutas absolutas o salidas con `..` dentro del ZIP. |
| `safe_extract_zip()` | Extrae archivos de forma controlada. |
| `parse_fields()` | Lee los campos de cada operación. |
| `parse_manifest()` | Interpreta metadatos y bloques de `patch.txt`. |
| `read_patch_manifest_from_zip()` | Lee `patch.txt` directamente desde el ZIP. |
| `find_manifest()` | Localiza el manifiesto después de extraer el parche. |
| `validate_package()` | Comprueba que el parche sea compatible con el paquete detectado. |

## 🧩 Aplicación del parche

| Función | Responsabilidad |
|---|---|
| `resolve_project_target()` | Convierte `TARGET` en una ruta segura dentro del proyecto. |
| `apply_add_files()` | Copia carpetas, archivos o extrae ZIP internos. |
| `find_target_files()` | Localiza archivos XML, Smali y rutas multidex. |
| `apply_match_replace()` | Ejecuta búsquedas y reemplazos exactos o Regex. |
| `remove_all_line_directives()` | Elimina directivas `.line` de los archivos Smali. |

## ⚙️ Ejecución general

| Función | Responsabilidad |
|---|---|
| `require_command()` | Comprueba que una herramienta esté instalada. |
| `run_command()` | Ejecuta comandos externos y muestra su salida. |
| `display_engine_banner()` | Muestra el banner del motor y los datos del parche. |
| `display_patch_info()` | Muestra nombre, versión, autor, paquete y descripción. |
| `main()` | Coordina todo el proceso de principio a fin. |

---

# 🚀 Flujo de ejecución

El motor realiza siete etapas:

```text
1. Preparar o descargar la APK
            ↓
2. Abrir y validar el parche ZIP
            ↓
3. Descompilar la APK con Apktool
            ↓
4. Eliminar directivas .line, salvo que se use --keep-lines
            ↓
5. Ejecutar ADD_FILES y MATCH_REPLACE
            ↓
6. Guardar patch-report.json
            ↓
7. Recompilar y calcular los hashes del APK resultante
```

Durante el proceso también:

- Detecta el nombre del paquete.
- Comprueba la versión mínima del motor.
- Registra cada operación aplicada.
- Cuenta archivos modificados y coincidencias.
- Rechaza reglas `REQUIRED` que no encuentren resultados.
- Elimina la carpeta descompilada después de una compilación exitosa.

---

# ▶️ Formas de ejecución

## 💻 Usar una APK local

```bash
python3 gndev_patcher.py \
  --apk MiAplicacion.apk \
  --patch GenOsPatch.zip \
  --output MiAplicacion-patched-unsigned.apk
```

En Windows:

```powershell
python gndev_patcher.py --apk MiAplicacion.apk --patch GenOsPatch.zip --output MiAplicacion-patched-unsigned.apk
```

## 🌐 Usar una URL directa

```bash
python3 gndev_patcher.py \
  --apk-url "https://servidor.com/aplicacion.apk" \
  --patch GenOsPatch.zip
```

## ⚡ Modo predeterminado

```bash
python3 gndev_patcher.py
```

Cuando no se indica `--apk` ni `--apk-url`, el motor usa el modo de descarga oficial configurado y busca `GenOsPatch.zip` en la carpeta actual.

## 🧪 Aplicar sin recompilar

```bash
python3 gndev_patcher.py \
  --apk MiAplicacion.apk \
  --patch GenOsPatch.zip \
  --no-build
```

Este modo permite revisar el contenido modificado dentro de la carpeta de trabajo.

---

# 🎛️ Parámetros disponibles

| Parámetro | Función |
|---|---|
| `--apk RUTA` | Usa una APK local. |
| `--apk-url URL` | Descarga una APK desde una URL directa. |
| `--official-whatsapp` | Selecciona explícitamente el modo oficial configurado. |
| `--patch RUTA` | Selecciona el parche ZIP. Por defecto: `GenOsPatch.zip`. |
| `--output RUTA` | Define el APK de salida. |
| `--workdir RUTA` | Define la carpeta de trabajo. Por defecto: `build`. |
| `--keep-lines` | Conserva las directivas `.line`. |
| `--keep-workdir` | Solicita conservar la carpeta de trabajo. |
| `--no-build` | Aplica el parche sin recompilar. |
| `--keep-decoded` | Se mantiene por compatibilidad, pero la versión actual lo ignora después de compilar. |

`--apk`, `--apk-url` y `--official-whatsapp` son opciones mutuamente excluyentes.

---

# 📁 Archivos generados

Después de una ejecución normal se obtiene:

```text
MiAplicacion-patched-unsigned.apk
build/
├── input/
├── patch/
└── patch-report.json
```

El reporte contiene, entre otros datos:

- Versión del motor.
- Fecha de inicio y finalización.
- Fuente de la APK.
- MD5 y SHA-256 de entrada.
- Información de cada `classes*.dex`.
- Paquete detectado.
- Metadatos del parche.
- Cantidad de coincidencias.
- Archivos modificados.
- APK de salida y hashes finales.

> 🔐 El APK generado está recompilado, pero permanece **sin firmar**.

---

# ✨ Resumen

GenOs Patch Engine permite crear parches reutilizables sin modificar manualmente cada APK desde cero.

El usuario prepara un ZIP con su estructura, define las operaciones en `patch.txt` y el motor se encarga de:

```text
leer → validar → descompilar → agregar → buscar → reemplazar → reportar → recompilar
```

La base actual está diseñada para crecer agregando nuevas reglas, recursos y clases dentro de futuros parches.

---

## 👨‍💻 Créditos

**GeniousMods | GnDev**

- GitHub: `https://github.com/GensOsOfc`
- YouTube: `https://www.youtube.com/@GeniousMods`

> 💡 Si puedes soñarlo, puedes programarlo.
