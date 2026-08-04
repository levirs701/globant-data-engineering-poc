import json
import boto3
import csv
import io
import logging
from datetime import datetime

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