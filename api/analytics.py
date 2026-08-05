import boto3

rds_client = boto3.client('rds-data')

CLUSTER_ARN = "arn:aws:rds:us-east-2:124194989357:cluster:database-1"
SECRET_ARN = "arn:aws:secretsmanager:us-east-2:124194989357:secret:rds-db-credentials/cluster-V3BH6DFRLDTHEXYUAPKPDTSFKU/postgres/1785528158439-aDho7M"
DATABASE_NAME = "postgres"

def parse_data_api_response(response):
    """
    Desempaqueta con precisión el formato tipado de la RDS Data API
    en un formato JSON plano tradicional.
    """
    if 'columnMetadata' not in response or 'records' not in response:
        print("⚠️ [ALERTA] No se encontraron metadatos o registros en el payload.")
        return []
        
    column_headers = [col['name'] for col in response['columnMetadata']]
    print("📋 [DIAGNOSTICO] Columnas detectadas con éxito:", column_headers)
    print(f"🔢 [DIAGNOSTICO] Cantidad de filas a procesar: {len(response['records'])}")
    
    records = []
    
    for row in response['records']:
        record = {}
        for i in range(len(column_headers)):
            col_name = column_headers[i]
            value_dict = row[i]
            
            # Desempaqueta estructuras tipo: {'stringValue': 'Accounting'} -> 'Accounting'
            if value_dict and isinstance(value_dict, dict):
                record[col_name] = list(value_dict.values())[0]
            else:
                record[col_name] = 0 if col_name in ['q1', 'q2', 'q3', 'q4'] else None
                
        records.append(record)
        
    return records

def query_quarterly_hiring():
    sql = """
    SELECT 
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
    ORDER BY d.department ASC, j.job ASC;
    """
    response = rds_client.execute_statement(
        resourceArn=CLUSTER_ARN,
        secretArn=SECRET_ARN,
        database=DATABASE_NAME,
        sql=sql
    )
    return parse_data_api_response(response)

def query_top_departments():
    sql = """
    WITH total_hiring_per_dept AS (
        SELECT 
            d.id, d.department, COUNT(he.id) AS hired
        FROM departments d
        INNER JOIN hired_employees he ON d.id = he.department_id
        WHERE EXTRACT(YEAR FROM CAST(he.datetime AS TIMESTAMP)) = 2021
        GROUP BY d.id, d.department
    )
    SELECT id, department, hired
    FROM total_hiring_per_dept
    WHERE hired > (SELECT AVG(hired) FROM total_hiring_per_dept)
    ORDER BY hired DESC;
    """
    response = rds_client.execute_statement(
        resourceArn=CLUSTER_ARN,
        secretArn=SECRET_ARN,
        database=DATABASE_NAME,
        sql=sql,
        includeResultMetadata=True
    )
    return parse_data_api_response(response)