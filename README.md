# Globant Data Engineering PoC

Proof of Concept (PoC) integral diseñado para resolver el desafío de migración de datos, ingesta en tiempo real, validación estricta y respaldos en formato binario Apache AVRO.

## 🛠️ Arquitectura y Tecnologías
- **Base de Datos**: Amazon Aurora Serverless v2 (PostgreSQL Compatible). Selección óptima para minimizar costos fijos en reposo (escalado automático a 0.5 ACU) y maximizar la capacidad de cómputo transaccional.
- **Estrategia de Carga Histórica**: Uso exclusivo de la extensión nativa `aws_s3.table_import_from_s3` integrada en Aurora para realizar cargas masivas (*Bulk Loads*) directamente desde archivos CSV en Amazon S3 en milisegundos, evitando procesamientos costosos fila por fila.
- **API de Ingesta Temporal**: Desplegada mediante **AWS Lambda (Function URL)** para garantizar latencias mínimas y escalabilidad inmediata sin dependencias complejas de API Gateway.
- **Formato de Backup**: Serialización atómica a formato **Apache AVRO** mediante Python nativo y la biblioteca `fastavro`.

### 💡 Decisiones de Diseño Técnico
- **¿Por qué no Apache Spark?** Los datasets iniciales son de escala pequeña (un par de MBs). Levantar un clúster de Spark (vía AWS Glue o EMR) añadiría una sobrecarga operativa masiva e innecesaria, además de un tiempo de arranque inicial de 3 a 5 minutos, elevando costos sin justificación técnica.
- **¿Por qué no Pandas?** Pandas requiere dependencias pesadas compiladas en C (como NumPy), lo que inflaría el paquete de despliegue de AWS Lambda por encima de los 50MB, afectando críticamente los tiempos de arranque en frío (*Cold Starts*). El uso de `dataclasses` nativos de Python mantiene la Lambda por debajo de los 10KB, garantizando respuestas en milisegundos.

---

## 🚀 Guía de Ejecución Local y Docker

### 📦 1. Ejecutar Utilidad de Backup y Restore con Docker
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

### 📥 2. Estructura de Peticiones para la API REST
El endpoint genérico acepta lotes transaccionales de **1 a 1000 registros** e implementa validaciones estrictas del diccionario de datos (campos obligatorios y formato ISO 8601). Los registros inválidos son filtrados, bloqueados y enviados de forma automática a los logs de **Amazon CloudWatch**.

#### Ejemplo de Carga Mixta (POST Request):
```json
{
  "table": "hired_employees",
  "rows": [
    {
      "id": 9001,
      "name": "Alan Turing",
      "datetime": "2026-08-01T14:30:00Z",
      "department_id": 1,
      "job_id": 1
    },
    {
      "id": 9002,
      "name": "Ada Lovelace",
      "datetime": "2026/08/01 14:30:00", 
      "department_id": 1,
      "job_id": 2
    }
  ]
}
```

---

## 🌳 Flujo de Trabajo (Git Workflow)
El proyecto implementa estrictamente la metodología **Feature Branch Workflow**:
- `main`: Código estable y listo para despliegues de producción.
- `develop`: Rama base de integración diaria para pruebas en ambientes controlados.
- `feature/*`: Ramas atómicas de corta duración utilizadas para desarrollar características aisladas antes de someterse a revisiones de código (*Pull Requests*).
