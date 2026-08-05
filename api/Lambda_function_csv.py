import json
import boto3
import csv
import io
import logging
from datetime import datetime
from analytics import query_quarterly_hiring, query_top_departments,parse_data_api_response

# Configurar el logger oficial de AWS Lambda
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Inicializar cliente de RDS Data API
rds_client = boto3.client('rds-data')

# CONFIGURACIÓN DE TU BASE DE DATOS
CLUSTER_ARN = "arn:aws:rds:us-east-2:124194989357:cluster:database-1"
SECRET_ARN = "arn:aws:secretsmanager:us-east-2:124194989357:secret:rds-db-credentials/cluster-V3BH6DFRLDTHEXYUAPKPDTSFKU/postgres/1785528158439-aDho7M"
DATABASE_NAME = "postgres"

# Definición explícita de las cabeceras requeridas para cada tabla según el modelo de Globant
TABLE_HEADERS = {
    "hired_employees": ["id", "name", "datetime", "department_id", "job_id"],
    "departments": ["id", "department"],
    "jobs": ["id", "job"]
}

def validate_iso_8601(date_string: str) -> bool:
    """Verifica si una cadena cumple con el formato estricto ISO 8601."""
    if not date_string or date_string.strip() == "":
        return True # Aceptamos vacío si el campo en la tabla permite nulos
    formats = ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"]
    for fmt in formats:
        try:
            datetime.strptime(date_string, fmt)
            return True
        except ValueError:
            continue
    return False

def clean_and_validate_row(row: dict, table: str) -> tuple[bool, str, dict]:
    """Valida los campos obligatorios del diccionario de datos."""
    try:
        cleaned = {}
        
        if table == "hired_employees":
            if not row.get("id") or not row.get("name") or row["name"].strip() == "":
                return False, "Missing required fields 'id' or 'name'", {}
            
            cleaned["id"] = int(row["id"])
            cleaned["name"] = str(row["name"]).strip()
            
            dt_val = row.get("datetime", "").strip()
            if dt_val == "":
                cleaned["datetime"] = None
            else:
                if not validate_iso_8601(dt_val):
                    return False, f"Invalid ISO 8601 datetime: '{dt_val}'", {}
                cleaned["datetime"] = dt_val
                
            dept_val = row.get("department_id", "").strip()
            cleaned["department_id"] = int(dept_val) if dept_val != "" else None
            
            job_val = row.get("job_id", "").strip()
            cleaned["job_id"] = int(job_val) if job_val != "" else None

        elif table == "departments":
            if not row.get("id") or not row.get("department") or row["department"].strip() == "":
                return False, "Missing fields 'id' or 'department'", {}
            cleaned["id"] = int(row["id"])
            cleaned["department"] = str(row["department"]).strip()

        elif table == "jobs":
            if not row.get("id") or not row.get("job") or row["job"].strip() == "":
                return False, "Missing fields 'id' or 'job'", {}
            cleaned["id"] = int(row["id"])
            cleaned["job"] = str(row["job"]).strip()
            
        return True, "Valid", cleaned
    except Exception as e:
        return False, f"Data type parsing error: {str(e)}", {}

def insert_single_row(row: dict, table: str) -> bool:
    """Inserta una sola fila de forma aislada."""
    try:
        columns = list(row.keys())
        col_string = ", ".join(columns)
        param_string = ", ".join([f":{col}" for col in columns])
        sql_statement = f"INSERT INTO {table} ({col_string}) VALUES ({param_string}) ON CONFLICT (id) DO NOTHING"
        
        entry_params = []
        for col in columns:
            value = row[col]
            if value is None:
                entry_params.append({"name": col, "value": {"isNull": True}})
            elif isinstance(value, int):
                entry_params.append({"name": col, "value": {"longValue": value}})
            else:
                entry_params.append({"name": col, "value": {"stringValue": str(value)}})

        rds_client.execute_statement(
            resourceArn=CLUSTER_ARN,
            secretArn=SECRET_ARN,
            database=DATABASE_NAME,
            sql=sql_statement,
            parameters=entry_params
        )
        return True
    except Exception as db_err:
        logger.warning(f"[DATABASE REJECTION LOGGED] Table: {table} | Reason: {str(db_err)} | Data: {row}")
        return False

