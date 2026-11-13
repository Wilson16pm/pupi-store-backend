# Usamos una imagen oficial de Python (versión completa, no 'slim')
FROM python:3.11

# Evita que apt pida confirmación interactiva
ENV DEBIAN_FRONTEND=noninteractive

# Instalamos dependencias del sistema y el driver ODBC de Microsoft
RUN apt-get update && \
    apt-get install -y curl gnupg2 apt-transport-https ca-certificates unixodbc-dev && \
    curl https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /etc/apt/trusted.gpg.d/microsoft.gpg && \
    curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql17 && \
    rm -rf /var/lib/apt/lists/*

# Copiamos los archivos de tu proyecto
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Exponemos el puerto y corremos la app
EXPOSE 10000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
