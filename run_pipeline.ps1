Write-Host "🚀 Iniciando Ejecución Integral del Pipeline - Globant Data Engineering POC" -ForegroundColor Cyan

$LambdaUrl = "https://m3a7p7vdd22kqwpn6faqxim2eq0fpkyb.lambda-url.us-east-2.on.aws"

# STEP 1: Ingesta masiva (Challenge #1)
Write-Host "`n📥 [STEP 1] Cargando datos de prueba vía API POST..." -ForegroundColor Yellow
if (Test-Path "./hired_employees2.csv") {
    $CsvContent = Get-Content -Path "./hired_employees2.csv" -Raw
    $ResponsePost = Invoke-RestMethod -Uri "$LambdaUrl?table=hired_employees" -Method Post -ContentType "text/csv; charset=utf-8" -Body $CsvContent.Trim()
    $ResponsePost | ConvertTo-Json
} else {
    Write-Host "⚠️ Archivo hired_employees2.csv no encontrado, saltando carga masiva." -ForegroundColor Red
}

if (Test-Path "./departments.csv") {
    $CsvContent = Get-Content -Path "./departments.csv" -Raw
    $ResponsePost = Invoke-RestMethod -Uri "$LambdaUrl?table=departments" -Method Post -ContentType "text/csv; charset=utf-8" -Body $CsvContent.Trim()
    $ResponsePost | ConvertTo-Json
} else {
    Write-Host "⚠️ Archivo departments.csv no encontrado, saltando carga masiva." -ForegroundColor Red
}

if (Test-Path "./jobs.csv") {
    $CsvContent = Get-Content -Path "./jobs.csv" -Raw
    $ResponsePost = Invoke-RestMethod -Uri "$LambdaUrl?table=jobs" -Method Post -ContentType "text/csv; charset=utf-8" -Body $CsvContent.Trim()
    $ResponsePost | ConvertTo-Json
} else {
    Write-Host "⚠️ Archivo jobs.csv no encontrado, saltando carga masiva." -ForegroundColor Red
}

# STEP 2: Consultas Analíticas (Challenge #2)
Write-Host "`n📊 [STEP 2] Extrayendo Reporte 1: Contrataciones por Trimestre (2021)..." -ForegroundColor Yellow
$Report1 = Invoke-RestMethod -Uri "$LambdaUrl/analytics/quarterly-hiring" -Method Get
$Report1 | Format-Table -AutoSize
# Guardar respaldo local en JSON plano
$Report1 | ConvertTo-Json -Depth 5 | Out-File -FilePath "./reports/quarterly_hiring.json" -Encoding utf8

Write-Host "`n📈 Extrayendo Reporte 2: Departamentos por Encima de la Media (2021)..." -ForegroundColor Yellow
$Report2 = Invoke-RestMethod -Uri "$LambdaUrl/analytics/top-departments" -Method Get
$Report2 | Format-Table -AutoSize
# Guardar respaldo local en JSON plano
$Report2 | ConvertTo-Json -Depth 5 | Out-File -FilePath "./reports/top_departments.json" -Encoding utf8

# STEP 3: Feature de Backup con Docker (Feature Requerido)
Write-Host "`n💾 [STEP 3] Disparando contenedor Docker para respaldo binario (AVRO)..." -ForegroundColor Yellow
# Construir la imagen local
docker build -t globant-data-poc .
# Ejecutar el contenedor mapeando un volumen local para guardar los archivos .avro generados
docker run --rm -v "$(Get-Location)/backups:/app/backups" globant-data-poc

Write-Host "`n✅ Pipeline completado con éxito de extremo a extremo." -ForegroundColor Green