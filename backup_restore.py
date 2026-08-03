import json
import os
import boto3
from fastavro import writer, reader, parse_schema

# Inicializar cliente de RDS Data API
rds_client = boto3.client('rds-data', region_name='us-east-2')

# CONFIGURACIÓN DE TU BASE DE DATOS (Pon tus ARNs reales)
CLUSTER_ARN = "arn:aws:rds:us-east-2:124194989357:cluster:database-1"
SECRET_ARN = "arn:aws:secretsmanager:us-east-2:124194989357:secret:rds-db-credentials/cluster-V3BH6DFRLDTHEXYUAPKPDTSFKU/postgres/1785528158439-aDho7M" 
DATABASE_NAME = "postgres"

# Definición de Esquemas AVRO Estrictos
SCHEMAS = {
    "departments": {
        "doc": "Backup de la tabla departments",
        "name": "Department",
        "type": "record",
        "fields": [
            {"name": "id", "type": "int"},
            {"name": "department", "type": "string"}
        ]
    },
    "jobs": {
        "doc": "Backup de la tabla jobs",
        "name": "Job",
        "type": "record",
        "fields": [
            {"name": "id", "type": "int"},
            {"name": "job", "type": "string"}
        ]
    },
    "hired_employees": {
        "doc": "Backup de la tabla hired_employees",
        "name": "HiredEmployee",
        "type": "record",
        "fields": [
            {"name": "id", "type": "int"},
            {"name": "name", "type": "string"},
            {"name": "datetime", "type": ["null", "string"], "default": None},
            {"name": "department_id", "type": ["null", "int"], "default": None},
            {"name": "job_id", "type": ["null", "int"], "default": None}
        ]
    }
}

def execute_query(sql: str):
    return rds_client.execute_statement(
        resourceArn=CLUSTER_ARN,
        secretArn=SECRET_ARN,
        database=DATABASE_NAME,
        sql=sql
    )

def backup_table_to_avro(table_name: str, output_directory: str = "./backups"):
    """FASE 4: Exporta el contenido completo de una tabla a formato AVRO en el filesystem."""
    print(f"📦 Iniciando respaldo de la tabla '{table_name}'...")
    
    if table_name not in SCHEMAS:
        print(f"❌ Error: Tabla '{table_name}' no soportada en los esquemas AVRO.")
        return

    os.makedirs(output_directory, exist_ok=True)
    output_path = os.path.join(output_directory, f"{table_name}.avro")

    try:
        response = execute_query(f"SELECT * FROM {table_name}")
        records = response.get("records", [])
        column_metadata = response.get("columnMetadata", [])
        
        # SOLUCIÓN AL EXCEPCIÓN: Si la tabla está vacía, extraemos las columnas del esquema AVRO fijo
        if not column_metadata:
            columns = [field["name"] for field in SCHEMAS[table_name]["fields"]]
        else:
            columns = [col["name"] for col in column_metadata]
            
    except Exception as e:
        print(f"❌ Error al consultar la base de datos: {str(e)}")
        return

    # Si la tabla no tiene filas, guardamos un archivo AVRO válido pero con 0 registros
    parsed_records = []
    if records:
        for row in records:
            record_dict = {}
            for idx, field_value in enumerate(row):
                col_name = columns[idx]
                
                if "isNull" in field_value and field_value["isNull"]:
                    record_dict[col_name] = None
                elif "longValue" in field_value:
                    record_dict[col_name] = int(field_value["longValue"])
                elif "stringValue" in field_value:
                    record_dict[col_name] = str(field_value["stringValue"])
                else:
                    record_dict[col_name] = None
                    
            parsed_records.append(record_dict)

    # Escribir el archivo AVRO (soporta listas vacías perfectamente)
    parsed_schema = parse_schema(SCHEMAS[table_name])
    with open(output_path, "wb") as out_file:
        writer(out_file, parsed_schema, parsed_records)
        
    print(f"✅ ¡Respaldo completado! Archivo guardado con éxito en: {output_path} ({len(parsed_records)} filas exportadas).")

def restore_table_from_avro(table_name: str, input_directory: str = "./backups"):
    """FASE 5: Restaura una tabla a partir de un archivo AVRO de respaldo."""
    print(f"🔄 Iniciando restauración de la tabla '{table_name}' desde AVRO...")
    input_path = os.path.join(input_directory, f"{table_name}.avro")

    if not os.path.exists(input_path):
        print(f"❌ Error: No se encontró el archivo de respaldo en '{input_path}'")
        return

    avro_records = []
    with open(input_path, "rb") as in_file:
        avro_reader = reader(in_file)
        for record in avro_reader:
            avro_records.append(record)

    if not avro_records:
        print("⚠️ El archivo de respaldo AVRO está vacío. No hay registros para reinsertar.")
        return

    print(f"... Limpiando registros antiguos de la tabla '{table_name}'...")
    try:
        execute_query(f"TRUNCATE TABLE {table_name} CASCADE")
    except Exception as e:
        print(f"❌ Error al limpiar la tabla: {str(e)}")
        return

    try:
        # Extraer las columnas de la primera fila del AVRO
        columns = list(avro_records[0].keys())
        col_string = ", ".join(columns)
        param_string = ", ".join([f":{col}" for col in columns])
        sql_statement = f"INSERT INTO {table_name} ({col_string}) VALUES ({param_string})"
        
        parameter_sets = []
        for row in avro_records:
            entry_params = []
            for col in columns:
                value = row[col]
                if value is None:
                    entry_params.append({"name": col, "value": {"isNull": True}})
                elif isinstance(value, int):
                    entry_params.append({"name": col, "value": {"longValue": value}})
                else:
                    entry_params.append({"name": col, "value": {"stringValue": str(value)}})
            parameter_sets.append(entry_params)

        rds_client.batch_execute_statement(
            resourceArn=CLUSTER_ARN,
            secretArn=SECRET_ARN,
            database=DATABASE_NAME,
            sql=sql_statement,
            parameterSets=parameter_sets
        )
        print(f"🎉 ¡Restauración exitosa! Se reinsertaron {len(avro_records)} filas de forma atómica en la tabla '{table_name}'.")
        
    except Exception as db_err:
        print(f"❌ Error crítico durante la restauración en base de datos: {str(db_err)}")

if __name__ == "__main__":
    print("--- INICIANDO PRUEBAS DE RESPALDO (BACKUP) ---")
    backup_table_to_avro("departments")
    backup_table_to_avro("jobs")
    backup_table_to_avro("hired_employees")
    
    print("\n--- INICIANDO PRUEBAS DE RESTAURACIÓN (RESTORE) ---")
    restore_table_from_avro("departments")
