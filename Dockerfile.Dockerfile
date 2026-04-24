FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    openjdk-17-jre-headless curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g lighthouse

ENV JMETER_VERSION=5.6.3
RUN curl -L https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-${JMETER_VERSION}.tgz -o /tmp/jmeter.tgz \
    && tar -xzf /tmp/jmeter.tgz -C /opt \
    && ln -s /opt/apache-jmeter-${JMETER_VERSION}/bin/jmeter /usr/local/bin/jmeter \
    && rm /tmp/jmeter.tgz

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p uploads reports lighthouse_reports
EXPOSE 5000
CMD ["python", "app.py"]
