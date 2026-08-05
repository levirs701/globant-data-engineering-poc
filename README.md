# Globant Data Engineering PoC

Proof of Concept (PoC) integral diseñado para resolver el desafío de migración de datos, ingesta en tiempo real bajo múltiples formatos (JSON/CSV), validación estricta, API analítica de alto rendimiento y respaldos en formato binario Apache AVRO.

## 🛠️ Arquitectura y Tecnologías
- **Base de Datos**: Amazon Aurora Serverless v2 (PostgreSQL Compatible). Selección óptima para minimizar costos fijos en reposo (escalado automático a 0.5 ACU) y maximizar la capacidad de cómputo transaccional.
- **Mecanismo de Conectividad**: **Amazon RDS Data API** gestionado mediante `boto3`. Esto elimina la sobrecarga de conexiones TCP de red tradicionales (`psycopg2`/`pg8000`), mitigando problemas de VPC peering y mejorando la seguridad al autenticar mediante roles nativos de AWS IAM (libre de contraseñas expuestas).
- **API Unificada de Ingesta y Analítica**: Desplegada mediante **AWS Lambda (Function URL)** actuando como un enrutador HTTP inteligente para garantizar latencias mínimas y escalabilidad inmediata sin dependencias complejas de API Gateway.
- **Estrategia de Carga Histórica**: Uso exclusivo de la extensión nativa `aws_s3.table_import_from_s3` integrada en Aurora para realizar cargas masivas (*Bulk Loads*) directamente desde archivos CSV en Amazon S3 en milisegundos.
- **Formato de Backup**: Serialización atómica a formato **Apache AVRO** mediante Python nativo y la biblioteca `fastavro`.

### 💡 Decisiones de Diseño Técnico
- **¿Por qué no Apache Spark?** Los datasets iniciales son de escala pequeña (un par de MBs). Levantar un clúster de Spark (vía AWS Glue o EMR) añadiría una sobrecarga operativa masiva e innecesaria, además de un tiempo de arranque inicial de 3 a 5 minutos, elevando costos sin justificación técnica.
- **¿Por qué no Pandas?** Pandas requiere dependencias pesadas compiladas en C (como NumPy), lo que inflaría el paquete de despliegue de AWS Lambda por encima de los 50MB, afectando críticamente los tiempos de arranque en frío (*Cold Starts*). El uso de la **RDS Data API** nativa y manipulaciones de texto nativas mantiene la Lambda ultra liviana, garantizando respuestas en milisegundos.

---

## 🚀 Guía de Ejecución y Orquestación de la API

Para validar todo el ecosistema de manera automática de extremo a extremo, puedes ejecutar el script de orquestación diseñado en PowerShell desde la raíz del proyecto:

```powershell
./run_pipeline.ps1
```

### 📥 1. Endpoints de Ingesta Temporal (Challenge #1 - POST)
Los endpoints aceptan lotes transaccionales de **1 a 1000 registros** e implementan validaciones estrictas del diccionario de datos (campos obligatorios y formato temporal). Los registros inválidos son filtrados, bloqueados y enviados de forma automática a los logs de **Amazon CloudWatch**.

#### Caso A: Ingesta en Formato JSON (Carga registro por registro)
- **Ruta**: `POST /`
- **Cuerpo del Request**:
```json
{
  "table": "hired_employees",
  "rows": [
    {
      "id": 9001,
      "name": "Alan Turing",
      "datetime": "2021-08-01T14:30:00Z",
      "department_id": 1,
      "job_id": 1
    }
  ]
}
```

#### Caso B: Ingesta en Formato CSV (Carga por lotes planos)
- **Ruta**: `POST /?table=[departments|jobs|hired_employees]`
- **Content-Type**: `text/csv; charset=utf-8`
- **Cuerpo del Request**: Texto plano separado por comas enviado directamente en el Body (sin encabezados incluidos, mapeados mediante esquema estático interno).

---

### 📊 2. Endpoints Analíticos de Negocio (Challenge #2 - GET)
Calculados con alto rendimiento utilizando SQL puro directamente en el motor relacional Aurora, aplicando funciones de agregación condicional y expresiones de tabla común (CTE).

- **Ruta 1**: `GET /analytics/quarterly-hiring`
  - **Descripción**: Muestra los empleados contratados por puesto y departamento divididos por cada trimestre del año 2021 ordenados alfabéticamente.
  - **Formato de Respuesta**: JSON Plano tradicional listo para el consumo de BI.

- **Ruta 2**: `GET /analytics/top-departments`
  - **Descripción**: Lista los departamentos que contrataron más empleados que el promedio general en 2021, ordenados descendentemente.

---

## 💾 3. Utilidad de Backup y Restore con Docker
El componente de respaldos AVRO ha sido contenedorizado para ejecutarse en cualquier sistema operativo de forma aislada, montando un volumen local para persistir los binarios en tu máquina.

```bash
# Construir la imagen local
docker build -t globant-data-poc .

# Ejecutar el contenedor (Heredando credenciales de AWS locales)
docker run --rm \
  -e AWS_ACCESS_KEY_ID="TU_AWS_ACCESS_KEY_ID" \
  -e AWS_SECRET_ACCESS_KEY="TU_AWS_SECRET_ACCESS_KEY" \
  -v \$(pwd)/local_backups:/app/backups \
  globant-data-poc
```
*Al finalizar, aparecerá la carpeta local `./local_backups` en tu sistema de archivos con los archivos binarios estructurados de las tres tablas corporativas.*

---

## 🌳 Flujo de Trabajo (Git Workflow)
El proyecto implementa estrictamente la metodología **Feature Branch Workflow**:
- `main`: Código estable y listo para despliegues de producción.
- `develop`: Rama base de integración diaria para pruebas en ambientes controlados.
- `feature/*`: Ramas atómicas de corta duración utilizadas para desarrollar características aisladas antes de someterse a revisiones de código (*Pull Requests*).