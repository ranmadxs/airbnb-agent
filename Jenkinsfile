// Jenkinsfile — CI/CD pipeline para airbnb-agent
//
// Stages:
//   1. Checkout   — obtiene código del PR/branch
//   2. Setup      — instala Python 3.11+ y Poetry
//   3. Unit Tests — corre la suite de pytest (mismo flujo que el PR workflow de GitHub)
//   4. Coverage   — publica el reporte Cobertura + chequea umbral mínimo
//
// Para que funcione, el Jenkins debe tener:
//   - Plugin "Pipeline" (incluye Cobertura)
//   - Plugin "Cobertura" (reporte de coverage)
//   - Tool "poetry" instalado en el agente (o se instala vía pip en el stage Setup)
//   - Credenciales SSH/credential ID para repo privado (ajustar abajo si aplica)
//
pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 15, unit: 'MINUTES')
        // No usar build dir por defecto; limpiamos manualmente
        ansiColor('xterm')
    }

    environment {
        // Variables dummy para que airbnb_agent se importe sin reventar en tests
        SECRET_KEY              = 'jenkins-test-secret'
        AUTH_USERNAME           = 'admin'
        AUTH_PASSWORD           = 'admin'
        MONGODB_URI             = ''
        AIRBNB_CALENDAR_URL     = ''
        BOOKING_CALENDAR_URL    = ''
        MERCADOPAGO_ACCESS_TOKEN = ''
        MERCADOPAGO_WEBHOOK_SECRET = ''
        // Umbral mínimo de coverage (porcentaje). Si baja, falla el build.
        COVERAGE_MIN            = '25'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Setup') {
            steps {
                sh '''
                    set -e
                    python3 --version
                    python3 -m pip --version

                    # Instalar Poetry si no está
                    if ! command -v poetry >/dev/null 2>&1; then
                        echo "Instalando Poetry..."
                        python3 -m pip install --quiet poetry
                    fi
                    poetry --version
                '''
            }
        }

        stage('Install dependencies') {
            steps {
                sh '''
                    set -e
                    poetry config virtualenvs.create true
                    poetry config virtualenvs.in-project true
                    poetry install --with dev --no-interaction --no-ansi
                '''
            }
        }

        stage('Unit Tests') {
            steps {
                sh '''
                    set -e
                    echo "================================================"
                    echo "  Ejecutando suite de tests unitarios (pytest)"
                    echo "================================================"
                    poetry run pytest \
                        --cov=airbnb_agent \
                        --cov-report=term \
                        --cov-report=xml:coverage.xml \
                        --cov-report=html:htmlcov \
                        --junitxml=junit-report.xml \
                        -v
                '''
            }
            post {
                always {
                    // Publicar resultados de tests en la UI de Jenkins
                    junit testResults: 'junit-report.xml', allowEmptyResults: false
                }
            }
        }

        stage('Coverage') {
            steps {
                sh '''
                    set -e
                    COVERAGE_PCT=$(poetry run coverage report --format=total | tail -n1)
                    echo ""
                    echo "================================================"
                    echo "  Porcentaje de cobertura: ${COVERAGE_PCT}%"
                    echo "================================================"
                    echo "${COVERAGE_PCT}" > coverage.txt
                '''
            }
            post {
                always {
                    // Reporte Cobertura (plugin "Cobertura") — pinta gráfica en el build
                    cobertura(
                        coberturaReportFile: 'coverage.xml',
                        failNoReports: false,
                        failUnhealthy: false,
                        // Solo falla si baja del umbral definido en COVERAGE_MIN
                        unhealthyThreshold: [
                            [thresholdTarget: 'Line',  unstableThreshold: '25.0', failedThreshold: '0.0'],
                            [thresholdTarget: 'Branch', unstableThreshold: '25.0', failedThreshold: '0.0']
                        ]
                    )
                    // Publicar el reporte HTML navegable como artefacto
                    archiveArtifacts artifacts: 'htmlcov/**, coverage.txt, coverage.xml',
                                     allowEmptyArchive: false,
                                     fingerprint: true
                }
            }
        }
    }

    post {
        success {
            echo "✅ Build OK — tests pasaron y coverage >= ${env.COVERAGE_MIN}%"
        }
        failure {
            echo "❌ Build falló — revisar logs arriba (Unit Tests o Coverage)"
        }
        always {
            // Limpieza opcional del workspace
            cleanWs(
                deleteDirs: false,
                patterns: [
                    [pattern: 'htmlcov/**', type: 'INCLUDE'],
                    [pattern: '.venv/**', type: 'INCLUDE'],
                ]
            )
        }
    }
}