def lambda_handler(event, context):
    # 1. Detectar el método HTTP y la ruta de la solicitud (Soporta API Gateway / Function URL)
    http_method = event.get('requestContext', {}).get('http', {}).get('method', event.get('httpMethod', 'POST'))
    path = event.get('rawPath', event.get('path', ''))

    # =========================================================================
    # --- CHALLENGE #2: NUEVOS ENDPOINTS ANALÍTICOS (GET) ---
    # =========================================================================
    if http_method == 'GET':
        try:
            if path == '/analytics/quarterly-hiring':
                # 1. Llamada directa a la API de AWS
                response = rds_client.execute_statement(
                    resourceArn=CLUSTER_ARN,
                    secretArn=SECRET_ARN,
                    database=DATABASE_NAME,
                    includeResultMetadata=True,
                    sql="""SELECT 
                            d.department AS department,
                            j.job AS job,
                            COUNT(CASE WHEN EXTRACT(QUARTER FROM CAST(he.datetime AS TIMESTAMP)) = 1 THEN 1 END) AS q1,
                            COUNT(CASE WHEN EXTRACT(QUARTER FROM CAST(he.datetime AS TIMESTAMP)) = 2 THEN 1 END) AS q2,
                            COUNT(CASE WHEN EXTRACT(QUARTER FROM CAST(he.datetime AS TIMESTAMP)) = 3 THEN 1 END) AS q3,
                            COUNT(CASE WHEN EXTRACT(QUARTER FROM CAST(he.datetime AS TIMESTAMP)) = 4 THEN 1 END) AS q4
                            FROM hired_employees he
                            INNER JOIN departments d ON he.department_id = d.id
                            INNER JOIN jobs j ON he.job_id = j.id
                            WHERE EXTRACT(YEAR FROM CAST(he.datetime AS TIMESTAMP)) = 2021
                            GROUP BY d.department, j.job
                            ORDER BY d.department ASC, j.job ASC;"""
                )
            
                clean_data = parse_data_api_response(response)

                # 2. Retornamos la respuesta cruda de AWS sin manipularla
                return {
                    "statusCode": 200,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps(clean_data, default=str)
                }
                
            elif path == '/analytics/top-departments':
                data = query_top_departments()
                return {
                    "statusCode": 200,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps(data, default=str)
                }
                
            elif path == '/analytics/test-db':
                # Una consulta ultra simple que solo cuenta cuántos registros hay en la tabla
                sql_test = "SELECT COUNT(*) AS total FROM hired_em ployees;"
                res = rds_client.execute_statement(
                    resourceArn=CLUSTER_ARN,
                    secretArn=SECRET_ARN,
                    database=DATABASE_NAME,
                    sql=sql_test
                )
                # Devolvemos la respuesta cruda de AWS para ver cómo viene estructurada
                return {
                    "statusCode": 200,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps(res, default=str)
                }
            
            else:
                return {
                    "statusCode": 404,
                    "body": json.dumps({"error": f"Ruta analítica '{path}' no encontrada."})
                }
        except Exception as e:
            return {
                "statusCode": 500,
                "body": json.dumps({"error": f"Error al procesar consulta analítica: {str(e)}"})
            }

    # =========================================================================
    # --- CHALLENGE #1: LOGICA EXISTENTE PARA CARGA DE CSV (POST) ---
    # =========================================================================
    elif http_method == 'POST':
        query_params = event.get("queryStringParameters") or {}
        table = query_params.get("table")
        
        if table not in ["hired_employees", "jobs", "departments"]:
            return {"statusCode": 400, "body": json.dumps({"error": "Invalid or missing '?table=' parameter"})}

        csv_content = event.get("body", "")
        if not csv_content:
            return {"statusCode": 400, "body": json.dumps({"error": "Empty CSV body"})}

        # Forzar la lectura con las columnas fijas inyectadas directamente mediante fieldnames
        csv_file = io.StringIO(csv_content.strip())
        explicit_headers = TABLE_HEADERS[table]
        reader = list(csv.DictReader(csv_file, fieldnames=explicit_headers))
        
        if len(reader) > 1000:
            return {"statusCode": 400, "body": json.dumps({"error": "The CSV file exceeds the limit of 1000 rows"})}

        inserted_rows_count = 0
        failed_rows_count = 0
        
        for idx, row in enumerate(reader):
            is_valid, reason, cleaned_data = clean_and_validate_row(row, table)
            
            if is_valid:
                # Nota: insert_single_row debe gestionar su propia apertura/cierre de conexión
                success = insert_single_row(cleaned_data, table)
                if success:
                    inserted_rows_count += 1
                else:
                    failed_rows_count += 1
            else:
                failed_rows_count += 1
                logger.warning(f"[INVALID RECORD LOGGED] Table: {table} | Row: {idx} | Reason: {reason} | Data: {row}")

        return {
            "statusCode": 201,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "status": "Batch processed inline with static schema",
                "inserted_rows": inserted_rows_count,
                "failed_rows_logged": failed_rows_count
            })
        }

    # Si se invoca con otro método no soportado (PUT, DELETE, etc.)
    return {
        "statusCode": 405,
        "body": json.dumps({"error": f"Method {http_method} not allowed"})
    }