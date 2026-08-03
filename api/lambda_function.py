import json
import boto3
import logging
from datetime import datetime
from typing import List, Dict, Tuple

# Configurar el logger oficial de AWS Lambda
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Inicializar cliente de RDS Data API
rds_client = boto3.client('rds-data')

# CONFIGURACIÓN DE TU BASE DE DATOS (Pon tus ARNs reales)
CLUSTER_ARN = "arn:aws:rds:us-east-2:124194989357:cluster:database-1"
SECRET_ARN = "arn:aws:secretsmanager:us-east-2:124194989357:secret:rds-db-credentials/cluster-V3BH6DFRLDTHEXYUAPKPDTSFKU/postgres/1785528158439-aDho7M"
DATABASE_NAME = "postgres"

def validate_iso_8601(date_string: str) -> bool:
    """Verifica si una cadena de texto cumple con el formato estricto ISO 8601."""
    formats = ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d %H:%M:%S"]
    for fmt in formats:
        try:
            datetime.strptime(date_string, fmt)
            return True
        except ValueError:
            continue
    return False

def validate_row_against_dictionary(row: Dict, table: str) -> Tuple[bool, str]:
    """Aplica las reglas comerciales estrictas del desafío para cada tabla."""
    try:
        # Regla 1: Validar Tabla de Empleados
        if table == "hired_employees":
            required_fields = ["id", "name", "datetime", "department_id", "job_id"]
            # Todos los campos son obligatorios y no pueden ser None
            for field in required_fields:
                if field not in row or row[field] is None:
                    return False, f"Missing or null required field: '{field}'"
            
            # Validaciones de Tipo
            if not isinstance(row["id"], int) or not isinstance(row["department_id"], int) or not isinstance(row["job_id"], int):
                return False, "Fields 'id', 'department_id', and 'job_id' must be integers"
            if not isinstance(row["name"], str) or row["name"].strip() == "":
                return False, "Field 'name' must be a non-empty string"
                
            # Regla Estricta: Validación de fecha ISO 8601
            if not validate_iso_8601(str(row["datetime"])):
                return False, f"Field 'datetime' value '{row['datetime']}' is not in valid ISO 8601 format"

        # Regla 2: Validar Tabla de Departamentos
        elif table == "departments":
            if "id" not in row or "department" not in row or row["id"] is None or row["department"] is None:
                return False, "Missing or null fields: 'id' and 'department' are required"
            if not isinstance(row["id"], int) or not isinstance(row["department"], str):
                return False, "Types mismatch: 'id' must be int, 'department' must be string"

        # Regla 3: Validar Tabla de Puestos (Jobs)
        elif table == "jobs":
            if "id" not in row or "job" not in row or row["id"] is None or row["job"] is None:
                return False, "Missing or null fields: 'id' and 'job' are required"
            if not isinstance(row["id"], int) or not isinstance(row["job"], str):
                return False, "Types mismatch: 'id' must be int, 'job' must be string"
                
        return True, "Valid"
    except Exception as e:
        return False, f"Unexpected validation error: {str(e)}"

def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body", "{}"))
        table = body.get("table")
        rows = body.get("rows", [])
        
        # Validar estructura del sobre JSON genérico
        if table not in ["hired_employees", "jobs", "departments"]:
            return {"statusCode": 400, "body": json.dumps({"error": f"Invalid target table: {table}"})}
            
        if not (1 <= len(rows) <= 1000):
            return {"statusCode": 400, "body": json.dumps({"error": "Batch size must be between 1 and 1000 rows"})}
        
        valid_records = []
        invalid_records_count = 0
        
        # Separación Atómica: Fila por fila
        for idx, row in enumerate(rows):
            is_valid, reason = validate_row_against_dictionary(row, table)
            
            if is_valid:
                valid_records.append(row)
            else:
                invalid_records_count += 1
                # REQUERIMIENTO COMPLANCE: Loggear registros inválidos de manera formal
                logger.warning(
                    f"[INVALID RECORD LOGGED] Table: {table} | Row Index: {idx} | Reason: {reason} | Payload: {json.dumps(row)}"
                )
                
    except Exception as parse_err:
        return {"statusCode": 400, "body": json.dumps({"error": "Malformed JSON request structure", "details": str(parse_err)})}

    # Enviar los registros válidos filtrados a la base de datos
    if not valid_records:
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Processing complete. No rows inserted.",
                "inserted_rows": 0,
                "failed_rows_logged": invalid_records_count
            })
        }

    try:
        # Construcción dinámica del SQL parametrizado
        columns = list(valid_records[0].keys())
        col_string = ", ".join(columns)
        param_string = ", ".join([f":{col}" for col in columns])
        sql_statement = f"INSERT INTO {table} ({col_string}) VALUES ({param_string})"
        
        parameter_sets = []
        for row in valid_records:
            entry_params = []
            for col in columns:
                value = row[col]
                if isinstance(value, int):
                    entry_params.append({"name": col, "value": {"longValue": value}})
                else:
                    entry_params.append({"name": col, "value": {"stringValue": str(value)}})
            parameter_sets.append(entry_params)
            
        # Ejecución masiva atómica en Aurora Serverless
        rds_client.batch_execute_statement(
            resourceArn=CLUSTER_ARN,
            secretArn=SECRET_ARN,
            database=DATABASE_NAME,
            sql=sql_statement,
            parameterSets=parameter_sets
        )
        
        return {
            "statusCode": 201,
            "body": json.dumps({
                "message": "Batch processed successfully",
                "inserted_rows": len(valid_records),
                "failed_rows_logged": invalid_records_count
            })
        }
        
    except Exception as db_err:
        # Capturar fallas de llaves foráneas (Integridad referencial contra departamentos/jobs)
        logger.error(f"[DATABASE ERROR] Batch insert failed for table {table}: {str(db_err)}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "Database write failure. Foreign key validation or duplicate ID error detected.",
                "details": str(db_err)
            })
        }
